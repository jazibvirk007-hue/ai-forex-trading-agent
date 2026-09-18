from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and normalize 5 years of EURUSD M5 data.")
    parser.add_argument("--from-date", default="2021-09-17")
    parser.add_argument("--to-date", default="2026-09-17")
    parser.add_argument("--output-dir", default="data/raw")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--batch-pause-ms", type=int, default=1000)
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    command = [
        "npx", "--yes", "dukascopy-node",
        "-i", "eurusd", "-from", args.from_date, "-to", args.to_date,
        "-t", "m5", "-f", "csv", "-bs", str(args.batch_size), "-bp", str(args.batch_pause_ms),
    ]
    print(" ".join(command), flush=True)
    subprocess.run(command, cwd=output_dir, check=True)

    candidates = sorted(
        path
        for path in output_dir.rglob("*.csv")
        if path.name.lower().startswith("eurusd-") and "-m5" in path.name.lower()
    )
    if not candidates:
        raise FileNotFoundError(
            f"No EURUSD M5 CSV files were produced under {output_dir}. "
            f"CSV files found: {[str(p.relative_to(output_dir)) for p in output_dir.rglob('*.csv')]}"
        )

    frames = [pd.read_csv(path) for path in candidates]
    frame = pd.concat(frames, ignore_index=True)
    if "datetime" in frame.columns and "timestamp" not in frame.columns:
        frame = frame.rename(columns={"datetime": "timestamp"})

    # Dukascopy FX rate downloads do not provide exchange volume by default.
    # The normalized OHLCV schema requires a non-negative volume column, but
    # none of the current research features use volume, so use an explicit
    # zero placeholder rather than fabricating tick/exchange volume.
    if "volume" not in frame.columns:
        frame["volume"] = 0.0

    required = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"Downloaded data missing columns: {missing}")

    frame = frame[required].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    for column in required[1:]:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    frame = frame.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")

    target = output_dir / "EURUSD_M5_5Y_raw.csv"
    frame.to_csv(target, index=False)
    for path in candidates:
        if path.resolve() != target.resolve():
            path.unlink()

    print(f"Saved {len(frame):,} rows to {target}", flush=True)
    print(f"Range: {frame['timestamp'].min()} -> {frame['timestamp'].max()}", flush=True)


if __name__ == "__main__":
    main()
