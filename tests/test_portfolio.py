import numpy as np

from app.domain import Side
from app.portfolio import CorrelationGuard, Exposure


def test_same_direction_high_correlation_is_counted():
    candidate = np.linspace(-0.01, 0.01, 60)
    exposure = Exposure("GBPUSD", Side.BUY, candidate * 0.9)
    result = CorrelationGuard(threshold=0.8).compare(
        Side.BUY,
        candidate,
        [exposure],
    )
    assert result.correlated_positions == 1


def test_opposite_direction_positive_correlation_is_not_duplicate():
    candidate = np.linspace(-0.01, 0.01, 60)
    exposure = Exposure("GBPUSD", Side.SELL, candidate)
    result = CorrelationGuard(threshold=0.8).compare(
        Side.BUY,
        candidate,
        [exposure],
    )
    assert result.correlated_positions == 0
