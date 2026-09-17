from dataclasses import dataclass

from .domain import Side, Signal


@dataclass(frozen=True)
class StrategyConfig:
    min_confidence: float = 0.60
    min_edge_after_costs: float = 0.0
    reward_risk: float = 1.5


class BaselineStrategy:
    """A deliberately simple research baseline, not a production alpha model."""

    def __init__(self, config: StrategyConfig | None = None) -> None:
        self.config = config or StrategyConfig()

    def generate(self, symbol: str, price: float, ema_fast: float, ema_slow: float,
                 probability: float, expected_move: float, transaction_cost: float) -> Signal | None:
        if probability < self.config.min_confidence:
            return None
        edge = expected_move - transaction_cost
        if edge <= self.config.min_edge_after_costs:
            return None
        if ema_fast == ema_slow or price <= 0 or expected_move <= 0:
            return None

        side = Side.BUY if ema_fast > ema_slow else Side.SELL
        stop_distance = expected_move / self.config.reward_risk
        if side is Side.BUY:
            stop, target = price - stop_distance, price + expected_move
        else:
            stop, target = price + stop_distance, price - expected_move
        return Signal(symbol, side, probability, probability, edge, stop, target)
