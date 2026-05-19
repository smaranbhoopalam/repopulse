"""
ScoringEngine — Multi-domain weighted health scoring.

Combines sub-scores from all metric domains into a single
Repository Health Score ∈ [0, 100].

Formula:
    Health Score = Σ(domain_weight × domain_sub_score)

Each domain sub-score is independently normalized to [0, 100].
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from driftguard.scoring.weights import WeightProfile, PROFILES


@dataclass
class HealthReport:
    """Full health report with per-domain breakdown."""
    overall_score: float
    architecture_score: float
    complexity_score: float
    dependency_score: float
    evolution_score: float
    team_score: float
    testing_score: float
    profile_name: str
    domain_weights: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_score": round(self.overall_score, 2),
            "architecture_score": round(self.architecture_score, 2),
            "complexity_score": round(self.complexity_score, 2),
            "dependency_score": round(self.dependency_score, 2),
            "evolution_score": round(self.evolution_score, 2),
            "team_score": round(self.team_score, 2),
            "testing_score": round(self.testing_score, 2),
            "profile": self.profile_name,
            "weights": self.domain_weights,
        }

    @property
    def grade(self) -> str:
        s = self.overall_score
        if s >= 90:
            return "A"
        elif s >= 80:
            return "B"
        elif s >= 70:
            return "C"
        elif s >= 60:
            return "D"
        else:
            return "F"

    @property
    def status_label(self) -> str:
        s = self.overall_score
        if s >= 85:
            return "HEALTHY"
        elif s >= 70:
            return "STABLE"
        elif s >= 55:
            return "AT RISK"
        elif s >= 40:
            return "DEGRADING"
        else:
            return "CRITICAL"


class ScoringEngine:
    """
    Combine sub-scores from all metric domains into a final health score.

    Parameters
    ----------
    profile:
        Name of the weight profile to use (default "default").
    custom_profile:
        Optional WeightProfile override.
    """

    def __init__(
        self,
        profile: str = "default",
        custom_profile: Optional[WeightProfile] = None,
    ) -> None:
        self.profile = custom_profile or PROFILES.get(profile, PROFILES["default"])

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute(
        self,
        architecture_score: float,
        complexity_score: float,
        dependency_score: float,
        evolution_score: float = 100.0,
        team_score: float = 100.0,
        testing_score: float = 100.0,
    ) -> HealthReport:
        """
        Compute overall health score from domain sub-scores.

        All input scores should be in [0, 100]. Missing domains default to
        100.0 (no penalty) so the engine works even when only some domains
        are available.
        """
        p = self.profile

        overall = (
            p.architecture * architecture_score
            + p.complexity * complexity_score
            + p.dependency * dependency_score
            + p.evolution * evolution_score
            + p.team * team_score
            + p.testing * testing_score
        )
        overall = round(max(0.0, min(100.0, overall)), 2)

        return HealthReport(
            overall_score=overall,
            architecture_score=round(architecture_score, 2),
            complexity_score=round(complexity_score, 2),
            dependency_score=round(dependency_score, 2),
            evolution_score=round(evolution_score, 2),
            team_score=round(team_score, 2),
            testing_score=round(testing_score, 2),
            profile_name=self.profile.name,
            domain_weights=self.profile.to_dict(),
        )

    def compute_from_metrics(
        self,
        architecture_metrics: Any,
        complexity_metrics: Optional[Any] = None,
        dependency_metrics: Optional[Any] = None,
        evolution_metrics: Optional[Any] = None,
        team_metrics: Optional[Any] = None,
        testing_metrics: Optional[Any] = None,
    ) -> HealthReport:
        """
        Convenience wrapper — accepts metric objects with a `sub_score` attribute.
        Falls back to 100.0 for absent domains.
        """
        def _score(m: Optional[Any], fallback: float = 100.0) -> float:
            if m is None:
                return fallback
            return float(getattr(m, "sub_score", fallback))

        # Architecture sub-score: derive from ArchitectureMetrics.score
        arch_score = float(getattr(architecture_metrics, "score", 100.0))

        return self.compute(
            architecture_score=arch_score,
            complexity_score=_score(complexity_metrics),
            dependency_score=_score(dependency_metrics),
            evolution_score=_score(evolution_metrics),
            team_score=_score(team_metrics),
            testing_score=_score(testing_metrics),
        )
