from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class TradeMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


@dataclass(frozen=True)
class Quote:
    symbol: str
    timestamp: datetime
    bid: float
    ask: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> float:
        return self.ask - self.bid


@dataclass(frozen=True)
class Signal:
    symbol: str
    side: Side
    probability: float
    confidence: float
    expected_edge: float
    stop_price: float
    take_profit: float


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: Side
    units: float
    entry_price: float
    stop_loss: float
    take_profit: float

    def validate(self) -> None:
        if self.units <= 0:
            raise ValueError("units must be positive")
        if self.stop_loss <= 0 or self.take_profit <= 0:
            raise ValueError("stop loss and take profit are required")
        if self.side is Side.BUY and not (self.stop_loss < self.entry_price < self.take_profit):
            raise ValueError("buy order requires SL < entry < TP")
        if self.side is Side.SELL and not (self.take_profit < self.entry_price < self.stop_loss):
            raise ValueError("sell order requires TP < entry < SL")
