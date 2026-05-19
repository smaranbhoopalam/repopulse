"""
Recommender — Actionable refactor suggestions.

Generates ranked Recommendation objects from metric snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Recommendation:
    """A single actionable refactoring suggestion."""
    priority: int           # 1 = highest
    category: str
    action: str
    rationale: str
    effort: str             # "LOW" | "MEDIUM" | "HIGH"
    modules: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "priority": self.priority,
            "category": self.category,
            "action": self.action,
            "rationale": self.rationale,
            "effort": self.effort,
            "modules": self.modules,
        }


class Recommender:
    """Generate ranked refactoring recommendations from metric snapshots."""

    def recommend(
        self,
        architecture_metrics: Any,
        complexity_metrics: Optional[Any] = None,
        dependency_metrics: Optional[Any] = None,
        evolution_metrics: Optional[Any] = None,
        graph_analysis: Optional[Any] = None,
    ) -> List[Recommendation]:
        """Return recommendations sorted by priority (1 = most urgent)."""
        recs: List[Recommendation] = []
        prio = 1

        # Circular dependencies
        scc = getattr(architecture_metrics, "scc_count", 0)
        circular = getattr(architecture_metrics, "circular_components", [])
        if scc > 0:
            modules = [str(c[0]) for c in circular[:3]]
            recs.append(Recommendation(
                priority=prio, category="Architecture",
                action=f"Break {scc} circular dependency cycle(s)",
                rationale="Circular deps prevent independent testing and deployment.",
                effort="HIGH", modules=modules,
            ))
            prio += 1

        # Violations
        viols = getattr(architecture_metrics, "violations_count", 0)
        if viols > 0:
            recs.append(Recommendation(
                priority=prio, category="Architecture",
                action=f"Fix {viols} layer rule violation(s)",
                rationale="Layer boundaries are being bypassed — enforce access rules.",
                effort="MEDIUM",
            ))
            prio += 1

        # Graph bottlenecks
        if graph_analysis:
            bottlenecks = getattr(graph_analysis, "top_bottlenecks", [])
            if bottlenecks:
                recs.append(Recommendation(
                    priority=prio, category="Architecture",
                    action=f"Refactor architectural bottleneck: {bottlenecks[0]}",
                    rationale="High betweenness — changes here cascade to many other modules.",
                    effort="HIGH", modules=bottlenecks[:3],
                ))
                prio += 1

        # High complexity
        if complexity_metrics:
            max_cyc = getattr(complexity_metrics, "max_cyclomatic", 1)
            if max_cyc > 15:
                recs.append(Recommendation(
                    priority=prio, category="Complexity",
                    action=f"Decompose functions with cyclomatic complexity > 15",
                    rationale=f"Peak complexity {max_cyc:.0f} — extremely hard to test.",
                    effort="MEDIUM",
                ))
                prio += 1

            dead = getattr(complexity_metrics, "total_dead_code", 0)
            if dead > 5:
                recs.append(Recommendation(
                    priority=prio, category="Complexity",
                    action=f"Remove ~{dead} dead code definitions",
                    rationale="Unreferenced code increases maintenance burden.",
                    effort="LOW",
                ))
                prio += 1

        # High instability
        if dependency_metrics:
            unstable = getattr(dependency_metrics, "avg_instability", 0)
            if unstable > 0.7:
                top_unstable = getattr(dependency_metrics, "module_deps", [])
                top_mods = [m.module_id for m in sorted(
                    top_unstable, key=lambda m: m.instability, reverse=True
                )[:3]]
                recs.append(Recommendation(
                    priority=prio, category="Dependency",
                    action="Introduce stable abstractions (interfaces/protocols)",
                    rationale=f"Avg instability {unstable:.2f} — most code depends on unstable modules.",
                    effort="HIGH", modules=top_mods,
                ))
                prio += 1

        # Hotspots
        if evolution_metrics:
            hotspots = getattr(evolution_metrics, "hotspots", [])
            if hotspots:
                recs.append(Recommendation(
                    priority=prio, category="Evolution",
                    action=f"Reduce change frequency in hotspot: {hotspots[0]}",
                    rationale="Hotspot files accumulate bugs disproportionately.",
                    effort="MEDIUM", modules=hotspots[:3],
                ))
                prio += 1

            bus = getattr(evolution_metrics, "bus_factor", 99)
            if bus <= 2:
                recs.append(Recommendation(
                    priority=prio, category="Team",
                    action="Cross-train contributors on core modules",
                    rationale=f"Bus factor is {bus} — knowledge is too concentrated.",
                    effort="MEDIUM",
                ))
                prio += 1

        return sorted(recs, key=lambda r: r.priority)
