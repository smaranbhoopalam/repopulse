"""
ReportGenerator — Multi-format report builder.

Generates JSON, Markdown, and self-contained HTML reports from a list
of EnrichedReport objects produced by the DriftGuardPipeline.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


class ReportGenerator:
    """Generate health reports in multiple formats."""

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    @staticmethod
    def to_json(reports: List[Any], indent: int = 2) -> str:
        """Serialise all reports to a JSON string."""
        data = [r.to_dict() for r in reports]
        return json.dumps(data, indent=indent, default=str)

    @staticmethod
    def to_json_file(reports: List[Any], path: str) -> None:
        Path(path).write_text(
            ReportGenerator.to_json(reports), encoding="utf-8"
        )

    # ------------------------------------------------------------------
    # Markdown
    # ------------------------------------------------------------------

    @staticmethod
    def to_markdown(reports: List[Any]) -> str:
        lines = ["# DriftGuard — Repository Health Report\n"]
        lines.append(f"Total commits analysed: **{len(reports)}**\n")

        for r in reports:
            d = r.to_dict()
            sha = d.get("commit_sha", "?")
            score = d.get("health", {}).get("overall_score", d.get("metrics", {}).get("score", 0))
            grade = d.get("health", {}).get("grade", "?")
            status = d.get("health", {}).get("status", "?")
            insights = d.get("insights", [])
            recs = d.get("recommendations", [])

            lines.append(f"---\n## Commit `{sha}` — Score: {score:.1f}/100 ({grade} · {status})\n")

            if insights:
                lines.append("### Insights\n")
                for ins in insights[:5]:
                    sev = ins.get("severity", "")
                    title = ins.get("title", "")
                    detail = ins.get("detail", "")
                    emoji = {"CRITICAL": "🔴", "WARNING": "🟡", "INFO": "🟢"}.get(sev, "⚪")
                    lines.append(f"- {emoji} **{title}**: {detail}\n")

            if recs:
                lines.append("### Recommendations\n")
                for rec in recs[:3]:
                    action = rec.get("action", "")
                    effort = rec.get("effort", "")
                    lines.append(f"- [{effort}] {action}\n")

        return "\n".join(lines)

    @staticmethod
    def to_markdown_file(reports: List[Any], path: str) -> None:
        Path(path).write_text(
            ReportGenerator.to_markdown(reports), encoding="utf-8"
        )

    # ------------------------------------------------------------------
    # HTML (self-contained dashboard data file)
    # ------------------------------------------------------------------

    @staticmethod
    def to_analysis_json(reports: List[Any]) -> Dict[str, Any]:
        """
        Build the analysis.json payload consumed by the dashboard.
        Serialises all reports + forecast data for client-side rendering.
        """
        serialised = [r.to_dict() for r in reports]

        # Build timeline data
        timeline = [
            {
                "commit": d.get("commit_sha", "?"),
                "score": d.get("health", {}).get("overall_score",
                         d.get("metrics", {}).get("score", 0)),
                "architecture_score": d.get("health", {}).get("architecture_score", 0),
                "complexity_score": d.get("health", {}).get("complexity_score", 0),
                "dependency_score": d.get("health", {}).get("dependency_score", 0),
                "evolution_score": d.get("health", {}).get("evolution_score", 0),
                "team_score": d.get("health", {}).get("team_score", 0),
                "testing_score": d.get("health", {}).get("testing_score", 0),
                "timestamp": d.get("timestamp", ""),
                "author": d.get("author", ""),
                "message": d.get("commit_message", ""),
            }
            for d in serialised
        ]

        # Latest snapshot
        latest = serialised[-1] if serialised else {}
        graph_data = latest.get("graph", {})

        return {
            "timeline": timeline,
            "reports": serialised,
            "graph": graph_data,
            "forecast": latest.get("forecast", {}),
            "insights": latest.get("insights", []),
            "recommendations": latest.get("recommendations", []),
            "summary": {
                "total_commits": len(reports),
                "current_score": timeline[-1]["score"] if timeline else 0,
                "min_score": min((t["score"] for t in timeline), default=0),
                "max_score": max((t["score"] for t in timeline), default=100),
            }
        }
