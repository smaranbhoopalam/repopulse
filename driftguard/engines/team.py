"""
TeamEngine — Contributor-level risk metrics.

Computes:
  - Bus factor
  - Contributor concentration (HHI per module)
  - Abandoned modules
  - Inactive ownership detection
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TeamMetrics:
    bus_factor: int
    contributor_count: int
    abandoned_modules: List[str]
    inactive_owners: List[str]
    concentration_hhi: float
    sub_score: float = 100.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bus_factor": self.bus_factor,
            "contributor_count": self.contributor_count,
            "abandoned_modules": self.abandoned_modules[:10],
            "inactive_owners": self.inactive_owners[:10],
            "concentration_hhi": round(self.concentration_hhi, 4),
            "sub_score": round(self.sub_score, 2),
        }


class TeamEngine:
    """Compute team-health metrics from ownership and activity data."""

    def __init__(
        self,
        bus_factor_min: int = 2,
        abandon_days: int = 90,
    ) -> None:
        self.bus_factor_min = bus_factor_min
        self.abandon_days = abandon_days

    def analyse(
        self,
        ownership_map: Dict[str, str],             # file -> dominant_author
        last_commit_ts: Dict[str, float],          # file -> unix timestamp
        author_activity: Dict[str, float],         # author -> last commit ts
        contributor_count: int = 0,
    ) -> TeamMetrics:
        if not ownership_map:
            return TeamMetrics(
                bus_factor=1, contributor_count=contributor_count,
                abandoned_modules=[], inactive_owners=[],
                concentration_hhi=0.0, sub_score=100.0,
            )

        now = time.time()
        cutoff = now - self.abandon_days * 86400

        # Abandoned modules
        abandoned = [
            f for f, ts in last_commit_ts.items()
            if ts < cutoff
        ]

        # Inactive owners
        inactive = [
            author for author, ts in author_activity.items()
            if ts < cutoff
        ]

        # Bus factor — authors covering >50% of files
        author_file_count: Dict[str, int] = {}
        for auth in ownership_map.values():
            if auth:
                author_file_count[auth] = author_file_count.get(auth, 0) + 1

        total_files = len(ownership_map)
        sorted_authors = sorted(
            author_file_count.items(), key=lambda x: x[1], reverse=True
        )
        covered, bus = 0, 0
        for _, cnt in sorted_authors:
            covered += cnt
            bus += 1
            if covered / max(total_files, 1) >= 0.5:
                break

        # HHI
        shares = [cnt / max(total_files, 1) for cnt in author_file_count.values()]
        hhi = sum(s ** 2 for s in shares)

        # Sub-score
        sub = 100.0
        sub -= max(0, self.bus_factor_min - bus) * 15.0
        sub -= len(abandoned) * 2.0
        sub -= len(inactive) * 3.0
        sub -= max(0, hhi - 0.3) * 30.0
        sub = round(max(0.0, min(100.0, sub)), 2)

        return TeamMetrics(
            bus_factor=bus,
            contributor_count=contributor_count or len(author_file_count),
            abandoned_modules=abandoned[:20],
            inactive_owners=inactive[:10],
            concentration_hhi=hhi,
            sub_score=sub,
        )
