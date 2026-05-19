"""
DriftGuard CLI — Command-line interface for the health intelligence platform.

Usage
-----
    # Analyse a local Python repository (single snapshot)
    python -m driftguard analyse --repo ./my_project --config driftguard.yaml

    # Replay a full Git commit history and report drift
    python -m driftguard history --repo ./my_project --config driftguard.yaml --limit 50

    # Output as JSON
    python -m driftguard analyse --repo ./my_project --config driftguard.yaml --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.text import Text

console = Console()


def _load_yaml(config_path: str) -> str:
    p = Path(config_path)
    if not p.exists():
        console.print(f"[bold red]Config file not found:[/bold red] {config_path}")
        sys.exit(1)
    return p.read_text(encoding="utf-8")


def _render_commit_report(report) -> None:
    """Render a CommitReport to the terminal with rich formatting."""
    score = report.metrics.score
    score_color = (
        "bright_green" if score >= 80
        else "yellow" if score >= 60
        else "bold red"
    )

    header = Text()
    header.append("  Commit: ", style="dim")
    header.append(report.commit_sha, style="cyan bold")
    header.append("   Score: ", style="dim")
    header.append(f"{score:.1f}/100", style=score_color + " bold")

    console.print(Panel(header, title="[bold]DriftGuard Analysis[/bold]", border_style="blue"))

    # Metrics table
    metrics_table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold magenta")
    metrics_table.add_column("Metric", style="cyan")
    metrics_table.add_column("Value", justify="right")
    m = report.metrics
    metrics_table.add_row("Nodes", str(m.nodes))
    metrics_table.add_row("Edges", str(m.edges))
    metrics_table.add_row("Avg Out-Degree", f"{m.avg_out_degree:.4f}")
    metrics_table.add_row("Complexity Ratio", f"{m.complexity_ratio:.4f}")
    metrics_table.add_row("Circular Deps (SCC > 1)", str(m.scc_count))
    metrics_table.add_row("Vision Violations", str(m.violations_count))
    console.print(metrics_table)

    # Violations
    if report.violations:
        console.print("[bold red][!] Violations[/bold red]")
        for v in report.violations:
            console.print(f"  * {v}", style="red")
    else:
        console.print("[bold green][OK] No vision violations[/bold green]")

    # Drift alerts 
    drift = report.drift
    if drift.has_alerts():
        if drift.crash_alert:
            console.print(
                f"[bold red][!!] CRASH ALERT[/bold red] -- Score dropped "
                f"[bold]{drift.score_drop:.1f}[/bold] points in this commit."
            )
        if drift.dependency_explosion:
            console.print(
                f"[bold yellow][!!] DEPENDENCY EXPLOSION[/bold yellow] -- "
                f"Edge count grew [bold]{drift.edge_growth_ratio:.1%}[/bold]."
            )
    else:
        console.print(
            f"[green][OK] Drift OK[/green]  |  Score Delta: "
            f"[bold]{drift.deltas.get('score_delta', 0):+.2f}[/bold]  |  "
            f"Edges Delta: {drift.deltas.get('edges_delta', 0):+d}"
        )
    console.print()


def cmd_analyse(args: argparse.Namespace) -> None:
    """Single-snapshot analysis of a local Python repository."""
    from driftguard import DriftGuardPipeline

    rules_yaml = _load_yaml(args.config)
    pipeline = DriftGuardPipeline(
        rules_yaml=rules_yaml,
        compute_pagerank=args.pagerank,
    )

    layer_map: dict | None = None
    if args.layers:
        layer_map = dict(pair.split("=") for pair in args.layers.split(","))

    report = pipeline.process_python_repo(
        args.repo, commit_sha="HEAD", layer_map=layer_map
    )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        _render_commit_report(report)


def cmd_history(args: argparse.Namespace) -> None:
    """Walk Git commit history and report drift over time."""
    from git import Repo, InvalidGitRepositoryError
    from driftguard import DriftGuardPipeline
    from driftguard.graph.builder import GraphBuilder
    import tempfile, os

    rules_yaml = _load_yaml(args.config)
    pipeline = DriftGuardPipeline(
        rules_yaml=rules_yaml,
        compute_pagerank=args.pagerank,
    )

    try:
        repo = Repo(args.repo)
    except InvalidGitRepositoryError:
        console.print(f"[bold red]Not a valid Git repository:[/bold red] {args.repo}")
        sys.exit(1)

    commits = list(repo.iter_commits("HEAD", max_count=args.limit or 20))
    commits.reverse()  # oldest → newest

    console.print(
        f"[bold cyan]Replaying {len(commits)} commits from {args.repo}[/bold cyan]\n"
    )

    all_reports = []
    for commit in commits:
        sha = commit.hexsha[:8]
        # Checkout the tree into a temp dir for AST scanning
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                repo.git.checkout(commit.hexsha, "--", ".")
                graph = GraphBuilder.from_python_files(args.repo)
                nodes = [{"id": n, **d} for n, d in graph.nodes(data=True)]
                edges = [{"source": u, "target": v} for u, v in graph.edges()]
                report = pipeline.process_commit(sha, nodes, edges)
                all_reports.append(report)
                _render_commit_report(report)
            except Exception as exc:
                console.print(f"[dim]Skip {sha}: {exc}[/dim]")

    # Restore HEAD
    repo.git.checkout("HEAD", "--", ".")

    if args.json:
        print(json.dumps([r.to_dict() for r in all_reports], indent=2))


def cmd_serve(args: argparse.Namespace) -> None:
    """Run analysis and serve the interactive dashboard."""
    from driftguard.dashboard.server import serve
    rules_yaml = _load_yaml(args.config)
    serve(
        repo_path=args.repo,
        port=args.port,
        rules_yaml=rules_yaml,
        limit=args.limit,
        branch=args.branch,
        weight_profile=args.profile,
        open_browser=not args.no_browser,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="driftguard",
        description="DriftGuard — Repository Health Intelligence Platform",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- analyse command ---
    p_analyse = sub.add_parser("analyse", help="Analyse current repo state")
    p_analyse.add_argument("--repo", required=True, help="Path to repository root")
    p_analyse.add_argument("--config", default="driftguard.yaml", help="Rules config YAML")
    p_analyse.add_argument("--layers", default=None, help="Module-to-layer map, e.g. 'frontend=ui,db=database'")
    p_analyse.add_argument("--pagerank", action="store_true", help="Compute PageRank centrality")
    p_analyse.add_argument("--json", action="store_true", help="Output raw JSON")
    p_analyse.set_defaults(func=cmd_analyse)

    # --- history command ---
    p_hist = sub.add_parser("history", help="Replay Git history for drift analysis")
    p_hist.add_argument("--repo", required=True, help="Path to Git repository")
    p_hist.add_argument("--config", default="driftguard.yaml", help="Rules config YAML")
    p_hist.add_argument("--limit", type=int, default=20, help="Max commits to replay")
    p_hist.add_argument("--pagerank", action="store_true", help="Compute PageRank centrality")
    p_hist.add_argument("--json", action="store_true", help="Output raw JSON")
    p_hist.set_defaults(func=cmd_history)

    # --- serve command ---
    p_serve = sub.add_parser("serve", help="Run analysis and serve interactive dashboard")
    p_serve.add_argument("--repo", required=True, help="Path to Git repository")
    p_serve.add_argument("--config", default="driftguard.yaml", help="Rules config YAML")
    p_serve.add_argument("--port", type=int, default=8080, help="Port to serve dashboard on")
    p_serve.add_argument("--limit", type=int, default=50, help="Max commits to analyse")
    p_serve.add_argument("--branch", default="HEAD", help="Git branch to analyse")
    p_serve.add_argument("--profile", default="default", help="Scoring weight profile")
    p_serve.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
