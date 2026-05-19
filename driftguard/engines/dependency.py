"""
DependencyEngine — AST-based inter-module dependency metrics.

Computes per-module and aggregate dependency signals:
  - Fan-in  (afferent coupling): how many modules import this one
  - Fan-out (efferent coupling): how many modules this one imports
  - Instability index: fan-out / (fan-in + fan-out)  [0=stable, 1=unstable]
  - Circular dependency detection (SCC via Tarjan's algorithm)
  - Coupling factor: proportion of possible module pairs that are coupled
  - God module detection (abnormally high fan-in)
"""

from __future__ import annotations

import ast
import os
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ModuleDependency:
    """Dependency metrics for a single module."""
    module_id: str
    path: str
    fan_in: int                          # afferent coupling (imported by N others)
    fan_out: int                         # efferent coupling (imports N others)
    instability: float                   # fan_out / (fan_in + fan_out)
    imports: List[str] = field(default_factory=list)   # resolved module IDs it imports
    imported_by: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module_id": self.module_id,
            "path": self.path,
            "fan_in": self.fan_in,
            "fan_out": self.fan_out,
            "instability": round(self.instability, 4),
            "imports": self.imports,
            "imported_by": self.imported_by,
        }


@dataclass
class DependencyMetrics:
    """Aggregate dependency metrics across a repository snapshot."""
    total_modules: int
    avg_fan_in: float
    avg_fan_out: float
    avg_instability: float
    coupling_factor: float               # proportion of coupled module pairs
    circular_dependency_count: int       # number of cycles found
    god_module_count: int                # modules with abnormally high fan-in
    circular_groups: List[List[str]] = field(default_factory=list)
    god_modules: List[str] = field(default_factory=list)
    module_metrics: List[ModuleDependency] = field(default_factory=list)
    # Normalized sub-score in [0, 100] — higher is better
    sub_score: float = 100.0

    @property
    def module_deps(self) -> List[ModuleDependency]:
        """Alias for module_metrics (pipeline compatibility)."""
        return self.module_metrics

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_modules": self.total_modules,
            "avg_fan_in": round(self.avg_fan_in, 2),
            "avg_fan_out": round(self.avg_fan_out, 2),
            "avg_instability": round(self.avg_instability, 4),
            "coupling_factor": round(self.coupling_factor, 4),
            "circular_dependency_count": self.circular_dependency_count,
            "god_module_count": self.god_module_count,
            "circular_groups": self.circular_groups,
            "god_modules": self.god_modules,
            "sub_score": round(self.sub_score, 2),
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class DependencyEngine:
    """
    Analyse Python source files for inter-module dependency metrics.

    Parameters
    ----------
    god_module_fan_in_threshold:
        Fan-in above which a module is considered a "god module" (default 10).
    instability_warn_threshold:
        Instability above which a module is considered unstable (default 0.8).
    """

    def __init__(
        self,
        god_module_fan_in_threshold: int = 10,
        instability_warn_threshold: float = 0.8,
    ) -> None:
        self.god_module_fan_in_threshold = god_module_fan_in_threshold
        self.instability_warn_threshold = instability_warn_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyse(self, graph: Any) -> DependencyMetrics:
        """
        Analyse a networkx DiGraph whose nodes are module IDs.
        Called by DriftGuardPipeline.process_commit().
        """
        # Build module_imports from graph edges
        module_imports: Dict[str, List[str]] = {str(n): [] for n in graph.nodes()}
        for u, v in graph.edges():
            module_imports[str(u)].append(str(v))
        return self.analyse_snapshot(module_imports)

    def analyse_directory(self, root_dir: str) -> DependencyMetrics:
        """Analyse all Python files under *root_dir* for dependency metrics."""
        root = Path(root_dir).resolve()
        py_files = list(root.rglob("*.py"))

        # Step 1: build module_id → raw imports map
        module_imports: Dict[str, List[str]] = {}
        module_paths: Dict[str, str] = {}

        for py_file in py_files:
            module_id = self._path_to_id(py_file, root)
            raw_imports = self._extract_imports(py_file)
            module_imports[module_id] = raw_imports
            module_paths[module_id] = str(py_file)

        # Step 2: resolve raw import strings to known module IDs
        known = set(module_imports.keys())
        resolved: Dict[str, List[str]] = {
            mid: self._resolve_imports(mid, raw, known)
            for mid, raw in module_imports.items()
        }

        # Step 3: compute fan-in / fan-out
        fan_in: Dict[str, int] = defaultdict(int)
        for mid, deps in resolved.items():
            for dep in deps:
                fan_in[dep] += 1

        # Step 4: build per-module metrics
        imported_by_map: Dict[str, List[str]] = defaultdict(list)
        for mid, deps in resolved.items():
            for dep in deps:
                imported_by_map[dep].append(mid)

        module_metrics: List[ModuleDependency] = []
        for mid in sorted(known):
            fo = len(resolved.get(mid, []))
            fi = fan_in.get(mid, 0)
            total = fi + fo
            instability = fo / total if total > 0 else 0.0
            module_metrics.append(ModuleDependency(
                module_id=mid,
                path=module_paths[mid],
                fan_in=fi,
                fan_out=fo,
                instability=instability,
                imports=sorted(resolved.get(mid, [])),
                imported_by=sorted(imported_by_map.get(mid, [])),
            ))

        # Step 5: detect circular dependencies (Tarjan SCC)
        cycles = self._find_cycles(resolved)

        # Step 6: detect god modules
        god_modules = [
            m.module_id for m in module_metrics
            if m.fan_in >= self.god_module_fan_in_threshold
        ]

        return self._aggregate(module_metrics, cycles, god_modules)

    def analyse_snapshot(
        self,
        module_imports: Dict[str, List[str]],
    ) -> DependencyMetrics:
        """
        Analyse a pre-built dependency map.

        Parameters
        ----------
        module_imports:
            Mapping of module_id → list of module_ids it imports.
            All keys and values should be internal module IDs.
        """
        known = set(module_imports.keys())
        fan_in: Dict[str, int] = defaultdict(int)
        imported_by_map: Dict[str, List[str]] = defaultdict(list)

        for mid, deps in module_imports.items():
            for dep in deps:
                if dep in known:
                    fan_in[dep] += 1
                    imported_by_map[dep].append(mid)

        module_metrics: List[ModuleDependency] = []
        for mid in sorted(known):
            fo = len([d for d in module_imports.get(mid, []) if d in known])
            fi = fan_in.get(mid, 0)
            total = fi + fo
            instability = fo / total if total > 0 else 0.0
            module_metrics.append(ModuleDependency(
                module_id=mid,
                path=mid,
                fan_in=fi,
                fan_out=fo,
                instability=instability,
                imports=sorted(d for d in module_imports.get(mid, []) if d in known),
                imported_by=sorted(imported_by_map.get(mid, [])),
            ))

        cycles = self._find_cycles({
            mid: [d for d in deps if d in known]
            for mid, deps in module_imports.items()
        })
        god_modules = [
            m.module_id for m in module_metrics
            if m.fan_in >= self.god_module_fan_in_threshold
        ]
        return self._aggregate(module_metrics, cycles, god_modules)

    # ------------------------------------------------------------------
    # Import extraction
    # ------------------------------------------------------------------

    def _extract_imports(self, py_file: Path) -> List[str]:
        """Return raw import strings found in a Python file via AST."""
        try:
            source = py_file.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source, filename=str(py_file))
        except (SyntaxError, OSError):
            return []

        imports: List[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    # Relative imports have node.level > 0
                    imports.append(node.module)
        return imports

    # ------------------------------------------------------------------
    # Import resolution
    # ------------------------------------------------------------------

    def _resolve_imports(
        self, importer: str, raw_imports: List[str], known: Set[str]
    ) -> List[str]:
        """
        Map raw import strings to known internal module IDs.
        Handles both exact matches and prefix matches (sub-module imports).
        """
        resolved: Set[str] = set()
        for raw in raw_imports:
            if raw == importer:
                continue  # skip self-imports
            # Exact match
            if raw in known:
                resolved.add(raw)
                continue
            # Prefix match: `from driftguard.engines import X` → raw = "driftguard.engines"
            # which may match "driftguard.engines.health" etc. — we match the package
            for mod in known:
                if mod == raw or mod.startswith(raw + ".") or raw.startswith(mod + "."):
                    resolved.add(mod)
        return sorted(resolved - {importer})

    # ------------------------------------------------------------------
    # Cycle detection — Tarjan's SCC
    # ------------------------------------------------------------------

    def _find_cycles(
        self, graph: Dict[str, List[str]]
    ) -> List[List[str]]:
        """
        Find all strongly connected components (SCCs) with size > 1.
        Each SCC of size > 1 represents a circular dependency group.
        Uses Tarjan's algorithm (iterative).
        """
        index_counter = [0]
        stack: List[str] = []
        lowlink: Dict[str, int] = {}
        index: Dict[str, int] = {}
        on_stack: Dict[str, bool] = {}
        sccs: List[List[str]] = []

        nodes = list(graph.keys())

        def strongconnect(v: str) -> None:
            index[v] = index_counter[0]
            lowlink[v] = index_counter[0]
            index_counter[0] += 1
            stack.append(v)
            on_stack[v] = True

            for w in graph.get(v, []):
                if w not in index:
                    strongconnect(w)
                    lowlink[v] = min(lowlink[v], lowlink.get(w, lowlink[v]))
                elif on_stack.get(w, False):
                    lowlink[v] = min(lowlink[v], index[w])

            if lowlink[v] == index[v]:
                scc: List[str] = []
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    scc.append(w)
                    if w == v:
                        break
                if len(scc) > 1:
                    sccs.append(sorted(scc))

        import sys
        old_limit = sys.getrecursionlimit()
        sys.setrecursionlimit(max(old_limit, len(nodes) * 10 + 1000))
        try:
            for node in nodes:
                if node not in index:
                    strongconnect(node)
        finally:
            sys.setrecursionlimit(old_limit)

        return sccs

    # ------------------------------------------------------------------
    # Coupling factor
    # ------------------------------------------------------------------

    def _coupling_factor(self, module_metrics: List[ModuleDependency]) -> float:
        """
        Proportion of possible directed module pairs that are actually coupled.
        CF = actual_edges / (N * (N-1))
        """
        n = len(module_metrics)
        if n < 2:
            return 0.0
        actual_edges = sum(m.fan_out for m in module_metrics)
        max_edges = n * (n - 1)
        return actual_edges / max_edges

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def _aggregate(
        self,
        module_metrics: List[ModuleDependency],
        cycles: List[List[str]],
        god_modules: List[str],
    ) -> DependencyMetrics:
        if not module_metrics:
            return DependencyMetrics(
                total_modules=0,
                avg_fan_in=0.0,
                avg_fan_out=0.0,
                avg_instability=0.0,
                coupling_factor=0.0,
                circular_dependency_count=0,
                god_module_count=0,
                circular_groups=[],
                god_modules=[],
                module_metrics=[],
                sub_score=100.0,
            )

        n = len(module_metrics)
        avg_fi = sum(m.fan_in for m in module_metrics) / n
        avg_fo = sum(m.fan_out for m in module_metrics) / n
        avg_inst = sum(m.instability for m in module_metrics) / n
        cf = self._coupling_factor(module_metrics)

        # Sub-score: start at 100, penalize coupling problems
        sub = 100.0
        sub -= len(cycles) * 8.0                       # circular deps are expensive
        sub -= len(god_modules) * 5.0                  # god modules increase fragility
        sub -= max(0, avg_fo - 5) * 2.0                # high average fan-out
        sub -= max(0, avg_inst - 0.5) * 20.0           # high average instability
        sub -= cf * 30.0                                # coupling density penalty
        sub = round(max(0.0, min(100.0, sub)), 2)

        return DependencyMetrics(
            total_modules=n,
            avg_fan_in=avg_fi,
            avg_fan_out=avg_fo,
            avg_instability=avg_inst,
            coupling_factor=cf,
            circular_dependency_count=len(cycles),
            god_module_count=len(god_modules),
            circular_groups=cycles,
            god_modules=god_modules,
            module_metrics=module_metrics,
            sub_score=sub,
        )

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _path_to_id(py_file: Path, root: Path) -> str:
        try:
            rel = py_file.relative_to(root)
            parts = list(rel.parts)
            if parts[-1].endswith(".py"):
                parts[-1] = parts[-1][:-3]
            if parts[-1] == "__init__":
                parts = parts[:-1]  # treat package __init__ as the package itself
            return ".".join(parts)
        except ValueError:
            return py_file.stem
