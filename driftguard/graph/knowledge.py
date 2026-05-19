"""
KnowledgeGraph — Multi-layer repository knowledge graph.

Represents the repository as a typed nx.MultiDiGraph with node types:
  file, module, contributor, commit

And edge types:
  imports, owns, modified_in

Provides typed query APIs for health analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

import networkx as nx


# ---------------------------------------------------------------------------
# Node / Edge type constants
# ---------------------------------------------------------------------------

class NodeType:
    FILE = "file"
    MODULE = "module"
    CONTRIBUTOR = "contributor"
    COMMIT = "commit"
    FUNCTION = "function"


class EdgeType:
    IMPORTS = "imports"
    OWNS = "owns"
    MODIFIED_IN = "modified_in"
    CALLS = "calls"
    INHERITS = "inherits"


# ---------------------------------------------------------------------------
# KnowledgeGraph
# ---------------------------------------------------------------------------

class KnowledgeGraph:
    """
    Multi-layer graph representing a repository's structure and evolution.

    The underlying graph is a ``nx.MultiDiGraph`` so multiple edge types
    between the same pair of nodes are allowed.
    """

    def __init__(self) -> None:
        self.G: nx.MultiDiGraph = nx.MultiDiGraph()

    # ------------------------------------------------------------------
    # Node management
    # ------------------------------------------------------------------

    def add_file(self, path: str, **attrs: Any) -> None:
        self.G.add_node(path, node_type=NodeType.FILE, **attrs)

    def add_module(self, module_id: str, **attrs: Any) -> None:
        self.G.add_node(module_id, node_type=NodeType.MODULE, **attrs)

    def add_contributor(self, name: str, email: str = "", **attrs: Any) -> None:
        key = f"contributor:{name}"
        self.G.add_node(key, node_type=NodeType.CONTRIBUTOR, name=name, email=email, **attrs)

    def add_commit(self, sha: str, **attrs: Any) -> None:
        key = f"commit:{sha}"
        self.G.add_node(key, node_type=NodeType.COMMIT, sha=sha, **attrs)

    # ------------------------------------------------------------------
    # Edge management
    # ------------------------------------------------------------------

    def add_import(self, source: str, target: str) -> None:
        self.G.add_edge(source, target, edge_type=EdgeType.IMPORTS)

    def add_ownership(self, contributor_name: str, path: str) -> None:
        self.G.add_edge(
            f"contributor:{contributor_name}", path, edge_type=EdgeType.OWNS
        )

    def add_modification(self, path: str, commit_sha: str) -> None:
        self.G.add_edge(path, f"commit:{commit_sha}", edge_type=EdgeType.MODIFIED_IN)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_nodes_by_type(self, node_type: str) -> List[str]:
        return [
            n for n, d in self.G.nodes(data=True)
            if d.get("node_type") == node_type
        ]

    def get_module_graph(self) -> nx.DiGraph:
        """
        Return a simple DiGraph containing only MODULE nodes and IMPORTS edges.
        Suitable for all existing health / drift / vision engines.
        """
        modules = set(self.get_nodes_by_type(NodeType.MODULE))
        # Also include file nodes for repos without explicit module tagging
        files = set(self.get_nodes_by_type(NodeType.FILE))
        included = modules | files

        G = nx.DiGraph()
        for node in included:
            G.add_node(node, **self.G.nodes[node])
        for u, v, data in self.G.edges(data=True):
            if (
                data.get("edge_type") == EdgeType.IMPORTS
                and u in included
                and v in included
            ):
                G.add_edge(u, v)
        return G

    def get_file_risk_score(self, path: str, churn_scores: Dict[str, float]) -> float:
        """
        Composite risk: churn × in-degree centrality × (1 / (hhi + 0.01)).
        Higher = more risky.
        """
        churn = churn_scores.get(path, 0.0)
        in_deg = self.G.in_degree(path)
        return churn * (1 + in_deg * 0.1)

    def get_hotspot_nodes(
        self, churn_scores: Dict[str, float], top_n: int = 10
    ) -> List[Tuple[str, float]]:
        """Return top-N hotspot nodes by composite risk."""
        all_files = self.get_nodes_by_type(NodeType.FILE)
        all_files += self.get_nodes_by_type(NodeType.MODULE)
        scored = [
            (path, self.get_file_risk_score(path, churn_scores))
            for path in all_files
        ]
        return sorted(scored, key=lambda x: x[1], reverse=True)[:top_n]

    def get_contributor_map(self) -> Dict[str, List[str]]:
        """Return {contributor_name: [owned_files]}."""
        result: Dict[str, List[str]] = {}
        for u, v, data in self.G.edges(data=True):
            if data.get("edge_type") == EdgeType.OWNS:
                name = self.G.nodes[u].get("name", u)
                result.setdefault(name, []).append(v)
        return result

    def to_dict(self) -> Dict[str, Any]:
        """Serialise graph to JSON-compatible dict (nodes + edges)."""
        nodes = [
            {"id": n, **{k: v for k, v in d.items()}}
            for n, d in self.G.nodes(data=True)
        ]
        edges = [
            {"source": u, "target": v, **data}
            for u, v, data in self.G.edges(data=True)
        ]
        return {
            "nodes": nodes,
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }

    @classmethod
    def from_dependency_graph(cls, dep_graph: nx.DiGraph) -> "KnowledgeGraph":
        """Build a KnowledgeGraph from an existing simple dependency graph."""
        kg = cls()
        for node, data in dep_graph.nodes(data=True):
            kg.G.add_node(
                node,
                node_type=NodeType.MODULE,
                **{k: v for k, v in data.items() if v is not None},
            )
        for u, v in dep_graph.edges():
            kg.G.add_edge(u, v, edge_type=EdgeType.IMPORTS)
        return kg
