"""
demo.py — End-to-end demonstration of DriftGuard analytical engine.

Simulates a three-commit history of a Python project that progressively
degrades in architectural quality:

  Commit A (abc1111): Clean baseline — healthy graph.
  Commit B (def2222): Auth module leaks; coupling rises.
  Commit C (ghi3333): Frontend bypasses database directly. Score crashes.

Run with:
    python demo.py
"""

from __future__ import annotations

from rich.console import Console
from rich.rule import Rule

from driftguard import DriftGuardPipeline

console = Console(highlight=False)

# ---------------------------------------------------------------------------
# Sample architecture rules
# ---------------------------------------------------------------------------

RULES_YAML = """
rules:
  - frontend_cannot_access_database
  - auth_module_must_remain_isolated
"""

# ---------------------------------------------------------------------------
# Simulated commit snapshots
# ---------------------------------------------------------------------------

COMMIT_A = {
    "sha": "abc1111",
    "nodes": [
        {"id": "frontend.views",   "layer": "frontend"},
        {"id": "frontend.forms",   "layer": "frontend"},
        {"id": "api.routes",       "layer": "api"},
        {"id": "api.serializers",  "layer": "api"},
        {"id": "auth_module.core", "layer": "auth"},
        {"id": "database.models",  "layer": "database"},
        {"id": "database.queries", "layer": "database"},
    ],
    "edges": [
        {"source": "frontend.views",    "target": "api.routes"},
        {"source": "frontend.forms",    "target": "api.serializers"},
        {"source": "api.routes",        "target": "auth_module.core"},
        {"source": "api.routes",        "target": "database.models"},
        {"source": "api.serializers",   "target": "database.queries"},
    ],
}

COMMIT_B = {
    "sha": "def2222",
    "nodes": [
        {"id": "frontend.views",   "layer": "frontend"},
        {"id": "frontend.forms",   "layer": "frontend"},
        {"id": "api.routes",       "layer": "api"},
        {"id": "api.serializers",  "layer": "api"},
        {"id": "api.middleware",   "layer": "api"},       # new
        {"id": "auth_module.core", "layer": "auth"},
        {"id": "auth_module.utils","layer": "auth"},      # new
        {"id": "database.models",  "layer": "database"},
        {"id": "database.queries", "layer": "database"},
        {"id": "utils.logging",    "layer": "utils"},     # new
    ],
    "edges": [
        {"source": "frontend.views",    "target": "api.routes"},
        {"source": "frontend.forms",    "target": "api.serializers"},
        {"source": "api.routes",        "target": "auth_module.core"},
        {"source": "api.routes",        "target": "database.models"},
        {"source": "api.serializers",   "target": "database.queries"},
        {"source": "api.middleware",    "target": "auth_module.core"},
        # Isolation violation: auth_module.utils leaks outward
        {"source": "auth_module.utils", "target": "utils.logging"},
        {"source": "auth_module.core",  "target": "auth_module.utils"},
        {"source": "utils.logging",     "target": "database.queries"},  # added coupling
    ],
}

COMMIT_C = {
    "sha": "ghi3333",
    "nodes": [
        {"id": "frontend.views",   "layer": "frontend"},
        {"id": "frontend.forms",   "layer": "frontend"},
        {"id": "frontend.dashboard","layer": "frontend"},  # new
        {"id": "api.routes",       "layer": "api"},
        {"id": "api.serializers",  "layer": "api"},
        {"id": "api.middleware",   "layer": "api"},
        {"id": "auth_module.core", "layer": "auth"},
        {"id": "auth_module.utils","layer": "auth"},
        {"id": "database.models",  "layer": "database"},
        {"id": "database.queries", "layer": "database"},
        {"id": "database.orm",     "layer": "database"},   # new
        {"id": "utils.logging",    "layer": "utils"},
        {"id": "utils.cache",      "layer": "utils"},      # new
    ],
    "edges": [
        {"source": "frontend.views",      "target": "api.routes"},
        {"source": "frontend.forms",      "target": "api.serializers"},
        # 🔴 CRITICAL: frontend directly bypasses API and hits database
        {"source": "frontend.dashboard",  "target": "database.models"},
        {"source": "frontend.dashboard",  "target": "database.orm"},
        {"source": "api.routes",          "target": "auth_module.core"},
        {"source": "api.routes",          "target": "database.models"},
        {"source": "api.serializers",     "target": "database.queries"},
        {"source": "api.middleware",      "target": "auth_module.core"},
        {"source": "auth_module.utils",   "target": "utils.logging"},
        {"source": "auth_module.core",    "target": "auth_module.utils"},
        {"source": "utils.logging",       "target": "database.queries"},
        # Circular dep: database.orm ↔ api.serializers
        {"source": "database.orm",        "target": "api.serializers"},
        {"source": "utils.cache",         "target": "database.orm"},
        {"source": "frontend.dashboard",  "target": "utils.cache"},
        {"source": "database.queries",    "target": "utils.cache"},
    ],
}

COMMITS = [COMMIT_A, COMMIT_B, COMMIT_C]

# ---------------------------------------------------------------------------
# Demo runner
# ---------------------------------------------------------------------------

def main() -> None:
    console.print(Rule("[bold cyan]DriftGuard — Demo Run[/bold cyan]"))
    console.print(
        "[dim]Simulating 3 commits of progressive architectural degradation...[/dim]\n"
    )

    pipeline = DriftGuardPipeline(rules_yaml=RULES_YAML, compute_pagerank=True)

    for commit in COMMITS:
        report = pipeline.process_commit(
            commit_sha=commit["sha"],
            nodes=commit["nodes"],
            edges=commit["edges"],
        )
        console.print(report.summary())
        console.print()

    # --- Score trend summary ---
    console.print(Rule("[bold]Score Trend[/bold]"))
    history = pipeline.score_history()
    for entry in history:
        bar_len = int(entry["score"] / 2)
        bar = "#" * bar_len
        color = "green" if entry["score"] >= 80 else "yellow" if entry["score"] >= 60 else "red"
        console.print(
            f"  [{color}]{entry['commit']}  {bar:<50} {entry['score']:.1f}[/{color}]"
        )

    if pipeline.is_trending_down():
        console.print(
            "\n[bold red][!!] Architecture is on a sustained downward trend![/bold red]"
        )
    else:
        console.print("\n[green]Architecture trend is stable.[/green]")



if __name__ == "__main__":
    main()
