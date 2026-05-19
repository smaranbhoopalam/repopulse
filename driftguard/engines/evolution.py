"""
EvolutionEngine — Git history-based repository evolution metrics.

Computes (from pre-extracted churn data):
  - Commit risk score
  - Hotspot files (frequency × recency weighted)
  - Churn analysis
  - Volatile modules
  - Ownership fragmentation (HHI)
  - Refactor frequency heuristic
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FileChurnRecord:
    """Churn data for a single file across the analysed commit range."""
    path: str
    module_id: str
    commit_count: int
    additions: int
    deletions: int
    authors: Dict[str, int]          # author -> commit count
    last_modified_ts: float          # unix timestamp
    is_test_file: bool = False

    @property
    def churn_score(self) -> float:
        """Weighted churn: edits × log(changes+1)."""
        total_changes = self.additions + self.deletions
        return self.commit_count * math.log1p(total_changes)

    @property
    def ownership_hhi(self) -> float:
        """
        Herfindahl–Hirschman Index of author concentration.
        HHI = Σ(share²); 1.0 = single owner, approaches 0 = dispersed.
        """
        total = sum(self.authors.values())
        if total == 0:
            return 0.0
        return sum((count / total) ** 2 for count in self.authors.values())

    @property
    def dominant_author(self) -> Optional[str]:
        if not self.authors:
            return None
        return max(self.authors, key=self.authors.__getitem__)


@dataclass
class EvolutionMetrics:
    """Aggregate repository evolution metrics for a snapshot."""
    hotspot_count: int               # files with churn_score above threshold
    volatile_module_count: int       # high churn, low coverage
    avg_ownership_hhi: float         # repo-wide ownership concentration
    bus_factor: int                  # number of authors holding >50% ownership
    commit_risk_score: float         # aggregate risk from last N commits
    total_churn: int                 # total lines changed
    refactor_frequency: float        # proportion of commits with "refactor" heuristics
    hotspots: List[str] = field(default_factory=list)
    sub_score: float = 100.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hotspot_count": self.hotspot_count,
            "volatile_module_count": self.volatile_module_count,
            "avg_ownership_hhi": round(self.avg_ownership_hhi, 4),
            "bus_factor": self.bus_factor,
            "commit_risk_score": round(self.commit_risk_score, 2),
            "total_churn": self.total_churn,
            "refactor_frequency": round(self.refactor_frequency, 4),
            "hotspots": self.hotspots[:10],
            "sub_score": round(self.sub_score, 2),
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class EvolutionEngine:
    """
    Compute evolution metrics from file churn records.

    Parameters
    ----------
    hotspot_threshold:
        Churn score above which a file is a "hotspot" (default 10).
    ownership_abandon_days:
        Days since last commit to flag abandoned ownership (default 90).
    """

    def __init__(
        self,
        hotspot_threshold: float = 10.0,
        ownership_abandon_days: int = 90,
    ) -> None:
        self.hotspot_threshold = hotspot_threshold
        self.ownership_abandon_days = ownership_abandon_days

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyse(
        self,
        churn_records: List[FileChurnRecord],
        commit_messages: Optional[List[str]] = None,
    ) -> EvolutionMetrics:
        """Compute evolution metrics from pre-extracted churn data."""
        if not churn_records:
            return self._empty_metrics()

        hotspots = self._identify_hotspots(churn_records)
        volatile = self._volatile_modules(churn_records)
        avg_hhi = self._avg_hhi(churn_records)
        bus_factor = self._bus_factor(churn_records)
        commit_risk = self._commit_risk_score(churn_records)
        total_churn = sum(r.additions + r.deletions for r in churn_records)
        refactor_freq = self._refactor_frequency(commit_messages or [])

        # Sub-score
        sub = 100.0
        sub -= len(hotspots) * 3.0
        sub -= len(volatile) * 4.0
        sub -= max(0, avg_hhi - 0.5) * 20.0    # ownership concentration penalty
        sub -= max(0, 3 - bus_factor) * 10.0   # bus factor below 3 is risky
        sub -= min(30, commit_risk * 2.0)
        sub = round(max(0.0, min(100.0, sub)), 2)

        return EvolutionMetrics(
            hotspot_count=len(hotspots),
            volatile_module_count=len(volatile),
            avg_ownership_hhi=avg_hhi,
            bus_factor=bus_factor,
            commit_risk_score=commit_risk,
            total_churn=total_churn,
            refactor_frequency=refactor_freq,
            hotspots=[r.module_id for r in hotspots[:10]],
            sub_score=sub,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _identify_hotspots(
        self, records: List[FileChurnRecord]
    ) -> List[FileChurnRecord]:
        return [r for r in records if r.churn_score > self.hotspot_threshold]

    def _volatile_modules(
        self, records: List[FileChurnRecord]
    ) -> List[FileChurnRecord]:
        """High churn + not a test file (proxy for no coverage)."""
        median_churn = sorted(r.churn_score for r in records)
        if not median_churn:
            return []
        mid = median_churn[len(median_churn) // 2]
        return [r for r in records if r.churn_score > mid and not r.is_test_file]

    def _avg_hhi(self, records: List[FileChurnRecord]) -> float:
        hhis = [r.ownership_hhi for r in records]
        return sum(hhis) / len(hhis) if hhis else 0.0

    def _bus_factor(self, records: List[FileChurnRecord]) -> int:
        """
        Number of authors required to cover >50% of file ownership.
        Uses a greedy coverage approach.
        """
        # Tally unique files per author
        author_files: Dict[str, set] = {}
        for rec in records:
            dom = rec.dominant_author
            if dom:
                author_files.setdefault(dom, set()).add(rec.path)

        total_files = len(records)
        if total_files == 0 or not author_files:
            return 1

        sorted_authors = sorted(
            author_files.items(), key=lambda x: len(x[1]), reverse=True
        )
        covered = set()
        bus_count = 0
        for author, files in sorted_authors:
            covered |= files
            bus_count += 1
            if len(covered) / total_files >= 0.5:
                break
        return bus_count

    def _commit_risk_score(self, records: List[FileChurnRecord]) -> float:
        """Aggregate risk: sum of churn_score × (1 - hhi) for all records."""
        total = 0.0
        for rec in records:
            fragmentation = 1.0 - rec.ownership_hhi
            total += rec.churn_score * (1 + fragmentation)
        return round(min(100.0, total / max(len(records), 1)), 2)

    def _refactor_frequency(self, messages: List[str]) -> float:
        """Proportion of commit messages matching refactor heuristics."""
        if not messages:
            return 0.0
        keywords = {"refactor", "cleanup", "clean up", "restructure", "reorganize", "extract"}
        matches = sum(
            1 for msg in messages
            if any(kw in msg.lower() for kw in keywords)
        )
        return matches / len(messages)

    @staticmethod
    def _empty_metrics() -> EvolutionMetrics:
        return EvolutionMetrics(
            hotspot_count=0,
            volatile_module_count=0,
            avg_ownership_hhi=0.0,
            bus_factor=1,
            commit_risk_score=0.0,
            total_churn=0,
            refactor_frequency=0.0,
            hotspots=[],
            sub_score=100.0,
        )
