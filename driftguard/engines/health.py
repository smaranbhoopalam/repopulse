"""
HealthScoreEngine — Deterministic, normalized architectural health score.

Score is strictly in [0, 100] and produced by a weighted penalty
deduction framework applied to four independent structural signals:

  1. Vision violations   (configurable weight per violation)
  2. Circular deps       (strongly-connected components with size > 1)
  3. Tight coupling      (avg out-degree above a healthy baseline)
  4. Structural density  (edge-to-node ratio)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

import networkx as nx


# ---------------------------------------------------------------------------
# Metric snapshot dataclass
# ---------------------------------------------------------------------------

@dataclass
class ArchitectureMetrics:
    """Structured snapshot of a single graph's health metrics."""

    score: float
    nodes: int
    edges: int
    violations_count: int
    scc_count: int
    avg_out_degree: float
    complexity_ratio: float
    # Detailed SCC info for reporting
    circular_components: List[List[Any]] = field(default_factory=list)
    # Centrality — optional, populated if requested
    pagerank: Dict[Any, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dictionary (excludes bulky centrality data by default)."""
        return {
            "score": self.score,
            "nodes": self.nodes,
            "edges": self.edges,
            "violations_count": self.violations_count,
            "scc_count": self.scc_count,
            "avg_out_degree": self.avg_out_degree,
            "complexity_ratio": self.complexity_ratio,
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class HealthScoreEngine:
    """
    Compute a deterministic architectural health score for a dependency graph.

    Parameters
    ----------
    violation_weight:
        Penalty per detected vision rule violation (default 20 pts).
    scc_weight:
        Penalty per circular dependency component with size > 1 (default 10 pts).
    coupling_threshold:
        Average out-degree above which tight coupling is penalized (default 2.5).
    coupling_weight:
        Penalty multiplier per unit of coupling excess (default 5 pts).
    complexity_weight:
        Penalty multiplier on the edge-to-node complexity ratio (default 2 pts).
    compute_pagerank:
        Whether to compute PageRank centrality and embed it in metrics.
    """

    def __init__(
        self,
        violation_weight: float = 20.0,
        scc_weight: float = 10.0,
        coupling_threshold: float = 2.5,
        coupling_weight: float = 5.0,
        complexity_weight: float = 2.0,
        compute_pagerank: bool = False,
    ) -> None:
        self.violation_weight = violation_weight
        self.scc_weight = scc_weight
        self.coupling_threshold = coupling_threshold
        self.coupling_weight = coupling_weight
        self.complexity_weight = complexity_weight
        self.compute_pagerank = compute_pagerank

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calculate(
        self,
        graph: nx.DiGraph,
        violations: List[str],
    ) -> Tuple[float, ArchitectureMetrics]:
        """
        Compute health score and return it alongside a rich metrics snapshot.

        Parameters
        ----------
        graph:
            The current dependency graph snapshot.
        violations:
            List of violation messages produced by ``VisionRuleEngine``.

        Returns
        -------
        (score, metrics)
            *score*  — float in [0, 100]
            *metrics* — ``ArchitectureMetrics`` instance
        """
        if graph is None or graph.number_of_nodes() == 0:
            return 100.0, self._empty_metrics()

        n = graph.number_of_nodes()
        e = graph.number_of_edges()

        # --- Penalty 1: Vision violations ---
        viol_penalty = len(violations) * self.violation_weight

        # --- Penalty 2: Circular dependencies (Tarjan SCC, O(V+E)) ---
        circular = [
            sorted(scc)  # deterministic ordering
            for scc in nx.strongly_connected_components(graph)
            if len(scc) > 1
        ]
        scc_penalty = len(circular) * self.scc_weight

        # --- Penalty 3: Tight coupling ---
        avg_out = e / n
        coupling_penalty = max(0.0, avg_out - self.coupling_threshold) * self.coupling_weight

        # --- Penalty 4: Structural complexity ---
        complexity_ratio = e / n
        complexity_penalty = complexity_ratio * self.complexity_weight

        total_penalty = viol_penalty + scc_penalty + coupling_penalty + complexity_penalty
        score = round(max(0.0, min(100.0, 100.0 - total_penalty)), 2)

        pagerank: Dict[Any, float] = {}
        if self.compute_pagerank and e > 0:
            pagerank = {
                k: round(v, 6)
                for k, v in nx.pagerank(graph, alpha=0.85).items()
            }

        metrics = ArchitectureMetrics(
            score=score,
            nodes=n,
            edges=e,
            violations_count=len(violations),
            scc_count=len(circular),
            avg_out_degree=round(avg_out, 4),
            complexity_ratio=round(complexity_ratio, 4),
            circular_components=circular,
            pagerank=pagerank,
        )
        return score, metrics

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_metrics() -> ArchitectureMetrics:
        return ArchitectureMetrics(
            score=100.0,
            nodes=0,
            edges=0,
            violations_count=0,
            scc_count=0,
            avg_out_degree=0.0,
            complexity_ratio=0.0,
        )
