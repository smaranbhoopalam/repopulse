"""
Weight profiles for the multi-domain scoring engine.

Each profile is a dict of domain -> weight (must sum to 1.0).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class WeightProfile:
    name: str
    architecture: float = 0.30
    complexity: float = 0.20
    dependency: float = 0.20
    evolution: float = 0.15
    team: float = 0.10
    testing: float = 0.05

    def to_dict(self) -> Dict[str, float]:
        return {
            "architecture": self.architecture,
            "complexity": self.complexity,
            "dependency": self.dependency,
            "evolution": self.evolution,
            "team": self.team,
            "testing": self.testing,
        }


PROFILES: Dict[str, WeightProfile] = {
    "default": WeightProfile("default"),
    "enterprise": WeightProfile(
        "enterprise",
        architecture=0.35,
        complexity=0.15,
        dependency=0.20,
        evolution=0.15,
        team=0.10,
        testing=0.05,
    ),
    "startup": WeightProfile(
        "startup",
        architecture=0.20,
        complexity=0.25,
        dependency=0.20,
        evolution=0.20,
        team=0.05,
        testing=0.10,
    ),
    "library": WeightProfile(
        "library",
        architecture=0.25,
        complexity=0.25,
        dependency=0.25,
        evolution=0.10,
        team=0.05,
        testing=0.10,
    ),
    "microservice": WeightProfile(
        "microservice",
        architecture=0.40,
        complexity=0.15,
        dependency=0.25,
        evolution=0.10,
        team=0.05,
        testing=0.05,
    ),
}
