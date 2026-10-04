from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from ..domain import Side


@dataclass(frozen=True)
class MarketSeries:
    symbol: str
    closes: tuple[float, ...]
    highs: tuple[float, ...]
    lows: tuple[float, ...]
    spread: float

    @property
    def price(self) -> float:
        return float(self.closes[-1])


@dataclass(frozen=True)
class StrategyCandidate:
    strategy: str
    symbol: str
    side: Side
    confidence: float
    entry_reference: float
    stop_distance: float
    target_distance: float
    diagnostics: dict[str, float]


class Strategy(Protocol):
    name: str

    def evaluate(self, market: MarketSeries) -> StrategyCandidate | None: ...


def _ema(values: np.ndarray, period: int) -> float:
    if len(values) < period:
        raise ValueError("insufficient values for EMA")
    alpha = 2.0 / (period + 1.0)
    value = float(values[0])
    for item in values[1:]:
        value = alpha * float(item) + (1.0 - alpha) * value
    return value


def _rsi(values: np.ndarray, period: int = 14) -> float:
    if len(values) <= period:
        return 50.0
    diff = np.diff(values[-(period + 1):])
    gains = np.where(diff > 0, diff, 0.0).mean()
    losses = np.where(diff < 0, -diff, 0.0).mean()
    if losses == 0:
        return 100.0
    rs = gains / losses
    return float(100.0 - (100.0 / (1.0 + rs)))


def _atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
    n = min(len(highs), len(lows), len(closes))
    if n <= period:
        return 0.0
    h = highs[-(period + 1):]
    l = lows[-(period + 1):]
    c = closes[-(period + 1):]
    tr = np.maximum(
        h[1:] - l[1:],
        np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])),
    )
    return float(np.mean(tr))


class TrendMomentumStrategy:
    name = "trend-momentum-v1"

    def __init__(
        self,
        fast_ema: int = 12,
        slow_ema: int = 26,
        atr_period: int = 14,
        stop_atr: float = 1.5,
        target_atr: float = 2.4,
        min_confidence: float = 0.56,
    ) -> None:
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.atr_period = atr_period
        self.stop_atr = stop_atr
        self.target_atr = target_atr
        self.min_confidence = min_confidence

    def evaluate(self, market: MarketSeries) -> StrategyCandidate | None:
        closes = np.asarray(market.closes, dtype=float)
        highs = np.asarray(market.highs, dtype=float)
        lows = np.asarray(market.lows, dtype=float)
        if len(closes) < max(self.slow_ema + 5, self.atr_period + 5):
            return None
        price = float(closes[-1])
        if price <= 0:
            return None

        fast = _ema(closes[-80:], self.fast_ema)
        slow = _ema(closes[-100:], self.slow_ema)
        atr = _atr(highs, lows, closes, self.atr_period)
        if atr <= 0:
            return None
        rsi = _rsi(closes)
        trend = (fast - slow) / max(atr, 1e-12)
        recent = (price / float(closes[-6])) - 1.0 if len(closes) >= 6 else 0.0
        spread_penalty = min(0.20, market.spread / max(atr, 1e-12) * 0.5)

        if trend > 0.10 and rsi >= 52 and recent > 0:
            side = Side.BUY
            momentum = min(1.0, max(0.0, (rsi - 50.0) / 25.0))
        elif trend < -0.10 and rsi <= 48 and recent < 0:
            side = Side.SELL
            momentum = min(1.0, max(0.0, (50.0 - rsi) / 25.0))
        else:
            return None

        trend_strength = min(1.0, abs(trend) / 2.0)
        confidence = 0.50 + 0.28 * trend_strength + 0.18 * momentum - spread_penalty
        confidence = float(min(0.95, max(0.0, confidence)))
        if confidence < self.min_confidence:
            return None

        return StrategyCandidate(
            strategy=self.name,
            symbol=market.symbol,
            side=side,
            confidence=confidence,
            entry_reference=price,
            stop_distance=atr * self.stop_atr,
            target_distance=atr * self.target_atr,
            diagnostics={
                "ema_fast": fast,
                "ema_slow": slow,
                "rsi": rsi,
                "atr": atr,
                "trend_atr": trend,
                "recent_return": recent,
                "spread_atr": market.spread / atr,
            },
        )


class StrategyRegistry:
    def __init__(self, strategies: list[Strategy] | None = None) -> None:
        self._strategies: dict[str, Strategy] = {}
        for strategy in strategies or [TrendMomentumStrategy()]:
            self.register(strategy)

    def register(self, strategy: Strategy) -> None:
        self._strategies[strategy.name] = strategy

    def names(self) -> list[str]:
        return sorted(self._strategies)

    def evaluate(self, market: MarketSeries) -> list[StrategyCandidate]:
        candidates = [
            result
            for strategy in self._strategies.values()
            if (result := strategy.evaluate(market)) is not None
        ]
        return sorted(candidates, key=lambda item: item.confidence, reverse=True)
