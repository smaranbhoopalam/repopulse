"""
Narrator — Rule-based human-readable insight generation.

Produces InsightCard objects describing what happened to the health score,
why it changed, which modules are responsible, and how severe the decay is.

No external LLM required — all narratives are generated from rule templates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# InsightCard
# ---------------------------------------------------------------------------

@dataclass
class InsightCard:
    """A single human-readable insight about architectural health."""
    severity: str       # "CRITICAL" | "WARNING" | "INFO"
    category: str       # "Architecture" | "Complexity" | "Dependency" | etc.
    title: str
    detail: str
    commit_sha: Optional[str] = None
    affected_modules: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "category": self.category,
            "title": self.title,
            "detail": self.detail,
            "commit_sha": self.commit_sha,
            "affected_modules": self.affected_modules,
        }

    @property
    def emoji(self) -> str:
        return {"CRITICAL": "🔴", "WARNING": "🟡", "INFO": "🟢"}.get(self.severity, "⚪")


# ---------------------------------------------------------------------------
# Narrator
# ---------------------------------------------------------------------------

class Narrator:
    """
    Generate InsightCards from metric snapshots and drift data.

    Accepts metric objects and produces ranked, human-readable insight cards.
    """

    def narrate(
        self,
        health_report: Any,
        architecture_metrics: Any,
        drift_report: Any,
        complexity_metrics: Optional[Any] = None,
        dependency_metrics: Optional[Any] = None,
        evolution_metrics: Optional[Any] = None,
        graph_analysis: Optional[Any] = None,
        commit_sha: Optional[str] = None,
    ) -> List[InsightCard]:
        """Generate all applicable insight cards for a commit snapshot."""
        cards: List[InsightCard] = []

        cards.extend(self._narrate_overall(health_report, drift_report, commit_sha))
        cards.extend(self._narrate_architecture(architecture_metrics, commit_sha))
        if complexity_metrics:
            cards.extend(self._narrate_complexity(complexity_metrics, commit_sha))
        if dependency_metrics:
            cards.extend(self._narrate_dependency(dependency_metrics, commit_sha))
        if evolution_metrics:
            cards.extend(self._narrate_evolution(evolution_metrics, commit_sha))
        if graph_analysis:
            cards.extend(self._narrate_graph(graph_analysis, commit_sha))

        # Sort by severity: CRITICAL > WARNING > INFO
        order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
        return sorted(cards, key=lambda c: order.get(c.severity, 3))

    # ------------------------------------------------------------------
    # Overall health
    # ------------------------------------------------------------------

    def _narrate_overall(
        self, hr: Any, drift: Any, sha: Optional[str]
    ) -> List[InsightCard]:
        cards = []
        score = getattr(hr, "overall_score", getattr(hr, "score", 100.0))
        status = getattr(hr, "status_label", "")
        score_drop = getattr(drift, "score_drop", 0.0)

        if score_drop >= 15:
            cards.append(InsightCard(
                severity="CRITICAL",
                category="Health",
                title="Score Crash Detected",
                detail=(
                    f"Health score dropped {score_drop:.1f} points in this commit "
                    f"(now {score:.1f}/100). This is a significant architectural regression."
                ),
                commit_sha=sha,
            ))
        elif score_drop >= 5:
            cards.append(InsightCard(
                severity="WARNING",
                category="Health",
                title="Notable Score Degradation",
                detail=(
                    f"Health score fell by {score_drop:.1f} pts to {score:.1f}/100. "
                    "Review recent changes for structural issues."
                ),
                commit_sha=sha,
            ))
        elif score >= 85:
            cards.append(InsightCard(
                severity="INFO",
                category="Health",
                title="Architecture Healthy",
                detail=f"Repository health score is {score:.1f}/100 — {status}.",
                commit_sha=sha,
            ))

        if getattr(drift, "dependency_explosion", False):
            ratio = getattr(drift, "edge_growth_ratio", 0)
            cards.append(InsightCard(
                severity="CRITICAL",
                category="Dependencies",
                title="Dependency Explosion",
                detail=(
                    f"Import edges grew by {ratio:.0%} in this commit. "
                    "A sudden coupling surge often signals architectural boundary erosion."
                ),
                commit_sha=sha,
            ))
        return cards

    # ------------------------------------------------------------------
    # Architecture
    # ------------------------------------------------------------------

    def _narrate_architecture(self, metrics: Any, sha: Optional[str]) -> List[InsightCard]:
        cards = []
        scc = getattr(metrics, "scc_count", 0)
        viols = getattr(metrics, "violations_count", 0)
        circular = getattr(metrics, "circular_components", [])
        avg_od = getattr(metrics, "avg_out_degree", 0.0)

        if scc >= 3:
            modules = [str(c[0]) for c in circular[:3]]
            cards.append(InsightCard(
                severity="CRITICAL",
                category="Architecture",
                title=f"Multiple Circular Dependency Clusters ({scc})",
                detail=(
                    f"Found {scc} strongly-connected component(s) — circular dependency "
                    f"clusters. This severely limits testability and refactoring. "
                    f"Affected: {', '.join(modules)}."
                ),
                commit_sha=sha,
                affected_modules=modules,
            ))
        elif scc >= 1:
            modules = [str(c[0]) for c in circular[:3]]
            cards.append(InsightCard(
                severity="WARNING",
                category="Architecture",
                title="Circular Dependencies Present",
                detail=(
                    f"{scc} circular dependency cluster(s) detected. "
                    f"Consider extracting shared interfaces to break cycles."
                ),
                commit_sha=sha,
                affected_modules=modules,
            ))

        if viols >= 3:
            cards.append(InsightCard(
                severity="CRITICAL",
                category="Architecture",
                title=f"Multiple Architecture Violations ({viols})",
                detail=(
                    f"{viols} architectural rule violations detected. "
                    "Layer boundaries are being systematically bypassed."
                ),
                commit_sha=sha,
            ))
        elif viols >= 1:
            cards.append(InsightCard(
                severity="WARNING",
                category="Architecture",
                title="Architecture Violations Detected",
                detail=f"{viols} layer rule violation(s) found. Review boundary definitions.",
                commit_sha=sha,
            ))

        if avg_od > 5.0:
            cards.append(InsightCard(
                severity="WARNING",
                category="Architecture",
                title="Tight Coupling Detected",
                detail=(
                    f"Average out-degree is {avg_od:.2f} (threshold 2.5). "
                    "Modules have too many direct dependencies — consider façade patterns."
                ),
                commit_sha=sha,
            ))
        return cards

    # ------------------------------------------------------------------
    # Complexity
    # ------------------------------------------------------------------

    def _narrate_complexity(self, metrics: Any, sha: Optional[str]) -> List[InsightCard]:
        cards = []
        avg_cyc = getattr(metrics, "avg_cyclomatic", 1.0)
        max_cyc = getattr(metrics, "max_cyclomatic", 1.0)
        avg_mi = getattr(metrics, "avg_maintainability", 100.0)
        dead = getattr(metrics, "total_dead_code", 0)
        dup = getattr(metrics, "duplication_percentage", 0.0)

        if max_cyc > 20:
            cards.append(InsightCard(
                severity="CRITICAL",
                category="Complexity",
                title="Extreme Cyclomatic Complexity",
                detail=(
                    f"Peak cyclomatic complexity is {max_cyc:.0f} (avg {avg_cyc:.1f}). "
                    "Functions this complex are nearly impossible to test exhaustively."
                ),
                commit_sha=sha,
            ))
        elif avg_cyc > 8:
            cards.append(InsightCard(
                severity="WARNING",
                category="Complexity",
                title="High Average Complexity",
                detail=(
                    f"Average cyclomatic complexity is {avg_cyc:.1f}. "
                    "Consider decomposing complex functions."
                ),
                commit_sha=sha,
            ))

        if avg_mi < 30:
            cards.append(InsightCard(
                severity="WARNING",
                category="Complexity",
                title="Low Maintainability Index",
                detail=(
                    f"Average maintainability index is {avg_mi:.1f}/100. "
                    "Code is approaching unmaintainable territory."
                ),
                commit_sha=sha,
            ))

        if dup > 20:
            cards.append(InsightCard(
                severity="WARNING",
                category="Complexity",
                title=f"High Code Duplication ({dup:.0f}%)",
                detail="Significant code duplication detected. Extract shared utilities.",
                commit_sha=sha,
            ))
        return cards

    # ------------------------------------------------------------------
    # Dependency
    # ------------------------------------------------------------------

    def _narrate_dependency(self, metrics: Any, sha: Optional[str]) -> List[InsightCard]:
        cards = []
        avg_inst = getattr(metrics, "avg_instability", 0.0)
        hidden = getattr(metrics, "hidden_dependency_count", 0)
        density = getattr(metrics, "graph_density", 0.0)

        if avg_inst > 0.7:
            cards.append(InsightCard(
                severity="WARNING",
                category="Dependency",
                title="High Average Instability",
                detail=(
                    f"Average dependency instability is {avg_inst:.2f} (max 1.0). "
                    "Most modules are highly dependent on unstable code. "
                    "Add stable abstractions (interfaces/protocols)."
                ),
                commit_sha=sha,
            ))

        if hidden > 10:
            cards.append(InsightCard(
                severity="WARNING",
                category="Dependency",
                title=f"Many Hidden Dependencies ({hidden} modules)",
                detail=(
                    f"{hidden} modules have large transitive dependency reach. "
                    "Changes to core modules will propagate broadly."
                ),
                commit_sha=sha,
            ))

        if density > 0.3:
            cards.append(InsightCard(
                severity="WARNING",
                category="Dependency",
                title="Dense Dependency Graph",
                detail=(
                    f"Graph density is {density:.2f} — the codebase is becoming "
                    "highly interconnected. Modularization is recommended."
                ),
                commit_sha=sha,
            ))
        return cards

    # ------------------------------------------------------------------
    # Evolution
    # ------------------------------------------------------------------

    def _narrate_evolution(self, metrics: Any, sha: Optional[str]) -> List[InsightCard]:
        cards = []
        hotspots = getattr(metrics, "hotspot_count", 0)
        bus = getattr(metrics, "bus_factor", 999)
        hhi = getattr(metrics, "avg_ownership_hhi", 0.0)

        if bus == 1:
            cards.append(InsightCard(
                severity="CRITICAL",
                category="Team",
                title="Bus Factor = 1 (Single Point of Failure)",
                detail=(
                    "A single contributor owns the majority of files. "
                    "This is a critical knowledge risk — bus factor is 1."
                ),
                commit_sha=sha,
            ))
        elif bus <= 2:
            cards.append(InsightCard(
                severity="WARNING",
                category="Team",
                title=f"Low Bus Factor ({bus})",
                detail=(
                    f"Only {bus} contributor(s) needed to lose >50% of codebase knowledge. "
                    "Encourage code reviews and pair programming."
                ),
                commit_sha=sha,
            ))

        if hotspots >= 5:
            cards.append(InsightCard(
                severity="WARNING",
                category="Evolution",
                title=f"{hotspots} Hotspot Files Detected",
                detail=(
                    "Multiple files have very high change frequency. "
                    "Hotspots accumulate bugs and technical debt disproportionately."
                ),
                commit_sha=sha,
                affected_modules=getattr(metrics, "hotspots", [])[:5],
            ))
        return cards

    # ------------------------------------------------------------------
    # Graph analysis
    # ------------------------------------------------------------------

    def _narrate_graph(self, analysis: Any, sha: Optional[str]) -> List[InsightCard]:
        cards = []
        drift = getattr(analysis, "architectural_drift", 0.0)
        mod = getattr(analysis, "modularity_score", 1.0)
        bottlenecks = getattr(analysis, "top_bottlenecks", [])

        if drift > 0.3:
            cards.append(InsightCard(
                severity="CRITICAL",
                category="Architecture",
                title="Severe Architectural Drift",
                detail=(
                    f"Architecture drift score is {drift:.2f} — over 30% of dependency "
                    "edges changed in this commit. The structure is shifting rapidly."
                ),
                commit_sha=sha,
            ))
        elif drift > 0.15:
            cards.append(InsightCard(
                severity="WARNING",
                category="Architecture",
                title="Moderate Architectural Drift",
                detail=f"Drift score {drift:.2f}: significant structural changes in this commit.",
                commit_sha=sha,
            ))

        if mod < 0.1 and mod > 0:
            cards.append(InsightCard(
                severity="WARNING",
                category="Architecture",
                title="Low Modularity Score",
                detail=(
                    f"Modularity score is {mod:.3f} — the codebase lacks clear module "
                    "boundaries. Consider extracting independent packages."
                ),
                commit_sha=sha,
            ))

        if bottlenecks:
            cards.append(InsightCard(
                severity="INFO",
                category="Architecture",
                title="Architectural Bottlenecks Identified",
                detail=(
                    f"High betweenness centrality detected in: "
                    f"{', '.join(bottlenecks[:3])}. Changes here cascade widely."
                ),
                commit_sha=sha,
                affected_modules=bottlenecks[:5],
            ))
        return cards
