from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Download 5 years of EURUSD M5 data from Dukascopy via dukascopy-node.")
    parser.add_argument("--from-date", default="2021-09-17")
    parser.add_argument("--to-date", default="2026-09-17")
    parser.add_argument("--output-dir", default="data/raw")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--batch-pause-ms", type=int, default=1000)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    command = [
        "npx", "--yes", "dukascopy-node",
        "-i", "eurusd",
        "-from", args.from_date,
        "-to", args.to_date,
        "-t", "m5",
        "-f", "csv",
        "-bs", str(args.batch_size),
        "-bp", str(args.batch_pause_ms),
    ]
    print("Downloading EURUSD M5 historical data:")
    print(" ".join(command))
    subprocess.run(command, cwd=output_dir, check=True)

    candidates = sorted(output_dir.glob("eurusd-*-m5.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(
            f"dukascopy-node completed but no eurusd-*-m5.csv was found in {output_dir.resolve()}"
        )

    source = candidates[0]
    target = output_dir / "EURUSD_M5_5Y_raw.csv"
    if source.resolve() != target.resolve():
        source.replace(target)
    print(f"Saved: {target.resolve()}")


if __name__ == "__main__":
    main()
