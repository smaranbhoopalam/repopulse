"""
TestingEngine — Heuristic test infrastructure metrics.

Computes (without running a test runner):
  - Test-to-code line ratio
  - Test coverage trend (delta across commits)
  - Untested critical modules (high-centrality, no paired test)
  - Flaky test indicators (high-churn test files)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import networkx as nx


@dataclass
class TestingMetrics:
    test_to_code_ratio: float
    test_file_count: int
    source_file_count: int
    untested_critical_modules: List[str]
    flaky_test_indicators: List[str]
    coverage_trend_delta: float     # positive = improving
    sub_score: float = 100.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_to_code_ratio": round(self.test_to_code_ratio, 4),
            "test_file_count": self.test_file_count,
            "source_file_count": self.source_file_count,
            "untested_critical_modules": self.untested_critical_modules[:10],
            "flaky_test_indicators": self.flaky_test_indicators[:10],
            "coverage_trend_delta": round(self.coverage_trend_delta, 4),
            "sub_score": round(self.sub_score, 2),
        }


class TestingEngine:
    """
    Heuristic test quality metrics.

    Parameters
    ----------
    test_ratio_min:
        Minimum acceptable test-to-code ratio (default 0.10).
    flaky_churn_threshold:
        Commit count above which a test file may be flaky (default 8).
    """

    def __init__(
        self,
        test_ratio_min: float = 0.10,
        flaky_churn_threshold: int = 8,
    ) -> None:
        self.test_ratio_min = test_ratio_min
        self.flaky_churn_threshold = flaky_churn_threshold

    def analyse(
        self,
        root_dir: Optional[str],
        graph: Optional[nx.DiGraph] = None,
        churn_map: Optional[Dict[str, int]] = None,     # file -> commit_count
        previous_ratio: Optional[float] = None,
    ) -> TestingMetrics:
        """
        Parameters
        ----------
        root_dir:
            Repository root for scanning Python files.
        graph:
            Dependency graph — used for centrality-based untested detection.
        churn_map:
            file path -> commit count, used for flaky test detection.
        previous_ratio:
            Test ratio from the prior commit for trend calculation.
        """
        if root_dir is None:
            return self._empty_metrics()

        root = Path(root_dir).resolve()
        py_files = list(root.rglob("*.py"))

        test_files = [f for f in py_files if self._is_test(f)]
        src_files = [f for f in py_files if not self._is_test(f)]

        # Line counts
        test_lines = self._count_lines(test_files)
        src_lines = self._count_lines(src_files)
        ratio = (test_lines / max(src_lines, 1))

        # Untested critical modules
        untested = self._untested_critical(graph, test_files, root)

        # Flaky test indicators
        flaky = self._flaky_tests(test_files, churn_map or {})

        # Coverage trend
        trend_delta = ratio - (previous_ratio or ratio)

        # Sub-score
        sub = 100.0
        sub -= max(0, self.test_ratio_min - ratio) * 200.0   # big penalty for low ratio
        sub -= len(untested) * 5.0
        sub -= len(flaky) * 3.0
        sub = round(max(0.0, min(100.0, sub)), 2)

        return TestingMetrics(
            test_to_code_ratio=ratio,
            test_file_count=len(test_files),
            source_file_count=len(src_files),
            untested_critical_modules=untested,
            flaky_test_indicators=flaky,
            coverage_trend_delta=trend_delta,
            sub_score=sub,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_test(path: Path) -> bool:
        return (
            path.name.startswith("test_")
            or path.name.endswith("_test.py")
            or "tests" in path.parts
            or "test" in path.parts
        )

    @staticmethod
    def _count_lines(files: List[Path]) -> int:
        total = 0
        for f in files:
            try:
                total += len(f.read_text(encoding="utf-8", errors="ignore").splitlines())
            except Exception:
                pass
        return total

    def _untested_critical(
        self,
        graph: Optional[nx.DiGraph],
        test_files: List[Path],
        root: Path,
    ) -> List[str]:
        """
        Identify high-centrality (PageRank) nodes that have no matching test file.
        """
        if graph is None or graph.number_of_nodes() < 2:
            return []

        # Compute PageRank
        try:
            pr = nx.pagerank(graph, alpha=0.85)
        except Exception:
            return []

        threshold = sorted(pr.values())[-max(1, len(pr) // 5)]  # top 20%
        high_centrality = {n for n, v in pr.items() if v >= threshold}

        # Test file name stems
        test_stems: Set[str] = set()
        for tf in test_files:
            stem = tf.stem.replace("test_", "").replace("_test", "")
            test_stems.add(stem)

        untested = []
        for node in high_centrality:
            node_str = str(node)
            last_part = node_str.split(".")[-1]
            if last_part not in test_stems and node_str not in test_stems:
                untested.append(node_str)

        return sorted(untested)[:10]

    def _flaky_tests(
        self, test_files: List[Path], churn_map: Dict[str, int]
    ) -> List[str]:
        """Test files with abnormally high churn are potential flaky indicators."""
        flagged = []
        for tf in test_files:
            key = str(tf)
            count = churn_map.get(key, churn_map.get(tf.name, 0))
            if count >= self.flaky_churn_threshold:
                flagged.append(tf.name)
        return flagged

    @staticmethod
    def _empty_metrics() -> TestingMetrics:
        return TestingMetrics(
            test_to_code_ratio=0.0,
            test_file_count=0,
            source_file_count=0,
            untested_critical_modules=[],
            flaky_test_indicators=[],
            coverage_trend_delta=0.0,
            sub_score=50.0,  # unknown = half penalty
        )
