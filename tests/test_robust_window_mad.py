import numpy as np
import pandas as pd
import pytest

from src.analytics.events import MAD_TO_SD, robust_z


def test_robust_z_uses_one_shared_center_for_each_historical_window():
    series = pd.Series([0.0, 1.0, 4.0, 9.0, 16.0, 25.0, 36.0, 49.0])
    scores = robust_z(series, lookback=6)
    previous = series.iloc[:6].to_numpy()
    center = np.median(previous)
    scale = np.median(np.abs(previous - center)) * MAD_TO_SD
    assert scores.iloc[6] == pytest.approx((36.0 - center) / scale)


def test_robust_z_ignores_current_and_future_values_in_its_baseline():
    series = pd.Series([0.0, 1.0, 4.0, 9.0, 16.0, 25.0, 36.0, 49.0])
    altered = series.copy()
    altered.iloc[7] = 1e6
    pd.testing.assert_series_equal(robust_z(series, lookback=6).iloc[:7], robust_z(altered, lookback=6).iloc[:7])
    assert np.isnan(robust_z(pd.Series([2.0] * 8), lookback=6).iloc[-1])
