from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .domain import Side


@dataclass(frozen=True)
class Exposure:
    symbol: str
    side: Side
    returns: np.ndarray


@dataclass(frozen=True)
class CorrelationResult:
    correlated_positions: int
    blockers: tuple[str, ...]


class CorrelationGuard:
    """Counts portfolio exposures that materially duplicate a candidate trade."""

    def __init__(self, threshold: float = 0.80, min_points: int = 30) -> None:
        if not 0 < threshold <= 1:
            raise ValueError("correlation threshold must be in (0, 1]")
        self.threshold = threshold
        self.min_points = max(10, min_points)

    def compare(
        self,
        candidate_side: Side,
        candidate_returns: np.ndarray,
        exposures: list[Exposure],
    ) -> CorrelationResult:
        blockers: list[str] = []
        candidate = np.asarray(candidate_returns, dtype=float)
        for exposure in exposures:
            other = np.asarray(exposure.returns, dtype=float)
            n = min(len(candidate), len(other))
            if n < self.min_points:
                continue
            left = candidate[-n:]
            right = other[-n:]
            if np.std(left) == 0 or np.std(right) == 0:
                continue
            corr = float(np.corrcoef(left, right)[0, 1])
            same_direction = candidate_side is exposure.side
            duplicates = (same_direction and corr >= self.threshold) or (
                not same_direction and corr <= -self.threshold
            )
            if duplicates:
                blockers.append(f"{exposure.symbol}:{corr:+.2f}")
        return CorrelationResult(len(blockers), tuple(blockers))


def close_returns(closes: list[float] | np.ndarray) -> np.ndarray:
    values = np.asarray(closes, dtype=float)
    if len(values) < 2:
        return np.asarray([], dtype=float)
    previous = values[:-1]
    current = values[1:]
    valid = previous != 0
    return (current[valid] / previous[valid]) - 1.0
