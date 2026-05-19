"""
Predictor — Trend-aware architectural collapse forecasting.

Uses linear regression on rolling score windows to estimate:
  - Commits until score drops below critical threshold
  - Technical debt growth rate
  - Danger zone identification
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CollapseEstimate:
    """Forecast of architectural degradation trajectory."""
    is_declining: bool
    slope: float                    # points per commit (negative = declining)
    commits_to_critical: Optional[int]  # None if stable / already critical
    current_score: float
    projected_score_in_10: float    # projected score in 10 commits
    danger_zones: List[str]         # module IDs flagged as danger zones
    debt_growth_rate: float         # % churn increase per commit (approx)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_declining": self.is_declining,
            "slope": round(self.slope, 4),
            "commits_to_critical": self.commits_to_critical,
            "current_score": round(self.current_score, 2),
            "projected_score_in_10": round(self.projected_score_in_10, 2),
            "danger_zones": self.danger_zones[:10],
            "debt_growth_rate": round(self.debt_growth_rate, 4),
        }


class Predictor:
    """
    Forecast architectural health trajectory.

    Parameters
    ----------
    critical_threshold:
        Score below which the architecture is considered "collapsed" (default 60).
    window:
        Number of most-recent commits used for regression (default 10).
    """

    def __init__(
        self,
        critical_threshold: float = 60.0,
        window: int = 10,
    ) -> None:
        self.critical_threshold = critical_threshold
        self.window = window

    def forecast(
        self,
        score_history: List[float],
        hotspot_modules: Optional[List[str]] = None,
        churn_history: Optional[List[float]] = None,
    ) -> CollapseEstimate:
        """
        Produce a collapse estimate from a rolling score history.

        Parameters
        ----------
        score_history:
            Ordered list of health scores (oldest first).
        hotspot_modules:
            List of module IDs currently flagged as hotspots.
        churn_history:
            Ordered list of total churn values for debt growth estimation.
        """
        if len(score_history) < 2:
            curr = score_history[-1] if score_history else 100.0
            return CollapseEstimate(
                is_declining=False,
                slope=0.0,
                commits_to_critical=None,
                current_score=curr,
                projected_score_in_10=curr,
                danger_zones=hotspot_modules or [],
                debt_growth_rate=0.0,
            )

        recent = score_history[-self.window:]
        slope = self._linear_slope(recent)
        current = recent[-1]

        # Projected score in 10 commits
        projected = max(0.0, min(100.0, current + slope * 10))

        # Commits to critical
        commits_to_critical = None
        if slope < 0 and current > self.critical_threshold:
            pts_to_go = current - self.critical_threshold
            commits_to_critical = max(1, int(pts_to_go / abs(slope)))

        # Debt growth rate from churn history
        debt_rate = 0.0
        if churn_history and len(churn_history) >= 2:
            debt_rate = self._linear_slope(churn_history[-self.window:])

        return CollapseEstimate(
            is_declining=slope < -0.5,
            slope=slope,
            commits_to_critical=commits_to_critical,
            current_score=current,
            projected_score_in_10=projected,
            danger_zones=(hotspot_modules or [])[:10],
            debt_growth_rate=debt_rate,
        )

    @staticmethod
    def _linear_slope(values: List[float]) -> float:
        """Compute the slope of the best-fit line through *values*."""
        n = len(values)
        if n < 2:
            return 0.0
        xs = list(range(n))
        mean_x = sum(xs) / n
        mean_y = sum(values) / n
        numerator = sum((xs[i] - mean_x) * (values[i] - mean_y) for i in range(n))
        denominator = sum((xs[i] - mean_x) ** 2 for i in range(n))
        return numerator / denominator if denominator else 0.0
