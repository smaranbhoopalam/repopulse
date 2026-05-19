"""
DriftGuard Dashboard Server.

Runs the full analysis pipeline on a Git repository, writes analysis.json,
then serves the interactive dashboard via Python's built-in http.server.

Usage
-----
    python -m driftguard serve --repo . --port 8080
    python -m driftguard serve --repo /path/to/myrepo --limit 30 --port 8080
"""

from __future__ import annotations

import http.server
import json
import os
import socketserver
import threading
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn

console = Console()

STATIC_DIR = Path(__file__).parent / "static"


# ---------------------------------------------------------------------------
# Analysis runner
# ---------------------------------------------------------------------------

def run_analysis(
    repo_path: str,
    rules_yaml: str = "rules: []",
    limit: int = 50,
    branch: str = "HEAD",
    weight_profile: str = "default",
    safe_mode: bool = True,
) -> Dict[str, Any]:
    """
    Run DriftGuard analysis on a repository and return the analysis.json payload.

    Tries Git-history mode first; falls back to single-snapshot mode if the
    path is not a valid Git repo or has no commits.
    """
    from driftguard.pipeline import DriftGuardPipeline
    from driftguard.reports.generator import ReportGenerator

    pipeline = DriftGuardPipeline(
        rules_yaml=rules_yaml,
        weight_profile=weight_profile,
        repo_path=repo_path,
    )

    reports: List[Any] = []

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[cyan]{task.completed}/{task.total}"),
            console=console,
        ) as progress:
            task = progress.add_task("Analysing commits...", total=limit)

            def _on_progress(idx: int, total: int, snap: Any) -> None:
                progress.update(
                    task,
                    completed=idx + 1,
                    total=total,
                    description=f"[dim]Processing commit [cyan]{snap.short_sha}[/cyan] "
                                f"by {snap.author[:20]}...[/dim]",
                )

            reports = pipeline.process_git_repo(
                repo_path=repo_path,
                limit=limit,
                branch=branch,
                on_progress=_on_progress,
            )

    except Exception as exc:
        console.print(f"[yellow]Git history mode failed ({exc}), falling back to snapshot mode...[/yellow]")
        try:
            report = pipeline.process_python_repo(repo_path)
            reports = [report]
        except Exception as exc2:
            console.print(f"[red]Snapshot mode also failed: {exc2}[/red]")

    return ReportGenerator.to_analysis_json(reports)


# ---------------------------------------------------------------------------
# HTTP Handler
# ---------------------------------------------------------------------------

class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    """Serves static files from the dashboard/static directory."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass  # suppress default request logging


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

def serve(
    repo_path: str,
    port: int = 8080,
    rules_yaml: str = "rules: []",
    limit: int = 50,
    branch: str = "HEAD",
    weight_profile: str = "default",
    open_browser: bool = True,
) -> None:
    """
    Run analysis and serve the interactive dashboard.

    Parameters
    ----------
    repo_path:
        Path to the repository to analyse.
    port:
        Port to serve the dashboard on.
    rules_yaml:
        Raw rules YAML configuration.
    limit:
        Maximum commits to analyse.
    branch:
        Git branch to analyse.
    weight_profile:
        Scoring weight profile.
    open_browser:
        Whether to open the browser automatically.
    """
    console.print(Panel(
        f"[bold cyan]DriftGuard Dashboard[/bold cyan]\n"
        f"Repository: [dim]{repo_path}[/dim]\n"
        f"Commits:    [dim]{limit}[/dim]\n"
        f"Profile:    [dim]{weight_profile}[/dim]",
        title="Initializing",
        border_style="blue",
    ))

    # Run analysis
    console.print("\n[bold]Running analysis pipeline...[/bold]\n")
    analysis_data = run_analysis(
        repo_path=repo_path,
        rules_yaml=rules_yaml,
        limit=limit,
        branch=branch,
        weight_profile=weight_profile,
    )

    # Write analysis.json to static dir
    analysis_path = STATIC_DIR / "analysis.json"
    analysis_path.write_text(
        json.dumps(analysis_data, indent=2, default=str),
        encoding="utf-8",
    )

    n_commits = analysis_data.get("summary", {}).get("total_commits", 0)
    current_score = analysis_data.get("summary", {}).get("current_score", 0)
    console.print(
        f"\n[bold green]Analysis complete![/bold green] "
        f"{n_commits} commits processed. "
        f"Current health score: [bold cyan]{current_score:.1f}/100[/bold cyan]\n"
    )

    # Start server
    url = f"http://localhost:{port}"
    with socketserver.TCPServer(("", port), DashboardHandler) as httpd:
        console.print(Panel(
            f"[bold green]Dashboard ready![/bold green]\n"
            f"Open: [link={url}][cyan]{url}[/cyan][/link]\n\n"
            f"[dim]Press Ctrl+C to stop[/dim]",
            title="DriftGuard Dashboard",
            border_style="green",
        ))

        if open_browser:
            threading.Timer(0.5, webbrowser.open, args=[url]).start()

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            console.print("\n[yellow]Dashboard stopped.[/yellow]")
