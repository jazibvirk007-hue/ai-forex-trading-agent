from __future__ import annotations

from datetime import datetime, timezone
import uuid

from .base import Broker, OrderResult
from ..domain import OrderRequest, Quote


class PaperBroker(Broker):
    def __init__(self, quotes: dict[str, Quote] | None = None) -> None:
        self.quotes = quotes or {}
        self.orders: dict[str, OrderRequest] = {}

    def quote(self, symbol: str) -> Quote:
        if symbol not in self.quotes:
            raise KeyError(f"no paper quote for {symbol}")
        return self.quotes[symbol]

    def submit(self, order: OrderRequest) -> OrderResult:
        order.validate()
        order_id = str(uuid.uuid4())
        self.orders[order_id] = order
        return OrderResult(True, order_id, "paper order accepted")

    def cancel(self, order_id: str) -> bool:
        return self.orders.pop(order_id, None) is not None

    @staticmethod
    def synthetic_quote(symbol: str, mid: float, spread: float = 0.0001) -> Quote:
        return Quote(symbol, datetime.now(timezone.utc), mid - spread / 2, mid + spread / 2)
