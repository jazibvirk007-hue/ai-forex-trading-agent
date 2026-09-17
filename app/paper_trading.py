from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .domain import OrderRequest, Quote, Side


@dataclass
class Position:
    position_id: str
    symbol: str
    side: Side
    units: float
    entry_price: float
    stop_loss: float
    take_profit: float
    opened_at: datetime
    highest_price: float
    lowest_price: float


@dataclass(frozen=True)
class ClosedTrade:
    position_id: str
    symbol: str
    side: Side
    units: float
    entry_price: float
    exit_price: float
    pnl_price: float
    reason: str
    opened_at: datetime
    closed_at: datetime


class PaperTradingEngine:
    """Deterministic paper position lifecycle using bid/ask-aware exits."""

    def __init__(self) -> None:
        self.positions: dict[str, Position] = {}
        self.closed_trades: list[ClosedTrade] = []
        self._counter = 0

    def open(self, order: OrderRequest, quote: Quote, now: datetime | None = None) -> Position:
        order.validate()
        now = now or quote.timestamp
        self._counter += 1
        position_id = f"paper-{self._counter:06d}"
        position = Position(
            position_id=position_id,
            symbol=order.symbol,
            side=order.side,
            units=order.units,
            entry_price=order.entry_price,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            opened_at=now,
            highest_price=quote.mid,
            lowest_price=quote.mid,
        )
        self.positions[position_id] = position
        return position

    def update(self, quote: Quote) -> list[ClosedTrade]:
        closed: list[ClosedTrade] = []
        for position_id, position in list(self.positions.items()):
            if position.symbol != quote.symbol:
                continue
            position.highest_price = max(position.highest_price, quote.mid)
            position.lowest_price = min(position.lowest_price, quote.mid)

            if position.side is Side.BUY:
                # A long exits at bid; stop has priority when both are touched in a bar/tick.
                if quote.bid <= position.stop_loss:
                    closed.append(self.close(position_id, quote.bid, "stop_loss", quote.timestamp))
                elif quote.bid >= position.take_profit:
                    closed.append(self.close(position_id, quote.bid, "take_profit", quote.timestamp))
            else:
                # A short exits at ask.
                if quote.ask >= position.stop_loss:
                    closed.append(self.close(position_id, quote.ask, "stop_loss", quote.timestamp))
                elif quote.ask <= position.take_profit:
                    closed.append(self.close(position_id, quote.ask, "take_profit", quote.timestamp))
        return closed

    def close(self, position_id: str, exit_price: float, reason: str, now: datetime) -> ClosedTrade:
        position = self.positions.pop(position_id)
        direction = 1.0 if position.side is Side.BUY else -1.0
        pnl_price = (exit_price - position.entry_price) * direction * position.units
        trade = ClosedTrade(
            position_id=position.position_id,
            symbol=position.symbol,
            side=position.side,
            units=position.units,
            entry_price=position.entry_price,
            exit_price=exit_price,
            pnl_price=pnl_price,
            reason=reason,
            opened_at=position.opened_at,
            closed_at=now,
        )
        self.closed_trades.append(trade)
        return trade

    def force_close_all(self, quotes: dict[str, Quote], reason: str = "time_stop") -> list[ClosedTrade]:
        closed: list[ClosedTrade] = []
        for position_id, position in list(self.positions.items()):
            quote = quotes.get(position.symbol)
            if quote is None:
                continue
            exit_price = quote.bid if position.side is Side.BUY else quote.ask
            closed.append(self.close(position_id, exit_price, reason, quote.timestamp))
        return closed
