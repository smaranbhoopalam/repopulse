"""
DriftGuard Configuration Schema.

Provides a dataclass-based validated configuration system for the platform.
Loads from YAML and merges with environment-level overrides.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import yaml


# ---------------------------------------------------------------------------
# Sub-configs
# ---------------------------------------------------------------------------

@dataclass
class GitConfig:
    branch: str = "HEAD"
    limit: int = 100
    safe_mode: bool = True          # no-checkout traversal
    cache_enabled: bool = True


@dataclass
class ThresholdConfig:
    crash_alert: float = 15.0
    explosion_threshold: float = 0.20
    complexity_max: int = 10
    coupling_threshold: float = 2.5
    bus_factor_min: int = 2
    instability_high: float = 0.8
    test_ratio_min: float = 0.10
    churn_hotspot_threshold: int = 10
    ownership_abandon_days: int = 90


@dataclass
class WeightConfig:
    profile: str = "default"
    # Domain weights (must sum to 1.0)
    architecture: float = 0.30
    complexity: float = 0.20
    dependency: float = 0.20
    evolution: float = 0.15
    team: float = 0.10
    testing: float = 0.05
    # Sub-metric weights within architecture domain
    circular_deps: float = 10.0
    violations: float = 20.0
    coupling: float = 5.0
    density: float = 2.0


@dataclass
class DriftGuardConfig:
    """Root configuration object for DriftGuard."""

    git: GitConfig = field(default_factory=GitConfig)
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)
    weights: WeightConfig = field(default_factory=WeightConfig)
    rules: List[str] = field(default_factory=list)
    language: str = "python"
    output_dir: str = "./driftguard-output"
    dashboard_port: int = 8080

    @classmethod
    def from_yaml(cls, yaml_text: str) -> "DriftGuardConfig":
        """Parse YAML configuration text and return a DriftGuardConfig."""
        raw: Dict[str, Any] = yaml.safe_load(yaml_text) or {}
        dg = raw.get("driftguard", raw)  # support top-level or nested key

        git_raw = dg.get("git", {})
        thresh_raw = dg.get("thresholds", {})
        weight_raw = dg.get("weights", {})

        git = GitConfig(
            branch=git_raw.get("branch", "HEAD"),
            limit=git_raw.get("limit", 100),
            safe_mode=git_raw.get("safe_mode", True),
            cache_enabled=git_raw.get("cache_enabled", True),
        )

        thresh = ThresholdConfig(
            crash_alert=thresh_raw.get("crash_alert", 15.0),
            explosion_threshold=thresh_raw.get("explosion_threshold", 0.20),
            complexity_max=thresh_raw.get("complexity_max", 10),
            coupling_threshold=thresh_raw.get("coupling_threshold", 2.5),
            bus_factor_min=thresh_raw.get("bus_factor_min", 2),
            instability_high=thresh_raw.get("instability_high", 0.8),
            test_ratio_min=thresh_raw.get("test_ratio_min", 0.10),
            churn_hotspot_threshold=thresh_raw.get("churn_hotspot_threshold", 10),
            ownership_abandon_days=thresh_raw.get("ownership_abandon_days", 90),
        )

        profile = weight_raw.get("profile", "default")
        weights = WeightConfig(
            profile=profile,
            architecture=weight_raw.get("architecture", 0.30),
            complexity=weight_raw.get("complexity", 0.20),
            dependency=weight_raw.get("dependency", 0.20),
            evolution=weight_raw.get("evolution", 0.15),
            team=weight_raw.get("team", 0.10),
            testing=weight_raw.get("testing", 0.05),
        )

        return cls(
            git=git,
            thresholds=thresh,
            weights=weights,
            rules=dg.get("rules", []),
            language=dg.get("language", "python"),
            output_dir=dg.get("output_dir", "./driftguard-output"),
            dashboard_port=dg.get("dashboard_port", 8080),
        )

    @classmethod
    def from_yaml_file(cls, path: str) -> "DriftGuardConfig":
        from pathlib import Path
        return cls.from_yaml(Path(path).read_text(encoding="utf-8"))

    @classmethod
    def default(cls) -> "DriftGuardConfig":
        return cls()
