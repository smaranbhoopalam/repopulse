"""
Architectural Drift Detection Module

Calculates structural health changes, dependency explosion, and high-risk layer violations
between two repository dependency graphs.
"""

from typing import Any, Dict, List, Set, Tuple
import networkx as nx

class DriftDetector:
    """
    Analyzes graph metrics, new dependencies, and structural anomalies to detect
    architectural drift between two consecutive codebase states.
    """
    def __init__(self, high_risk_patterns: List[Tuple[str, str]] = None):
        """
        Initialize the detector with configurable high-risk edge patterns.
        
        :param high_risk_patterns: A list of (source_substring, dest_substring) tuples.
                                   If a new edge matches any pattern, it is flagged.
        """
        self.high_risk_patterns = high_risk_patterns or []

    def detect_drift(self, previous_graph: nx.DiGraph, current_graph: nx.DiGraph) -> Dict[str, Any]:
        """
        Process the structural evolution between previous and current graph states.
        
        Returns a structured dictionary indicating any detected architectural drift.
        """
        prev_g = previous_graph if previous_graph else nx.DiGraph()
        curr_g = current_graph if current_graph else nx.DiGraph()
        
        # Step 1: Global Graph Metrics Delta
        density_change = self._safe_density(curr_g) - self._safe_density(prev_g)
        clustering_change = self._safe_clustering(curr_g) - self._safe_clustering(prev_g)

        # Step 2: Dependency Explosion (Hub Node Detection)
        hub_nodes = []
        for node in curr_g.nodes():
            if not prev_g.has_node(node):
                continue
            
            p_in, p_out = prev_g.in_degree(node), prev_g.out_degree(node)
            c_in, c_out = curr_g.in_degree(node), curr_g.out_degree(node)
            
            in_increase_pct = ((c_in - p_in) / p_in) if p_in > 0 else 0
            out_increase_pct = ((c_out - p_out) / p_out) if p_out > 0 else 0
            
            if in_increase_pct > 0.30 or out_increase_pct > 0.30:
                hub_nodes.append({
                    "node": node,
                    "in_degree_change_pct": round(in_increase_pct * 100, 2),
                    "out_degree_change_pct": round(out_increase_pct * 100, 2)
                })

        # Step 3: Structural Degradation (New Circular Dependencies)
        prev_cycles = self._get_unique_cycles(prev_g)
        curr_cycles = self._get_unique_cycles(curr_g)
        new_cycles = list(curr_cycles - prev_cycles)

        # Step 4: Layer & Isolation Violations
        added_edges = set(curr_g.edges()) - set(prev_g.edges())
        high_risk_edges = []
        
        for src, dst in added_edges:
            for p_src, p_dst in self.high_risk_patterns:
                if p_src in src and p_dst in dst:
                    high_risk_edges.append({"from": src, "to": dst})
                    break

        # Check if actionable drift occurred
        drift_detected = any([
            len(hub_nodes) > 0,
            len(new_cycles) > 0,
            len(high_risk_edges) > 0,
            abs(density_change) >= 0.05,
            abs(clustering_change) >= 0.05
        ])

        return {
            "drift_detected": drift_detected,
            "metrics_delta": {
                "density_change": round(density_change, 4),
                "avg_clustering_change": round(clustering_change, 4)
            },
            "structural_degradation": {
                "new_cycles": [list(cycle) for cycle in new_cycles],
                "high_risk_edge_additions": high_risk_edges
            },
            "dependency_explosion": {
                "hub_nodes_created": hub_nodes
            }
        }

    # --- Internal Helpers ---

    def _safe_density(self, g: nx.DiGraph) -> float:
        """Calculate graph density safely."""
        return nx.density(g) if g.number_of_nodes() > 1 else 0.0

    def _safe_clustering(self, g: nx.DiGraph) -> float:
        """Calculate average clustering coefficient safely."""
        return nx.average_clustering(g) if g.number_of_nodes() > 0 else 0.0

    def _get_unique_cycles(self, g: nx.DiGraph) -> Set[Tuple[str, ...]]:
        """Find unique simple cycles by inspecting SCCs > size 1, avoiding permutation dupes."""
        cycles = set()
        for scc in nx.strongly_connected_components(g):
            if len(scc) > 1:
                subgraph = g.subgraph(scc)
                for cycle in nx.simple_cycles(subgraph):
                    if len(cycle) > 1:
                        # Canonicalize by rotating so the minimum element is first
                        min_idx = cycle.index(min(cycle))
                        canonical = tuple(cycle[min_idx:] + cycle[:min_idx])
                        cycles.add(canonical)
        return cycles
