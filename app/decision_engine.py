from __future__ import annotations

from dataclasses import dataclass

from .domain import OrderRequest, Quote, Signal
from .paper_trading import PaperTradingEngine, Position
from .risk import AccountState, RiskEngine


@dataclass(frozen=True)
class DecisionResult:
    approved: bool
    reason: str
    order: OrderRequest | None = None
    position: Position | None = None


class TradingDecisionEngine:
    """Connect strategy signals to the risk gate and paper execution layer."""

    def __init__(self, risk: RiskEngine | None = None, paper: PaperTradingEngine | None = None) -> None:
        self.risk = risk or RiskEngine()
        self.paper = paper or PaperTradingEngine()

    def process(
        self,
        signal: Signal,
        quote: Quote,
        account: AccountState,
        value_per_price_unit: float,
    ) -> DecisionResult:
        if signal.symbol != quote.symbol:
            return DecisionResult(False, "signal/quote symbol mismatch")
        if not 0.0 <= signal.probability <= 1.0 or not 0.0 <= signal.confidence <= 1.0:
            return DecisionResult(False, "invalid probability or confidence")
        if signal.stop_price <= 0 or signal.take_profit <= 0:
            return DecisionResult(False, "invalid protective prices")

        entry = quote.ask if signal.side.value == "buy" else quote.bid
        stop_distance = abs(entry - signal.stop_price)
        if stop_distance <= 0:
            return DecisionResult(False, "zero stop distance")

        risk = self.risk.check(account, stop_distance, value_per_price_unit)
        if not risk.approved:
            return DecisionResult(False, risk.reason)

        order = OrderRequest(
            symbol=signal.symbol,
            side=signal.side,
            units=risk.units,
            entry_price=entry,
            stop_loss=signal.stop_price,
            take_profit=signal.take_profit,
        )
        try:
            order.validate()
            position = self.paper.open(order, quote)
        except ValueError as exc:
            return DecisionResult(False, f"order rejected: {exc}")
        return DecisionResult(True, "approved", order, position)
