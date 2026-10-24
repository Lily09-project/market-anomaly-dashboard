"""Gaussian hidden Markov model fitted by Baum-Welch, decoded by Viterbi.

The forward-backward pass is scaled (each step normalised) so long series do
not underflow. Several seeded initialisations are tried and the one with the
highest log-likelihood is kept. States are finally ordered by volatility so
"state 0" always means the calmest regime.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

import numpy as np

MIN_VARIANCE = 1e-10


@dataclass
class HMMResult:
    means: np.ndarray
    variances: np.ndarray
    transition: np.ndarray
    initial: np.ndarray
    log_likelihood: float
    history: list[float] = field(default_factory=list)

    @property
    def expected_durations(self) -> np.ndarray:
        stay = np.clip(np.diag(self.transition), 0.0, 1 - 1e-12)
        return 1.0 / (1.0 - stay)


def _emission(x: np.ndarray, means: np.ndarray, variances: np.ndarray) -> np.ndarray:
    """Gaussian densities; a missing observation (NaN) is equally likely under every state."""
    diff = x[:, None] - means[None, :]
    density = np.exp(-0.5 * diff**2 / variances[None, :]) / np.sqrt(2 * math.pi * variances[None, :])
    return np.where(np.isnan(x)[:, None], 1.0, density)


def _forward_backward(x: np.ndarray, means: np.ndarray, variances: np.ndarray, transition: np.ndarray, initial: np.ndarray):
    n, k = len(x), len(means)
    b = np.maximum(_emission(x, means, variances), 1e-300)
    alpha = np.empty((n, k))
    scale = np.empty(n)
    alpha[0] = initial * b[0]
    scale[0] = alpha[0].sum()
    alpha[0] /= scale[0]
    for t in range(1, n):
        alpha[t] = (alpha[t - 1] @ transition) * b[t]
        scale[t] = alpha[t].sum()
        alpha[t] /= scale[t]
    beta = np.empty((n, k))
    beta[-1] = 1.0
    for t in range(n - 2, -1, -1):
        beta[t] = (transition @ (b[t + 1] * beta[t + 1])) / scale[t + 1]
    gamma = alpha * beta
    gamma /= gamma.sum(axis=1, keepdims=True)
    xi_sum = np.zeros((k, k))
    for t in range(n - 1):
        xi = alpha[t][:, None] * transition * (b[t + 1] * beta[t + 1])[None, :] / scale[t + 1]
        xi_sum += xi
    return gamma, xi_sum, float(np.log(scale).sum())


def _initial_guess(x: np.ndarray, k: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Seed states from quantiles of a 20-day rolling volatility, with random jitter.

    Regimes persist, so grouping days by local volatility starts EM near the
    persistent solution instead of one that merely splits the calm days by |x|.
    """
    filled = np.where(np.isnan(x), 0.0, x)
    window = 20
    kernel = np.ones(window) / window
    local_var = np.convolve(filled**2, kernel, mode="same")
    edges = np.quantile(local_var, np.linspace(0, 1, k + 1)[1:-1] + rng.uniform(-0.05, 0.05, k - 1))
    groups = np.searchsorted(np.sort(edges), local_var)
    observed = ~np.isnan(x)
    means = np.empty(k)
    variances = np.empty(k)
    for state in range(k):
        members = x[(groups == state) & observed]
        if members.size < 2:
            members = x[observed]
        means[state] = members.mean()
        variances[state] = max(members.var(), MIN_VARIANCE)
    stay = rng.uniform(0.9, 0.99, k)
    transition = np.empty((k, k))
    for i in range(k):
        transition[i] = (1 - stay[i]) / (k - 1)
        transition[i, i] = stay[i]
    return means, variances, transition, np.full(k, 1.0 / k)


def fit(x: np.ndarray, k: int = 3, n_init: int = 4, max_iter: int = 200, tol: float = 1e-6, seed: int = 0) -> HMMResult:
    x = np.asarray(x, dtype=float)
    if x.ndim != 1 or int((~np.isnan(x)).sum()) < 10 * k:
        raise ValueError("need a 1-D series with at least 10 observations per state")
    observed = ~np.isnan(x)
    xo = x[observed]
    rng = np.random.default_rng(seed)
    best: HMMResult | None = None
    for _ in range(n_init):
        means, variances, transition, initial = _initial_guess(x, k, rng)
        history: list[float] = []
        for _ in range(max_iter):
            gamma, xi_sum, ll = _forward_backward(x, means, variances, transition, initial)
            history.append(ll)
            # Missing days inform the state path but not the emission parameters.
            g = gamma[observed]
            weights = g.sum(axis=0)
            means = (g * xo[:, None]).sum(axis=0) / weights
            variances = np.maximum((g * (xo[:, None] - means[None, :]) ** 2).sum(axis=0) / weights, MIN_VARIANCE)
            transition = xi_sum / xi_sum.sum(axis=1, keepdims=True)
            initial = gamma[0]
            if len(history) > 1 and abs(history[-1] - history[-2]) < tol * max(1.0, abs(history[-2])):
                break
        _, _, ll = _forward_backward(x, means, variances, transition, initial)
        history.append(ll)
        if best is None or ll > best.log_likelihood:
            best = HMMResult(means, variances, transition, initial, ll, history)
    if best is None:
        raise ValueError("n_init must be at least 1")
    return _order_by_volatility(best)


def _order_by_volatility(result: HMMResult) -> HMMResult:
    order = np.argsort(result.variances)
    return HMMResult(
        means=result.means[order],
        variances=result.variances[order],
        transition=result.transition[np.ix_(order, order)],
        initial=result.initial[order],
        log_likelihood=result.log_likelihood,
        history=result.history,
    )


def viterbi(x: np.ndarray, result: HMMResult) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    n, k = len(x), len(result.means)
    log_b = np.log(np.maximum(_emission(x, result.means, result.variances), 1e-300))
    log_a = np.log(np.maximum(result.transition, 1e-300))
    delta = np.log(np.maximum(result.initial, 1e-300)) + log_b[0]
    back = np.zeros((n, k), dtype=int)
    for t in range(1, n):
        scores = delta[:, None] + log_a
        back[t] = np.argmax(scores, axis=0)
        delta = scores[back[t], np.arange(k)] + log_b[t]
    path = np.empty(n, dtype=int)
    path[-1] = int(np.argmax(delta))
    for t in range(n - 1, 0, -1):
        path[t - 1] = back[t, path[t]]
    return path


def posterior(x: np.ndarray, result: HMMResult) -> np.ndarray:
    gamma, _, _ = _forward_backward(np.asarray(x, dtype=float), result.means, result.variances, result.transition, result.initial)
    return gamma


def aligned_accuracy(predicted: np.ndarray, truth: np.ndarray, k: int) -> tuple[float, tuple[int, ...]]:
    """Best accuracy over all relabelings of the predicted states (labels are arbitrary)."""
    best = (-1.0, tuple(range(k)))
    for perm in itertools.permutations(range(k)):
        mapped = np.array(perm)[predicted]
        accuracy = float(np.mean(mapped == truth))
        if accuracy > best[0]:
            best = (accuracy, perm)
    return best


def predictive_z(x: np.ndarray, result: HMMResult) -> np.ndarray:
    """z-score of each observation under the one-step-ahead state mixture.

    Uses the filtered state probabilities up to t-1 only, so a day is judged
    against the regime the market was in, without peeking at that day.
    Missing observations get NaN.
    """
    x = np.asarray(x, dtype=float)
    n, k = len(x), len(result.means)
    b = np.maximum(_emission(x, result.means, result.variances), 1e-300)
    filtered = result.initial.copy()
    z = np.full(n, np.nan)
    for t in range(n):
        predicted = filtered if t == 0 else filtered @ result.transition
        mean = float(predicted @ result.means)
        variance = float(predicted @ (result.variances + result.means**2)) - mean**2
        if not np.isnan(x[t]):
            z[t] = (x[t] - mean) / math.sqrt(max(variance, MIN_VARIANCE))
        filtered = predicted * b[t]
        filtered /= filtered.sum()
    return z
