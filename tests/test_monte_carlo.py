import numpy as np

from app.ml.monte_carlo import simulate_returns


def test_monte_carlo_is_reproducible():
    returns = np.array([0.01, -0.005, 0.008, -0.002, 0.004])
    a = simulate_returns(returns, simulations=100, seed=7)
    b = simulate_returns(returns, simulations=100, seed=7)
    assert a == b
    assert a.simulations == 100


def test_monte_carlo_rejects_empty():
    try:
        simulate_returns(np.array([]))
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
