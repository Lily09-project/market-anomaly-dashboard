from __future__ import annotations

import numpy as np

from src import export_web


def test_future_perturbations_do_not_change_scored_prefix_or_states():
    rng = np.random.default_rng(29)
    values = rng.normal(0, 0.01, 650)
    values[400] = -0.15
    changed = values.copy()
    changed[501:] = rng.normal(0.05, 0.15, len(changed)-501)
    original_z, original_states = export_web.causal_event_scores(values)
    changed_z, changed_states = export_web.causal_event_scores(changed)
    prefix_z, prefix_states = export_web.causal_event_scores(values[:501])
    np.testing.assert_allclose(original_z[:501], changed_z[:501], equal_nan=True)
    np.testing.assert_allclose(original_z[:501], prefix_z, equal_nan=True)
    np.testing.assert_array_equal(original_states[:501], changed_states[:501])
    np.testing.assert_array_equal(original_states[:501], prefix_states)
    assert np.isnan(original_z[:252]).all()
    assert original_z[400] < -export_web.EVENT_Z


def test_insufficient_calibration_has_no_events():
    z, states = export_web.causal_event_scores(np.ones(200)*0.001)
    assert np.isnan(z).all()
    assert len(states) == 200
