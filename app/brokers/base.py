from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..domain import OrderRequest, Quote


@dataclass(frozen=True)
class OrderResult:
    accepted: bool
    order_id: str | None
    message: str


class Broker(ABC):
    @abstractmethod
    def quote(self, symbol: str) -> Quote: ...

    @abstractmethod
    def submit(self, order: OrderRequest) -> OrderResult: ...

    @abstractmethod
    def cancel(self, order_id: str) -> bool: ...
