"""
VisionRuleEngine — Parses architectural rules from a YAML schema and
detects structural violations in a dependency graph snapshot.

Supported rule types
---------------------
Type A  :  ``<layer1>_cannot_access_<layer2>``
           Catches direct and indirect dependency paths using a single
           multi-source BFS traversal (O(V+E)).
Type B  :  ``<module>_must_remain_isolated``
           Detects inbound or outbound leakage at module boundaries.
"""

from __future__ import annotations

from typing import Any, List, Set, Tuple

import networkx as nx


class VisionRuleEngine:
    """Parse user-defined architectural rules and validate a graph snapshot."""

    def __init__(self, rules: List[str]) -> None:
        """
        Parameters
        ----------
        rules:
            Raw rule strings loaded from the YAML ``rules:`` list.
        """
        self.cannot_access_rules: List[Tuple[str, str]] = []
        self.isolated_rules: List[str] = []
        self._raw_rules = rules
        self._parse_rules(rules)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_rules(self, rules: List[str]) -> None:
        """Tokenize raw rule strings into typed rule collections."""
        for rule in rules:
            rule = rule.strip()
            if "_cannot_access_" in rule:
                parts = rule.split("_cannot_access_", maxsplit=1)
                if len(parts) == 2:
                    self.cannot_access_rules.append(
                        (parts[0].strip(), parts[1].strip())
                    )
            elif rule.endswith("_must_remain_isolated"):
                module = rule[: -len("_must_remain_isolated")].strip()
                if module:
                    self.isolated_rules.append(module)

    def _matching_nodes(self, graph: nx.DiGraph, prefix: str) -> Set[Any]:
        """Return all nodes whose string representation starts with *prefix*."""
        return {n for n in graph.nodes if str(n).startswith(prefix)}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_violations(self, graph: nx.DiGraph) -> List[str]:
        """
        Run all registered rules against *graph*.

        Returns
        -------
        List[str]
            Sorted, deduplicated list of human-readable violation messages.
        """
        violations: List[str] = []
        violations.extend(self._check_cannot_access(graph))
        violations.extend(self._check_isolation(graph))
        return sorted(set(violations))

    # ------------------------------------------------------------------
    # Rule Type A — cannot_access
    # ------------------------------------------------------------------

    def _check_cannot_access(self, graph: nx.DiGraph) -> List[str]:
        """
        Detect direct *and* indirect forbidden access paths.

        For each target-layer node, performs a single BFS on the **reversed**
        graph via ``nx.single_target_shortest_path`` — O(V+E) per target —
        to find all source-layer nodes that can reach it.  This avoids the
        removed ``nx.multi_source_shortest_path`` (deprecated in nx 3.x) while
        preserving the same algorithmic complexity.
        """
        violations: List[str] = []
        reversed_graph = graph.reverse(copy=False)  # O(1) view

        for src_layer, tgt_layer in self.cannot_access_rules:
            sources = self._matching_nodes(graph, src_layer)
            targets = self._matching_nodes(graph, tgt_layer)
            if not sources or not targets:
                continue

            for tgt in targets:
                # BFS from *tgt* on the reversed graph gives all ancestors
                try:
                    ancestor_paths = nx.single_target_shortest_path(
                        reversed_graph, tgt
                    )
                except nx.NetworkXError:
                    continue

                for src in sources:
                    if src in ancestor_paths:
                        # ancestor_paths[src] is the reversed path; flip it
                        path_str = " -> ".join(
                            str(n) for n in reversed(ancestor_paths[src])
                        )
                        violations.append(
                            f"[CANNOT_ACCESS] '{src_layer}' must not access "
                            f"'{tgt_layer}'. Forbidden path: {path_str}"
                        )
        return violations

    # ------------------------------------------------------------------
    # Rule Type B — must_remain_isolated
    # ------------------------------------------------------------------

    def _check_isolation(self, graph: nx.DiGraph) -> List[str]:
        """
        Detect boundary leakage for isolated modules.

        Iterates only over the boundary edges of matched nodes — O(boundary)
        — rather than performing full graph traversals.
        """
        violations: List[str] = []
        for module in self.isolated_rules:
            mod_nodes = self._matching_nodes(graph, module)
            if not mod_nodes:
                continue

            for node in mod_nodes:
                for u, _ in graph.in_edges(node):
                    if u not in mod_nodes:
                        violations.append(
                            f"[ISOLATION] '{module}' is compromised: "
                            f"external node '{u}' imports into module node '{node}'."
                        )
                for _, v in graph.out_edges(node):
                    if v not in mod_nodes:
                        violations.append(
                            f"[ISOLATION] '{module}' leaks outward: "
                            f"module node '{node}' depends on external '{v}'."
                        )
        return violations
