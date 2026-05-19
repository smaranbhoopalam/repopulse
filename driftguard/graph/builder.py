"""
GraphBuilder — Constructs and manages NetworkX dependency graphs.

Accepts two primary input formats:
  1. Structured JSON (node/edge list) — from a repository parser.
  2. Python import statement lists — for direct integration with AST tools.

Also provides graph quality utilities (pruning, metadata enrichment).
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import networkx as nx


class GraphBuilder:
    """
    Build a directed dependency graph from various input formats.

    The produced graph uses module/file identifiers as node keys and
    directed edges to represent import relationships
    (``source`` imports ``target``).
    """

    # ------------------------------------------------------------------
    # Construction from structured data
    # ------------------------------------------------------------------

    @staticmethod
    def from_node_edge_lists(
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
    ) -> nx.DiGraph:
        """
        Build a graph from a pre-parsed node/edge payload.

        Parameters
        ----------
        nodes:
            List of dicts, each containing at minimum ``{"id": <node_id>, ...}``.
            All extra keys are stored as node attributes.
        edges:
            List of dicts, each containing ``{"source": <id>, "target": <id>}``.
            An optional ``"weight"`` key is respected.

        Returns
        -------
        nx.DiGraph
        """
        G = nx.DiGraph()
        for node in nodes:
            nid = node["id"]
            attrs = {k: v for k, v in node.items() if k != "id"}
            G.add_node(nid, **attrs)
        for edge in edges:
            src, tgt = edge["source"], edge["target"]
            weight = edge.get("weight", 1)
            G.add_edge(src, tgt, weight=weight)
        return G

    # ------------------------------------------------------------------
    # Construction from Python source files (AST-based)
    # ------------------------------------------------------------------

    @classmethod
    def from_python_files(
        cls,
        root_dir: "str | Path",
        include_stdlib: bool = False,
        layer_map: Optional[Dict[str, str]] = None,
    ) -> nx.DiGraph:
        """
        Parse all Python files under *root_dir* and construct a dependency graph
        using AST import extraction.

        Parameters
        ----------
        root_dir:
            Repository root to scan recursively.
        include_stdlib:
            If False (default), edges to standard-library modules are omitted.
        layer_map:
            Optional mapping of module-name prefix → architectural layer tag,
            e.g. ``{"frontend": "ui", "db": "database"}``.
            Stored as a ``layer`` node attribute for vision rule matching.

        Returns
        -------
        nx.DiGraph
        """
        root = Path(root_dir).resolve()
        G = nx.DiGraph()
        stdlib_modules = cls._stdlib_modules()

        py_files = list(root.rglob("*.py"))
        for py_file in py_files:
            module_id = cls._file_to_module_id(py_file, root)
            layer = cls._resolve_layer(module_id, layer_map)
            G.add_node(module_id, path=str(py_file), layer=layer)

            imports = cls._extract_imports(py_file)
            for imp in imports:
                if not include_stdlib and imp in stdlib_modules:
                    continue
                resolved = cls._resolve_import(imp, py_file, root)
                if resolved:
                    target_layer = cls._resolve_layer(resolved, layer_map)
                    if resolved not in G:
                        G.add_node(resolved, path=None, layer=target_layer)
                    G.add_edge(module_id, resolved)

        return G

    # ------------------------------------------------------------------
    # Construction from in-memory source dict (Git blob traversal)
    # ------------------------------------------------------------------

    @classmethod
    def from_python_source_dict(
        cls,
        source_map: Dict[str, str],
        include_stdlib: bool = False,
        layer_map: Optional[Dict[str, str]] = None,
    ) -> nx.DiGraph:
        """
        Build a dependency graph from a ``{path: source}`` dictionary.

        Used by the safe Git walker which loads file content in-memory
        without modifying the working tree.

        Parameters
        ----------
        source_map:
            Mapping of file path strings to their Python source text.
        include_stdlib:
            If False, stdlib imports are excluded.
        layer_map:
            Optional module-prefix → layer tag mapping.
        """
        G = nx.DiGraph()
        stdlib_modules = cls._stdlib_modules()
        # Build a set of known internal module ids for resolution
        internal_ids: Set[str] = set()

        for raw_path in source_map:
            mod_id = cls._raw_path_to_module_id(raw_path)
            internal_ids.add(mod_id.split(".")[0])  # top-level package
            layer = cls._resolve_layer(mod_id, layer_map)
            G.add_node(mod_id, path=raw_path, layer=layer)

        for raw_path, source in source_map.items():
            mod_id = cls._raw_path_to_module_id(raw_path)
            imports = cls._extract_imports_from_source(source, raw_path)
            for imp in imports:
                top = imp.split(".")[0]
                if not include_stdlib and top in stdlib_modules:
                    continue
                if top not in internal_ids:
                    continue  # external dependency — skip
                if imp not in G:
                    target_layer = cls._resolve_layer(imp, layer_map)
                    G.add_node(imp, path=None, layer=target_layer)
                G.add_edge(mod_id, imp)

        return G

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    @staticmethod
    def add_metadata(
        graph: nx.DiGraph,
        node_metadata: Dict[Any, Dict[str, Any]],
    ) -> nx.DiGraph:
        """Bulk-attach attribute dictionaries to existing nodes."""
        for node_id, attrs in node_metadata.items():
            if node_id in graph:
                graph.nodes[node_id].update(attrs)
        return graph

    @staticmethod
    def subgraph_for_layer(graph: nx.DiGraph, layer: str) -> nx.DiGraph:
        """Return a view of the graph containing only nodes of *layer*."""
        layer_nodes = [
            n for n, d in graph.nodes(data=True) if d.get("layer") == layer
        ]
        return graph.subgraph(layer_nodes).copy()

    @staticmethod
    def prune_isolated_nodes(graph: nx.DiGraph) -> nx.DiGraph:
        """Return a copy of the graph with all degree-zero nodes removed."""
        isolated: Set[Any] = set(nx.isolates(graph))
        pruned = graph.copy()
        pruned.remove_nodes_from(isolated)
        return pruned

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _file_to_module_id(py_file: Path, root: Path) -> str:
        """Convert an absolute file path to a dotted module identifier."""
        try:
            rel = py_file.relative_to(root)
        except ValueError:
            return py_file.stem
        parts = list(rel.parts)
        if parts[-1].endswith(".py"):
            parts[-1] = parts[-1][:-3]
        if parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts) if parts else py_file.stem

    @staticmethod
    def _extract_imports(py_file: Path) -> List[str]:
        """Extract top-level import names from a Python file via AST."""
        try:
            source = py_file.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            return []
        imports: List[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module.split(".")[0])
        return imports

    @staticmethod
    def _resolve_import(
        imp: str, current_file: Path, root: Path
    ) -> Optional[str]:
        """Attempt to resolve an import name to a repo-relative module id."""
        candidate = root / imp.replace(".", os.sep)
        if (candidate.with_suffix(".py")).exists():
            try:
                return str(candidate.with_suffix(".py").relative_to(root)).replace(
                    os.sep, "."
                )[:-3]
            except ValueError:
                pass
        if (candidate / "__init__.py").exists():
            try:
                return str(candidate.relative_to(root)).replace(os.sep, ".")
            except ValueError:
                pass
        return imp

    @staticmethod
    def _resolve_layer(
        module_id: str, layer_map: Optional[Dict[str, str]]
    ) -> Optional[str]:
        """Look up an architectural layer for a module id."""
        if not layer_map:
            return None
        for prefix, layer in layer_map.items():
            if module_id.startswith(prefix):
                return layer
        return None

    @staticmethod
    def _stdlib_modules() -> Set[str]:
        """Return a best-effort set of Python standard library module names."""
        import sys
        stdlib: Set[str] = set(sys.stdlib_module_names)  # type: ignore[attr-defined]
        return stdlib

    @staticmethod
    def _raw_path_to_module_id(raw_path: str) -> str:
        """Convert a raw path string (from Git tree) to a dotted module id."""
        import os as _os
        parts = raw_path.replace("\\", "/").split("/")
        if parts and parts[-1].endswith(".py"):
            parts[-1] = parts[-1][:-3]
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts) if parts else raw_path

    @staticmethod
    def _extract_imports_from_source(source: str, filename: str = "<string>") -> List[str]:
        """Extract top-level import names from an in-memory source string via AST."""
        try:
            tree = ast.parse(source, filename=filename)
        except SyntaxError:
            return []
        imports: List[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module.split(".")[0])
        return imports
