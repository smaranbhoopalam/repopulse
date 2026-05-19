"""
ComplexityEngine — AST-based code quality and complexity metrics.

Computes per-file and aggregate complexity signals:
  - Cyclomatic complexity (McCabe)
  - Cognitive complexity (nesting-weighted)
  - Maintainability index (Halstead-inspired)
  - Dead code estimation
  - Duplication percentage
"""

from __future__ import annotations

import ast
import hashlib
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FileComplexity:
    """Complexity metrics for a single source file."""
    path: str
    module_id: str
    cyclomatic_complexity: float
    cognitive_complexity: float
    maintainability_index: float
    line_count: int
    function_count: int
    class_count: int
    dead_code_estimate: int         # unreferenced top-level defs
    halstead_volume: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "module_id": self.module_id,
            "cyclomatic_complexity": round(self.cyclomatic_complexity, 2),
            "cognitive_complexity": round(self.cognitive_complexity, 2),
            "maintainability_index": round(self.maintainability_index, 2),
            "line_count": self.line_count,
            "function_count": self.function_count,
            "class_count": self.class_count,
            "dead_code_estimate": self.dead_code_estimate,
            "halstead_volume": round(self.halstead_volume, 2),
        }


@dataclass
class ComplexityMetrics:
    """Aggregate complexity metrics across a repository snapshot."""
    avg_cyclomatic: float
    max_cyclomatic: float
    avg_cognitive: float
    avg_maintainability: float
    total_dead_code: int
    duplication_percentage: float
    file_metrics: List[FileComplexity] = field(default_factory=list)
    # Normalized sub-score in [0, 100] — higher is better (lower complexity)
    sub_score: float = 100.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "avg_cyclomatic": round(self.avg_cyclomatic, 2),
            "max_cyclomatic": round(self.max_cyclomatic, 2),
            "avg_cognitive": round(self.avg_cognitive, 2),
            "avg_maintainability": round(self.avg_maintainability, 2),
            "total_dead_code": self.total_dead_code,
            "duplication_percentage": round(self.duplication_percentage, 2),
            "sub_score": round(self.sub_score, 2),
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ComplexityEngine:
    """
    Analyse Python source files for code complexity signals.

    Parameters
    ----------
    max_cyclomatic_threshold:
        Cyclomatic complexity above which a function is "complex" (default 10).
    maintainability_min:
        Minimum acceptable maintainability index (default 20 — MS scale).
    """

    DECISION_NODES = (
        ast.If, ast.While, ast.For, ast.ExceptHandler,
        ast.With, ast.Assert, ast.comprehension,
    )
    BOOL_OPS = (ast.BoolOp,)

    def __init__(
        self,
        max_cyclomatic_threshold: int = 10,
        maintainability_min: float = 20.0,
    ) -> None:
        self.max_cyclomatic_threshold = max_cyclomatic_threshold
        self.maintainability_min = maintainability_min

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyse_directory(self, root_dir: str) -> ComplexityMetrics:
        """Analyse all Python files under root_dir."""
        root = Path(root_dir).resolve()
        py_files = list(root.rglob("*.py"))

        file_metrics: List[FileComplexity] = []
        all_lines: List[str] = []

        for py_file in py_files:
            try:
                source = py_file.read_text(encoding="utf-8", errors="ignore")
                fc = self._analyse_file(py_file, root, source)
                file_metrics.append(fc)
                all_lines.extend(source.splitlines())
            except Exception:
                pass

        return self._aggregate(file_metrics, all_lines)

    def analyse_source(
        self, source: str, path: str = "<string>", module_id: str = "<string>"
    ) -> FileComplexity:
        """Analyse a single source string."""
        return self._analyse_file(Path(path), Path("."), source, module_id=module_id)

    # ------------------------------------------------------------------
    # Internal — file-level
    # ------------------------------------------------------------------

    def _analyse_file(
        self,
        py_file: Path,
        root: Path,
        source: Optional[str] = None,
        module_id: Optional[str] = None,
    ) -> FileComplexity:
        if source is None:
            source = py_file.read_text(encoding="utf-8", errors="ignore")
        if module_id is None:
            module_id = self._path_to_id(py_file, root)

        lines = source.splitlines()
        line_count = len(lines)

        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            return FileComplexity(
                path=str(py_file), module_id=module_id,
                cyclomatic_complexity=0, cognitive_complexity=0,
                maintainability_index=100, line_count=line_count,
                function_count=0, class_count=0,
                dead_code_estimate=0, halstead_volume=0,
            )

        functions = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]

        cyc = self._cyclomatic_complexity(tree, functions)
        cog = self._cognitive_complexity(tree)
        hv = self._halstead_volume(tree)
        mi = self._maintainability_index(hv, cyc, line_count)
        dead = self._dead_code_estimate(tree)

        return FileComplexity(
            path=str(py_file),
            module_id=module_id,
            cyclomatic_complexity=cyc,
            cognitive_complexity=cog,
            maintainability_index=mi,
            line_count=line_count,
            function_count=len(functions),
            class_count=len(classes),
            dead_code_estimate=dead,
            halstead_volume=hv,
        )

    # ------------------------------------------------------------------
    # Cyclomatic complexity — McCabe
    # ------------------------------------------------------------------

    def _cyclomatic_complexity(
        self, tree: ast.AST, functions: List[ast.AST]
    ) -> float:
        """Average McCabe complexity across all functions in the module."""
        if not functions:
            return 1.0  # module baseline

        scores = []
        for func in functions:
            decisions = 0
            for node in ast.walk(func):
                if isinstance(node, self.DECISION_NODES):
                    decisions += 1
                elif isinstance(node, ast.BoolOp):
                    decisions += len(node.values) - 1
                elif isinstance(node, ast.comprehension):
                    decisions += sum(1 for _ in node.ifs)
            scores.append(1 + decisions)
        return sum(scores) / len(scores)

    # ------------------------------------------------------------------
    # Cognitive complexity — nesting-weighted
    # ------------------------------------------------------------------

    def _cognitive_complexity(self, tree: ast.AST) -> float:
        """
        Simplified cognitive complexity — penalizes nesting depth.
        Each structural node adds 1 + nesting_level penalty.
        """
        STRUCTURAL = (ast.If, ast.For, ast.While, ast.Try, ast.With,
                      ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        total = 0

        def _walk(node: ast.AST, depth: int) -> None:
            nonlocal total
            for child in ast.iter_child_nodes(node):
                if isinstance(child, STRUCTURAL):
                    total += 1 + depth
                    _walk(child, depth + 1)
                else:
                    _walk(child, depth)

        _walk(tree, 0)
        return float(total)

    # ------------------------------------------------------------------
    # Halstead volume (approximation)
    # ------------------------------------------------------------------

    def _halstead_volume(self, tree: ast.AST) -> float:
        """Approximate Halstead volume from operator/operand counts."""
        operators: Set[str] = set()
        operands: Set[str] = set()
        op_count = 0
        opd_count = 0

        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp):
                operators.add(type(node.op).__name__)
                op_count += 1
            elif isinstance(node, ast.UnaryOp):
                operators.add(type(node.op).__name__)
                op_count += 1
            elif isinstance(node, ast.Compare):
                for cmp in node.ops:
                    operators.add(type(cmp).__name__)
                op_count += len(node.ops)
            elif isinstance(node, ast.Name):
                operands.add(node.id)
                opd_count += 1
            elif isinstance(node, ast.Constant):
                operands.add(str(node.value)[:20])
                opd_count += 1
            elif isinstance(node, ast.Call):
                op_count += 1

        n1, n2 = len(operators), len(operands)
        N1, N2 = op_count, opd_count
        vocab = n1 + n2
        length = N1 + N2
        if vocab < 2 or length < 2:
            return 0.0
        return length * math.log2(vocab)

    # ------------------------------------------------------------------
    # Maintainability index
    # ------------------------------------------------------------------

    def _maintainability_index(
        self, halstead_volume: float, cyclomatic: float, loc: int
    ) -> float:
        """
        Microsoft's Maintainability Index formula (0–100 scale).
        MI = max(0, (171 - 5.2*ln(HV) - 0.23*CC - 16.2*ln(LOC)) * 100 / 171)
        """
        try:
            hv_term = 5.2 * math.log(max(halstead_volume, 1))
            cc_term = 0.23 * cyclomatic
            loc_term = 16.2 * math.log(max(loc, 1))
            raw = (171 - hv_term - cc_term - loc_term) * 100 / 171
            return max(0.0, min(100.0, raw))
        except (ValueError, ZeroDivisionError):
            return 100.0

    # ------------------------------------------------------------------
    # Dead code estimation
    # ------------------------------------------------------------------

    def _dead_code_estimate(self, tree: ast.AST) -> int:
        """
        Count top-level definitions that are not referenced elsewhere.
        Heuristic only — checks names, not full cross-module analysis.
        """
        top_defs: Dict[str, str] = {}
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                top_defs[node.name] = type(node).__name__
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        top_defs[t.id] = "variable"

        # Collect all referenced names
        all_names: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                all_names.add(node.id)
            elif isinstance(node, ast.Attribute):
                all_names.add(node.attr)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    all_names.add(node.func.id)

        unreferenced = {
            name for name in top_defs
            if name not in all_names and not name.startswith("_")
        }
        return len(unreferenced)

    # ------------------------------------------------------------------
    # Duplication detection
    # ------------------------------------------------------------------

    def _duplication_percentage(self, all_lines: List[str]) -> float:
        """Line-hash-based duplication estimate (ignore blanks/comments)."""
        significant = [
            l.strip() for l in all_lines
            if l.strip() and not l.strip().startswith("#")
        ]
        if not significant:
            return 0.0
        hashes = [hashlib.md5(l.encode()).hexdigest() for l in significant]
        unique = len(set(hashes))
        return round((1 - unique / len(hashes)) * 100, 2)

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def _aggregate(
        self, file_metrics: List[FileComplexity], all_lines: List[str]
    ) -> ComplexityMetrics:
        if not file_metrics:
            return ComplexityMetrics(
                avg_cyclomatic=1.0, max_cyclomatic=1.0,
                avg_cognitive=0.0, avg_maintainability=100.0,
                total_dead_code=0, duplication_percentage=0.0,
                file_metrics=[], sub_score=100.0,
            )

        avg_cyc = sum(f.cyclomatic_complexity for f in file_metrics) / len(file_metrics)
        max_cyc = max(f.cyclomatic_complexity for f in file_metrics)
        avg_cog = sum(f.cognitive_complexity for f in file_metrics) / len(file_metrics)
        avg_mi = sum(f.maintainability_index for f in file_metrics) / len(file_metrics)
        total_dead = sum(f.dead_code_estimate for f in file_metrics)
        dup_pct = self._duplication_percentage(all_lines)

        # Sub-score: start at 100, penalize complexity signals
        sub = 100.0
        sub -= max(0, avg_cyc - 5) * 3.0          # complexity above baseline
        sub -= max(0, max_cyc - self.max_cyclomatic_threshold) * 2.0
        sub -= max(0, avg_cog - 20) * 0.5
        sub -= max(0, 60 - avg_mi) * 0.5           # maintainability below 60
        sub -= total_dead * 0.5                     # dead code penalty
        sub -= dup_pct * 0.3                        # duplication penalty
        sub = round(max(0.0, min(100.0, sub)), 2)

        return ComplexityMetrics(
            avg_cyclomatic=avg_cyc,
            max_cyclomatic=max_cyc,
            avg_cognitive=avg_cog,
            avg_maintainability=avg_mi,
            total_dead_code=total_dead,
            duplication_percentage=dup_pct,
            file_metrics=file_metrics,
            sub_score=sub,
        )

    @staticmethod
    def _path_to_id(py_file: Path, root: Path) -> str:
        try:
            rel = py_file.relative_to(root)
            parts = list(rel.parts)
            if parts[-1].endswith(".py"):
                parts[-1] = parts[-1][:-3]
            return ".".join(parts)
        except ValueError:
            return py_file.stem
