from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .domain import Side
from .paper_trading import ClosedTrade, Position


@dataclass
class PaperAccount:
    starting_equity: float
    equity: float
    peak_equity: float
    day_start_equity: float
    week_start_equity: float
    current_day: date | None = None
    current_week: tuple[int, int] | None = None

    @classmethod
    def create(cls, equity: float) -> "PaperAccount":
        if equity <= 0:
            raise ValueError("starting equity must be positive")
        return cls(equity, equity, equity, equity, equity)

    def mark_to_market(self, positions: list[Position], quotes: dict) -> float:
        floating = 0.0
        for p in positions:
            q = quotes.get(p.symbol)
            if q is None:
                continue
            exit_price = q.bid if p.side is Side.BUY else q.ask
            direction = 1.0 if p.side is Side.BUY else -1.0
            floating += (exit_price - p.entry_price) * direction * p.units
        return self.equity + floating

    def apply_closed_trade(self, trade: ClosedTrade) -> float:
        self.equity += trade.pnl_price
        self.peak_equity = max(self.peak_equity, self.equity)
        return self.equity

    @property
    def drawdown(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, 1.0 - self.equity / self.peak_equity)

    @property
    def daily_loss(self) -> float:
        return max(0.0, 1.0 - self.equity / self.day_start_equity)

    @property
    def weekly_loss(self) -> float:
        return max(0.0, 1.0 - self.equity / self.week_start_equity)
