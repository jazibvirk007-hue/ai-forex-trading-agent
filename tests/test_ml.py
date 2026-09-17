import pandas as pd
import pytest

from app.ml.walk_forward import make_folds


def test_walk_forward_is_chronological():
    frame = pd.DataFrame({"x": range(100)})
    folds = make_folds(frame, 50, 20, 10, step=10)
    assert folds
    for fold in folds:
        assert max(fold.train) < min(fold.validation)
        assert max(fold.validation) < min(fold.test)


def test_invalid_fold_size():
    with pytest.raises(ValueError):
        make_folds(pd.DataFrame({"x": range(10)}), 0, 2, 2)
