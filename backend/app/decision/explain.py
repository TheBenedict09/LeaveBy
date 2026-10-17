"""Deterministic template explanations (blueprint F8). Every number comes from the Decision, so nothing can drift."""

from dataclasses import dataclass

from app.decision.engine import Decision, OptionResult

SUBJECT = {"walk": "Walking", "bike": "Cycling", "drive": "Driving", "train": "The train"}
OBJECT = {"walk": "walking", "bike": "cycling", "drive": "driving", "train": "the train"}
CRITERION = {"time": "time", "cost": "cost", "carbon": "carbon", "accessibility": "easy access"}


@dataclass(frozen=True)
class Explanation:
    because: list[str]
    tradeoffs: list[str]
    flip_points: list[str]
    hedge: str | None


def _tradeoff(win: OptionResult, other: OptionResult) -> str:
    dc = other.facts.cost_gbp - win.facts.cost_gbp
    de = other.facts.co2e_kg - win.facts.co2e_kg
    cost = f"costs £{abs(dc):.2f} {'more' if dc > 0 else 'less'}" if abs(dc) >= 0.005 else "costs about the same"
    co2 = f"{abs(de):.1f} kg {'more' if de > 0 else 'less'} CO2e" if abs(de) >= 0.05 else "about the same CO2e"
    return f"{SUBJECT[other.mode]} {cost} and emits {co2} than {OBJECT[win.mode]}."


def explain(decision: Decision) -> Explanation:
    pct = round(decision.confidence * 100)
    win = decision.winner
    if win is None:
        return Explanation([f"No option reaches {pct}% confidence by the deadline."], [], [], None)

    buffer_min = round(win.summary.journey_at_risk_min)
    because = [f"{SUBJECT[win.mode]} meets {pct}% confidence with a {buffer_min} minute buffer."]
    others = [o for o in decision.options if o.feasible and o is not win]
    tradeoffs = [_tradeoff(win, o) for o in others]
    flips = [
        f"If {CRITERION[f.criterion]} counted for {f.to_weight:.0%} instead of {f.from_weight:.0%}, "
        f"{OBJECT[f.mode]} would win."
        for f in decision.flips
    ]
    hedge = None
    if decision.hedge is not None:
        h = decision.hedge
        if h.both_late_scenarios == 0:
            hedge = (
                f"{SUBJECT[h.backup_mode]} is the backup: it was never late on the same morning "
                f"in {h.total_scenarios} scenarios."
            )
        else:
            hedge = (
                f"{SUBJECT[h.backup_mode]} is the backup: both plans are late together in "
                f"{h.both_late_scenarios} of {h.total_scenarios} scenarios."
            )
    return Explanation(because, tradeoffs, flips, hedge)
