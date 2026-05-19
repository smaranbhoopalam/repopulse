"""
DriftEngine — Detects macro-structural drift across consecutive commit snapshots.

Capabilities
------------
* Computes metric deltas (score drop, node/edge growth, violation change).
* Detects **Dependency Explosions** — sudden uncharacteristic growth of
  import edges relative to the previous snapshot.
* Issues a **Crash Alert** when the health score collapses by ≥ N points
  in a single commit transition.
* Tracks a rolling history of snapshots for trend analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Drift report dataclass
# ---------------------------------------------------------------------------

@dataclass
class DriftReport:
    """Structured result of a drift analysis between two commit snapshots."""

    # --- Alert flags ---
    crash_alert: bool
    dependency_explosion: bool

    # --- Top-level signals ---
    score_drop: float           # positive = degradation
    edge_growth_ratio: float    # (curr_edges - prev_edges) / prev_edges

    # --- Fine-grained deltas ---
    deltas: Dict[str, Any] = field(default_factory=dict)

    # --- Trend data ---
    commit_sha: Optional[str] = None
    previous_commit_sha: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "crash_alert": self.crash_alert,
            "dependency_explosion": self.dependency_explosion,
            "score_drop": self.score_drop,
            "edge_growth_ratio": self.edge_growth_ratio,
            "deltas": self.deltas,
            "commit_sha": self.commit_sha,
            "previous_commit_sha": self.previous_commit_sha,
        }

    def has_alerts(self) -> bool:
        """Return True if any critical alert flag is set."""
        return self.crash_alert or self.dependency_explosion


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class DriftEngine:
    """
    Compare consecutive architectural snapshots to detect structural drift.

    Parameters
    ----------
    crash_threshold:
        Minimum score drop (in points) to trigger a ``crash_alert``
        (default: 15.0).
    explosion_threshold:
        Minimum edge growth ratio to trigger ``dependency_explosion``
        (default: 0.20, i.e. 20% edge growth in one commit).
    history_limit:
        Maximum number of past snapshots retained for trend analysis.
    """

    def __init__(
        self,
        crash_threshold: float = 15.0,
        explosion_threshold: float = 0.20,
        history_limit: int = 100,
    ) -> None:
        self.crash_threshold = crash_threshold
        self.explosion_threshold = explosion_threshold
        self._history: List[Dict[str, Any]] = []
        self._history_limit = history_limit

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_drift(
        self,
        previous_metrics: Dict[str, Any],
        current_metrics: Dict[str, Any],
        current_commit: Optional[str] = None,
        previous_commit: Optional[str] = None,
    ) -> DriftReport:
        """
        Compare two metric snapshots and produce a ``DriftReport``.

        Parameters
        ----------
        previous_metrics:
            ``ArchitectureMetrics.to_dict()`` output from the prior commit.
        current_metrics:
            ``ArchitectureMetrics.to_dict()`` output from the current commit.
        current_commit:
            Optional SHA of the current commit for reporting.
        previous_commit:
            Optional SHA of the previous commit for reporting.

        Returns
        -------
        DriftReport
        """
        if not previous_metrics or not current_metrics:
            return self._empty_report(current_commit, previous_commit)

        prev_score = float(previous_metrics.get("score", 100.0))
        curr_score = float(current_metrics.get("score", 100.0))
        score_drop = round(prev_score - curr_score, 2)

        prev_edges = int(previous_metrics.get("edges", 0))
        curr_edges = int(current_metrics.get("edges", 0))

        if prev_edges > 0:
            edge_growth_ratio = (curr_edges - prev_edges) / prev_edges
        elif curr_edges > 0:
            edge_growth_ratio = 1.0
        else:
            edge_growth_ratio = 0.0

        crash_alert = score_drop >= self.crash_threshold
        dependency_explosion = edge_growth_ratio >= self.explosion_threshold

        deltas = {
            "score_delta": round(curr_score - prev_score, 2),
            "violations_delta": (
                current_metrics.get("violations_count", 0)
                - previous_metrics.get("violations_count", 0)
            ),
            "scc_delta": (
                current_metrics.get("scc_count", 0)
                - previous_metrics.get("scc_count", 0)
            ),
            "edges_delta": curr_edges - prev_edges,
            "nodes_delta": (
                current_metrics.get("nodes", 0)
                - previous_metrics.get("nodes", 0)
            ),
            "avg_out_degree_delta": round(
                current_metrics.get("avg_out_degree", 0.0)
                - previous_metrics.get("avg_out_degree", 0.0),
                4,
            ),
        }

        report = DriftReport(
            crash_alert=crash_alert,
            dependency_explosion=dependency_explosion,
            score_drop=score_drop,
            edge_growth_ratio=round(edge_growth_ratio, 4),
            deltas=deltas,
            commit_sha=current_commit,
            previous_commit_sha=previous_commit,
        )

        # Maintain rolling history for trend analysis
        self._push_history(current_metrics, current_commit)

        return report

    def score_trend(self) -> List[float]:
        """Return the ordered list of health scores from the rolling history."""
        return [snap["score"] for snap in self._history]

    def is_trending_down(self, window: int = 5) -> bool:
        """
        Return True if the score has been monotonically decreasing over the
        last *window* snapshots (leading-edge regression detection).
        """
        trend = self.score_trend()[-window:]
        return len(trend) >= 2 and all(
            trend[i] > trend[i + 1] for i in range(len(trend) - 1)
        )

    def clear_history(self) -> None:
        """Reset the rolling snapshot history."""
        self._history.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _push_history(self, metrics: Dict[str, Any], sha: Optional[str]) -> None:
        entry = dict(metrics)
        entry["commit_sha"] = sha
        self._history.append(entry)
        if len(self._history) > self._history_limit:
            self._history.pop(0)

    @staticmethod
    def _empty_report(
        current_commit: Optional[str], previous_commit: Optional[str]
    ) -> DriftReport:
        return DriftReport(
            crash_alert=False,
            dependency_explosion=False,
            score_drop=0.0,
            edge_growth_ratio=0.0,
            deltas={},
            commit_sha=current_commit,
            previous_commit_sha=previous_commit,
        )
