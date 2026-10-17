"""Normalise, weight, rank and explain-by-sensitivity (blueprint 5.6). Pure functions, no I/O."""

from dataclasses import dataclass

CRITERIA = ("time", "cost", "carbon", "accessibility")
LOWER_IS_BETTER = frozenset({"time", "cost", "carbon"})


@dataclass(frozen=True)
class FlipPoint:
    mode: str  # the option that would win
    criterion: str  # the weight that was raised
    from_weight: float
    to_weight: float


def normalise_weights(weights: dict[str, float]) -> dict[str, float]:
    w = {c: float(weights.get(c, 0.0)) for c in CRITERIA}
    if any(v < 0 for v in w.values()):
        raise ValueError("weights must not be negative")
    total = sum(w.values())
    if total <= 0:
        raise ValueError("at least one weight must be greater than 0")
    return {c: v / total for c, v in w.items()}


def normalise_criteria(raw: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    """raw[mode][criterion] -> [0, 1] where 1 is best among the given options. Ties on a criterion give everyone 1."""
    out: dict[str, dict[str, float]] = {m: {} for m in raw}
    for c in CRITERIA:
        vals = [raw[m][c] for m in raw]
        lo, hi = min(vals), max(vals)
        for m in raw:
            if hi - lo < 1e-12:
                out[m][c] = 1.0
            elif c in LOWER_IS_BETTER:
                out[m][c] = (hi - raw[m][c]) / (hi - lo)
            else:
                out[m][c] = (raw[m][c] - lo) / (hi - lo)
    return out


def composite(norm: dict[str, dict[str, float]], weights: dict[str, float]) -> dict[str, float]:
    return {m: sum(weights[c] * norm[m][c] for c in CRITERIA) for m in norm}


def rank_modes(scores: dict[str, float], p_on_time: dict[str, float], cost: dict[str, float]) -> list[str]:
    """Best first. Ties: higher P(on time), then lower cost, then name (so the order is deterministic)."""
    return sorted(scores, key=lambda m: (-round(scores[m], 9), -round(p_on_time[m], 9), cost[m], m))


def shifted_weights(w0: dict[str, float], criterion: str, x: float) -> dict[str, float]:
    """Set one weight to x and rescale the others so everything still sums to 1."""
    scale = (1.0 - x) / (1.0 - w0[criterion])
    return {k: (x if k == criterion else v * scale) for k, v in w0.items()}


def flip_points(
    norm: dict[str, dict[str, float]],
    weights: dict[str, float],
    p_on_time: dict[str, float],
    cost: dict[str, float],
    steps: int = 100,
) -> list[FlipPoint]:
    """For every other option, the smallest single-weight increase that would make it the winner.
    Options that never win (even with one criterion at 100%) are simply absent."""
    w0 = normalise_weights(weights)
    base = rank_modes(composite(norm, w0), p_on_time, cost)[0]
    best: dict[str, FlipPoint] = {}
    for crit in CRITERIA:
        if 1.0 - w0[crit] < 1e-9:
            continue
        seen: set[str] = set()
        for i in range(1, steps + 1):
            x = w0[crit] + (1.0 - w0[crit]) * i / steps
            winner = rank_modes(composite(norm, shifted_weights(w0, crit, x)), p_on_time, cost)[0]
            if winner == base or winner in seen:
                continue
            seen.add(winner)
            fp = FlipPoint(winner, crit, w0[crit], x)
            cur = best.get(winner)
            if cur is None or (fp.to_weight - fp.from_weight) < (cur.to_weight - cur.from_weight):
                best[winner] = fp
    return sorted(best.values(), key=lambda f: (f.to_weight - f.from_weight, f.mode))


def apply_flip(weights: dict[str, float], fp: FlipPoint) -> dict[str, float]:
    return shifted_weights(normalise_weights(weights), fp.criterion, fp.to_weight)
