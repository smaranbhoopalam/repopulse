"""
DriftGuardPipeline v2 — Full multi-domain health intelligence orchestration.

Commit-by-commit, this pipeline:
  1. Builds the dependency graph (AST or in-memory from Git).
  2. Constructs a KnowledgeGraph layer.
  3. Runs VisionRuleEngine for architecture violations.
  4. Computes ArchitectureMetrics + DriftReport (v1-compatible).
  5. Runs ComplexityEngine, DependencyEngine, EvolutionEngine, TeamEngine, TestingEngine.
  6. Runs full GraphAnalysis (PageRank, betweenness, modularity, drift).
  7. Computes weighted HealthReport via ScoringEngine.
  8. Generates InsightCards via Narrator.
  9. Produces refactor Recommendations via Recommender.
  10. Returns an EnrichedReport.

Backward Compatibility
----------------------
  ``process_commit()`` and ``process_python_repo()`` still work unchanged.
  ``EnrichedReport`` extends ``CommitReport`` — existing ``to_dict()`` works.
"""

from __future__ import annotations

import textwrap
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml

from driftguard.engines.drift import DriftEngine, DriftReport
from driftguard.engines.health import ArchitectureMetrics, HealthScoreEngine
from driftguard.engines.vision import VisionRuleEngine
from driftguard.engines.complexity import ComplexityEngine, ComplexityMetrics
from driftguard.engines.dependency import DependencyEngine, DependencyMetrics
from driftguard.engines.evolution import EvolutionEngine, EvolutionMetrics
from driftguard.engines.team import TeamEngine, TeamMetrics
from driftguard.engines.testing import TestingEngine, TestingMetrics
from driftguard.graph.builder import GraphBuilder
from driftguard.graph.knowledge import KnowledgeGraph
from driftguard.graph.analysis import GraphAnalysis, GraphAnalysisResult
from driftguard.scoring.engine import ScoringEngine, HealthReport
from driftguard.scoring.weights import PROFILES
from driftguard.insight.narrator import Narrator, InsightCard
from driftguard.insight.predictor import Predictor, CollapseEstimate
from driftguard.insight.recommendations import Recommender, Recommendation

import networkx as nx


# ---------------------------------------------------------------------------
# CommitReport (v1-compatible)
# ---------------------------------------------------------------------------

@dataclass
class CommitReport:
    """v1 commit report — preserved for backward compatibility."""
    commit_sha: str
    metrics: ArchitectureMetrics
    violations: List[str]
    drift: DriftReport

    def summary(self) -> str:
        score = self.metrics.score
        alert_str = ""
        if self.drift.crash_alert:
            alert_str += "  [!] CRASH ALERT: Score dropped {:.1f} pts\n".format(self.drift.score_drop)
        if self.drift.dependency_explosion:
            alert_str += "  [!] DEPENDENCY EXPLOSION: +{:.0%} edge growth\n".format(self.drift.edge_growth_ratio)
        viols = (
            "\n".join(f"  * {v}" for v in self.violations)
            if self.violations else "  None"
        )
        sep = "=" * 56
        return textwrap.dedent(f"""
        +{sep}+
        | DriftGuard Report
        | Commit : {self.commit_sha}
        | Score  : {score:.1f} / 100
        | Nodes  : {self.metrics.nodes}   Edges  : {self.metrics.edges}
        | SCCs   : {self.metrics.scc_count}   Avg Out-Deg : {self.metrics.avg_out_degree:.2f}
        +-- Violations {'-' * 43}+
        {viols}
        +-- Drift {'- ' * 23}+
        {alert_str if alert_str else '  No critical alerts.'}
          Score Delta : {self.drift.deltas.get('score_delta', 0):+.2f}
          Edges Delta : {self.drift.deltas.get('edges_delta', 0):+d}
        +{sep}+
        """).strip()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "commit_sha": self.commit_sha,
            "metrics": self.metrics.to_dict(),
            "violations": self.violations,
            "drift": self.drift.to_dict(),
        }


# ---------------------------------------------------------------------------
# EnrichedReport (v2)
# ---------------------------------------------------------------------------

@dataclass
class EnrichedReport(CommitReport):
    """
    Full v2 commit report with multi-domain metrics, insights, and graph data.
    Extends CommitReport for backward compatibility.
    """
    health: Optional[HealthReport] = None
    complexity: Optional[ComplexityMetrics] = None
    dependency: Optional[DependencyMetrics] = None
    evolution: Optional[EvolutionMetrics] = None
    team: Optional[TeamMetrics] = None
    testing: Optional[TestingMetrics] = None
    graph_analysis: Optional[GraphAnalysisResult] = None
    insights: List[InsightCard] = field(default_factory=list)
    recommendations: List[Recommendation] = field(default_factory=list)
    forecast: Optional[CollapseEstimate] = None
    # graph snapshot for dashboard
    graph_nodes: List[Dict[str, Any]] = field(default_factory=list)
    graph_edges: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    author: str = ""
    commit_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "health": self.health.to_dict() if self.health else None,
            "complexity": self.complexity.to_dict() if self.complexity else None,
            "dependency": self.dependency.to_dict() if self.dependency else None,
            "evolution": self.evolution.to_dict() if self.evolution else None,
            "team": self.team.to_dict() if self.team else None,
            "testing": self.testing.to_dict() if self.testing else None,
            "graph_analysis": self.graph_analysis.to_dict() if self.graph_analysis else None,
            "insights": [i.to_dict() for i in self.insights],
            "recommendations": [r.to_dict() for r in self.recommendations],
            "forecast": self.forecast.to_dict() if self.forecast else None,
            "graph": {
                "nodes": self.graph_nodes[:200],  # cap for JSON size
                "edges": self.graph_edges[:500],
            },
            "timestamp": self.timestamp,
            "author": self.author,
            "commit_message": self.commit_message,
        })
        return base

    @property
    def overall_score(self) -> float:
        if self.health:
            return self.health.overall_score
        return self.metrics.score


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class DriftGuardPipeline:
    """
    Orchestrates the full multi-domain analytical pipeline.

    Parameters
    ----------
    rules_yaml:
        Raw YAML string containing ``rules:`` configuration.
    health_config:
        Kwargs forwarded to ``HealthScoreEngine``.
    drift_config:
        Kwargs forwarded to ``DriftEngine``.
    compute_pagerank:
        Whether to compute PageRank (legacy flag — now always computed).
    weight_profile:
        Scoring weight profile name (default "default").
    repo_path:
        Optional repo path for complexity, testing, and churn analysis.
    """

    def __init__(
        self,
        rules_yaml: str = "rules: []",
        health_config: Optional[Dict[str, Any]] = None,
        drift_config: Optional[Dict[str, Any]] = None,
        compute_pagerank: bool = False,
        weight_profile: str = "default",
        repo_path: Optional[str] = None,
    ) -> None:
        parsed = yaml.safe_load(rules_yaml) or {}
        # Support both top-level 'rules' and nested 'driftguard.rules'
        rules: List[str] = (
            parsed.get("rules", [])
            or parsed.get("driftguard", {}).get("rules", [])
        )

        self.vision = VisionRuleEngine(rules)
        self.health_engine = HealthScoreEngine(
            **(health_config or {}),
            compute_pagerank=compute_pagerank,
        )
        self.drift_engine = DriftEngine(**(drift_config or {}))
        self.complexity_engine = ComplexityEngine()
        self.dependency_engine = DependencyEngine()
        self.evolution_engine = EvolutionEngine()
        self.team_engine = TeamEngine()
        self.testing_engine = TestingEngine()
        self.graph_analysis_engine = GraphAnalysis()
        self.scoring_engine = ScoringEngine(profile=weight_profile)
        self.narrator = Narrator()
        self.recommender = Recommender()
        self.predictor = Predictor()

        self._repo_path = repo_path
        self._previous_metrics: Optional[Dict[str, Any]] = None
        self._previous_sha: Optional[str] = None
        self._previous_graph: Optional[nx.DiGraph] = None
        self._reports: List[EnrichedReport] = []
        self._score_history: List[float] = []
        self._churn_history: List[float] = []

    # ------------------------------------------------------------------
    # Core pipeline — single commit
    # ------------------------------------------------------------------

    def process_commit(
        self,
        commit_sha: str,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        author: str = "",
        commit_message: str = "",
        timestamp: Optional[float] = None,
        churn_records: Optional[List[Any]] = None,
        ownership_map: Optional[Dict[str, str]] = None,
        last_commit_ts: Optional[Dict[str, float]] = None,
        author_activity: Optional[Dict[str, float]] = None,
    ) -> EnrichedReport:
        """
        Run the full analysis pipeline for one commit snapshot.

        Backward-compatible: callers only need commit_sha, nodes, edges.
        """
        # 1. Build dependency graph
        graph = GraphBuilder.from_node_edge_lists(nodes, edges)

        # 2. Architecture (v1 engines)
        violations = self.vision.check_violations(graph)
        _, arch_metrics = self.health_engine.calculate(graph, violations)

        # 3. Drift detection (v1)
        drift_report = self.drift_engine.analyze_drift(
            previous_metrics=self._previous_metrics or {},
            current_metrics=arch_metrics.to_dict(),
            current_commit=commit_sha,
            previous_commit=self._previous_sha,
        )

        # 4. Dependency metrics
        dep_metrics = self.dependency_engine.analyse(graph)

        # 5. Complexity (from repo_path if available)
        complexity_metrics = None
        if self._repo_path:
            try:
                complexity_metrics = self.complexity_engine.analyse_directory(self._repo_path)
            except Exception:
                pass

        # 6. Evolution / team metrics (from churn data if provided)
        evo_metrics = None
        team_metrics = None
        if churn_records:
            evo_metrics = self.evolution_engine.analyse(churn_records)
            if ownership_map is not None:
                team_metrics = self.team_engine.analyse(
                    ownership_map=ownership_map,
                    last_commit_ts=last_commit_ts or {},
                    author_activity=author_activity or {},
                )

        # 7. Testing metrics
        testing_metrics = None
        if self._repo_path:
            try:
                testing_metrics = self.testing_engine.analyse(
                    root_dir=self._repo_path,
                    graph=graph,
                )
            except Exception:
                pass

        # 8. Graph analysis
        hotspot_seeds = set()
        if evo_metrics:
            hotspot_seeds = set(evo_metrics.hotspots[:5])
        graph_result = self.graph_analysis_engine.analyse(
            graph=graph,
            previous_graph=self._previous_graph,
            hotspot_nodes=hotspot_seeds,
        )

        # 9. Multi-domain health score
        health_report = self.scoring_engine.compute_from_metrics(
            architecture_metrics=arch_metrics,
            complexity_metrics=complexity_metrics,
            dependency_metrics=dep_metrics,
            evolution_metrics=evo_metrics,
            team_metrics=team_metrics,
            testing_metrics=testing_metrics,
        )

        # 10. Update score history
        self._score_history.append(health_report.overall_score)
        churn_total = sum(
            r.additions + r.deletions for r in (churn_records or [])
        )
        self._churn_history.append(float(churn_total))

        # 11. Forecast
        forecast = self.predictor.forecast(
            score_history=self._score_history,
            hotspot_modules=list(hotspot_seeds),
            churn_history=self._churn_history,
        )

        # 12. Insights
        insights = self.narrator.narrate(
            health_report=health_report,
            architecture_metrics=arch_metrics,
            drift_report=drift_report,
            complexity_metrics=complexity_metrics,
            dependency_metrics=dep_metrics,
            evolution_metrics=evo_metrics,
            graph_analysis=graph_result,
            commit_sha=commit_sha,
        )

        # 13. Recommendations
        recs = self.recommender.recommend(
            architecture_metrics=arch_metrics,
            complexity_metrics=complexity_metrics,
            dependency_metrics=dep_metrics,
            evolution_metrics=evo_metrics,
            graph_analysis=graph_result,
        )

        # 14. Serialise graph snapshot for dashboard
        graph_nodes = [
            {
                "id": str(n),
                "instability": round(
                    next((m.instability for m in dep_metrics.module_deps if m.module_id == str(n)), 0.0),
                    4
                ),
                "pagerank": round(graph_result.pagerank.get(str(n), 0.0), 6),
                "risk": round(graph_result.risk_propagation.get(str(n), 0.0), 4),
                **{k: v for k, v in graph.nodes[n].items() if v is not None},
            }
            for n in graph.nodes()
        ]
        graph_edges = [
            {"source": str(u), "target": str(v)}
            for u, v in graph.edges()
        ]

        report = EnrichedReport(
            commit_sha=commit_sha,
            metrics=arch_metrics,
            violations=violations,
            drift=drift_report,
            health=health_report,
            complexity=complexity_metrics,
            dependency=dep_metrics,
            evolution=evo_metrics,
            team=team_metrics,
            testing=testing_metrics,
            graph_analysis=graph_result,
            insights=insights,
            recommendations=recs,
            forecast=forecast,
            graph_nodes=graph_nodes,
            graph_edges=graph_edges,
            timestamp=timestamp or time.time(),
            author=author,
            commit_message=commit_message,
        )

        self._reports.append(report)
        self._previous_metrics = arch_metrics.to_dict()
        self._previous_sha = commit_sha
        self._previous_graph = graph

        return report

    # ------------------------------------------------------------------
    # Single-snapshot (repo path) analysis
    # ------------------------------------------------------------------

    def process_python_repo(
        self,
        repo_path: str,
        commit_sha: str = "HEAD",
        layer_map: Optional[Dict[str, str]] = None,
    ) -> EnrichedReport:
        """
        Analyse a local Python repository from source files (single snapshot).
        Backward-compatible with v1 callers.
        """
        if not self._repo_path:
            self._repo_path = repo_path

        graph = GraphBuilder.from_python_files(repo_path, layer_map=layer_map)
        nodes = [{"id": n, **{k: v for k, v in d.items()}} for n, d in graph.nodes(data=True)]
        edges = [{"source": u, "target": v} for u, v in graph.edges()]
        return self.process_commit(commit_sha, nodes, edges)

    # ------------------------------------------------------------------
    # Git history analysis (safe, no checkout)
    # ------------------------------------------------------------------

    def process_git_repo(
        self,
        repo_path: str,
        limit: int = 50,
        branch: str = "HEAD",
        on_progress: Optional[Any] = None,
    ) -> List[EnrichedReport]:
        """
        Analyse a Git repository commit-by-commit using safe in-memory traversal.

        Parameters
        ----------
        repo_path:
            Path to the Git repository.
        limit:
            Maximum commits to analyse (most recent).
        branch:
            Git branch/ref to walk.
        on_progress:
            Optional callback(index, total, snapshot) for progress reporting.
        """
        from driftguard.git.walker import GitWalker
        from driftguard.git.churn import ChurnAnalyzer

        if not self._repo_path:
            self._repo_path = repo_path

        # Pre-compute churn data (single pass)
        churn_analyzer = ChurnAnalyzer(repo_path, limit=limit, branch=branch)
        churn_records = churn_analyzer.analyse()
        ownership_map = churn_analyzer.get_ownership_map()
        last_commit_ts = churn_analyzer.get_last_commit_timestamps()
        author_activity = churn_analyzer.get_author_activity()
        churn_file_map = churn_analyzer.get_churn_map()

        # Walk commits
        walker = GitWalker(repo_path, branch=branch, limit=limit)

        all_reports: List[EnrichedReport] = []
        snapshots = list(walker.walk())
        total = len(snapshots)

        for idx, snapshot in enumerate(snapshots):
            if on_progress:
                on_progress(idx, total, snapshot)

            # Build graph from in-memory file contents
            py_files = snapshot.get_python_files()
            if not py_files:
                continue

            try:
                graph = GraphBuilder.from_python_source_dict(py_files)
                nodes = [{"id": n, **{k: v for k, v in d.items()}} for n, d in graph.nodes(data=True)]
                edges = [{"source": u, "target": v} for u, v in graph.edges()]

                report = self.process_commit(
                    commit_sha=snapshot.short_sha,
                    nodes=nodes,
                    edges=edges,
                    author=snapshot.author,
                    commit_message=snapshot.message,
                    timestamp=snapshot.timestamp,
                    churn_records=churn_records,
                    ownership_map=ownership_map,
                    last_commit_ts=last_commit_ts,
                    author_activity=author_activity,
                )
                all_reports.append(report)
            except Exception:
                continue

        return all_reports

    # ------------------------------------------------------------------
    # Reporting helpers
    # ------------------------------------------------------------------

    def all_reports(self) -> List[EnrichedReport]:
        return list(self._reports)

    def score_history(self) -> List[Dict[str, Any]]:
        return [
            {"commit": r.commit_sha, "score": r.overall_score}
            for r in self._reports
        ]

    def is_trending_down(self, window: int = 5) -> bool:
        return self.drift_engine.is_trending_down(window)

    def latest_forecast(self) -> Optional[CollapseEstimate]:
        return self._reports[-1].forecast if self._reports else None
