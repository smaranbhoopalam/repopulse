"""
GraphAnalysis — Advanced graph algorithms for architectural intelligence.

Provides:
  - PageRank centrality
  - Betweenness centrality
  - SCC condensation analysis
  - Risk propagation (BFS flood from hotspot nodes)
  - Architectural drift score (graph edit distance approximation)
  - Modularity score (community detection)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx


@dataclass
class GraphAnalysisResult:
    """Results from the full graph analysis suite."""
    pagerank: Dict[str, float]
    betweenness: Dict[str, float]
    scc_components: List[List[str]]
    scc_count: int
    modularity_score: float
    risk_propagation: Dict[str, float]   # node -> risk score
    architectural_drift: float           # edit-distance-based drift vs. previous
    top_hubs: List[str]                  # highest PageRank nodes
    top_bottlenecks: List[str]           # highest betweenness nodes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scc_count": self.scc_count,
            "modularity_score": round(self.modularity_score, 4),
            "architectural_drift": round(self.architectural_drift, 4),
            "top_hubs": self.top_hubs[:5],
            "top_bottlenecks": self.top_bottlenecks[:5],
            "top_risk_nodes": sorted(
                self.risk_propagation.items(), key=lambda x: x[1], reverse=True
            )[:5],
        }


class GraphAnalysis:
    """
    Run the full suite of graph analysis algorithms on a dependency graph.
    """

    def __init__(self, top_n: int = 10) -> None:
        self.top_n = top_n

    def analyse(
        self,
        graph: nx.DiGraph,
        previous_graph: Optional[nx.DiGraph] = None,
        hotspot_nodes: Optional[Set[str]] = None,
    ) -> GraphAnalysisResult:
        """
        Run all graph analysis algorithms.

        Parameters
        ----------
        graph:
            Current dependency graph snapshot.
        previous_graph:
            Prior snapshot for drift computation (optional).
        hotspot_nodes:
            Seed nodes for risk propagation (e.g. high-churn files).
        """
        if graph.number_of_nodes() == 0:
            return self._empty_result()

        # PageRank
        try:
            pr = nx.pagerank(graph, alpha=0.85, max_iter=200)
            pr = {str(k): round(v, 6) for k, v in pr.items()}
        except Exception:
            pr = {str(n): 0.0 for n in graph.nodes()}

        # Betweenness (approximate for large graphs)
        try:
            n = graph.number_of_nodes()
            k = min(n, 50)  # sample for performance
            bet = nx.betweenness_centrality(graph, k=k, normalized=True)
            bet = {str(k): round(v, 6) for k, v in bet.items()}
        except Exception:
            bet = {str(n): 0.0 for n in graph.nodes()}

        # SCC
        sccs = [
            sorted(str(x) for x in scc)
            for scc in nx.strongly_connected_components(graph)
            if len(scc) > 1
        ]

        # Modularity via greedy community detection on undirected projection
        mod_score = self._modularity(graph)

        # Risk propagation
        seeds = hotspot_nodes or set()
        risk = self._risk_propagation(graph, seeds)

        # Architectural drift
        drift = self._architectural_drift(graph, previous_graph)

        # Top lists
        top_hubs = sorted(pr, key=pr.__getitem__, reverse=True)[:self.top_n]
        top_bottlenecks = sorted(bet, key=bet.__getitem__, reverse=True)[:self.top_n]

        return GraphAnalysisResult(
            pagerank=pr,
            betweenness=bet,
            scc_components=sccs,
            scc_count=len(sccs),
            modularity_score=mod_score,
            risk_propagation=risk,
            architectural_drift=drift,
            top_hubs=top_hubs,
            top_bottlenecks=top_bottlenecks,
        )

    # ------------------------------------------------------------------
    # Modularity
    # ------------------------------------------------------------------

    def _modularity(self, graph: nx.DiGraph) -> float:
        """
        Compute modularity score on the undirected projection.
        Uses Louvain-style greedy modularity maximization via NetworkX.
        Returns 0.0 if the graph is too sparse or algorithm fails.
        """
        try:
            undirected = graph.to_undirected()
            if undirected.number_of_edges() < 2:
                return 0.0
            communities = nx.community.greedy_modularity_communities(undirected)
            return nx.community.modularity(
                undirected,
                communities,
                weight=None,
            )
        except Exception:
            return 0.0

    # ------------------------------------------------------------------
    # Risk propagation
    # ------------------------------------------------------------------

    def _risk_propagation(
        self, graph: nx.DiGraph, seeds: Set[str]
    ) -> Dict[str, float]:
        """
        BFS flood from seed nodes. Risk decays with distance.
        risk(node) = Σ(1 / (dist + 1)) for all seeds reachable.
        """
        risk: Dict[str, float] = {str(n): 0.0 for n in graph.nodes()}

        for seed in seeds:
            if seed not in graph:
                continue
            try:
                lengths = nx.single_source_shortest_path_length(graph, seed)
                for node, dist in lengths.items():
                    risk[str(node)] = risk.get(str(node), 0.0) + 1.0 / (dist + 1)
            except Exception:
                pass

        return risk

    # ------------------------------------------------------------------
    # Architectural drift
    # ------------------------------------------------------------------

    def _architectural_drift(
        self,
        current: nx.DiGraph,
        previous: Optional[nx.DiGraph],
    ) -> float:
        """
        Approximate graph edit distance between two snapshots.
        Uses symmetric difference of edge sets (normalized).
        """
        if previous is None:
            return 0.0

        curr_edges = set(current.edges())
        prev_edges = set(previous.edges())

        added = len(curr_edges - prev_edges)
        removed = len(prev_edges - curr_edges)
        total = len(curr_edges | prev_edges)

        if total == 0:
            return 0.0

        return round((added + removed) / total, 4)

    # ------------------------------------------------------------------
    # Empty result
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_result() -> GraphAnalysisResult:
        return GraphAnalysisResult(
            pagerank={},
            betweenness={},
            scc_components=[],
            scc_count=0,
            modularity_score=0.0,
            risk_propagation={},
            architectural_drift=0.0,
            top_hubs=[],
            top_bottlenecks=[],
        )
