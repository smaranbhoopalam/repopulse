"""
ChurnAnalyzer — File churn and ownership extraction from Git history.

Extracts per-file change frequency, line additions/deletions, and
author attribution from a Git repository without modifying the working tree.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


from driftguard.engines.evolution import FileChurnRecord


class ChurnAnalyzer:
    """
    Extract churn and ownership data from a Git repository.

    Parameters
    ----------
    repo_path:
        Path to the Git repository root.
    limit:
        Maximum number of commits to analyze (default 100).
    branch:
        Branch to analyze (default "HEAD").
    """

    def __init__(
        self,
        repo_path: str,
        limit: int = 100,
        branch: str = "HEAD",
    ) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.limit = limit
        self.branch = branch

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyse(self) -> List[FileChurnRecord]:
        """
        Walk commit history and produce FileChurnRecord per file.

        Returns an empty list if GitPython is unavailable or the path
        is not a valid repository.
        """
        try:
            from git import Repo, InvalidGitRepositoryError
            repo = Repo(str(self.repo_path))
        except Exception:
            return []

        # Accumulate per-file stats
        file_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "commit_count": 0,
            "additions": 0,
            "deletions": 0,
            "authors": defaultdict(int),
            "last_modified_ts": 0.0,
        })

        messages: List[str] = []

        try:
            commits = list(repo.iter_commits(self.branch, max_count=self.limit))
        except Exception:
            return []

        for commit in commits:
            messages.append(str(commit.message).strip())
            ts = float(commit.committed_date)
            author = str(commit.author.name) if commit.author else "unknown"

            try:
                stats_files = commit.stats.files
            except Exception:
                continue

            for fpath, fstats in stats_files.items():
                rec = file_stats[fpath]
                rec["commit_count"] += 1
                rec["additions"] += fstats.get("insertions", 0)
                rec["deletions"] += fstats.get("deletions", 0)
                rec["authors"][author] += 1
                if ts > rec["last_modified_ts"]:
                    rec["last_modified_ts"] = ts

        records: List[FileChurnRecord] = []
        for path, stats in file_stats.items():
            module_id = self._path_to_module_id(path)
            is_test = (
                Path(path).name.startswith("test_")
                or "tests" in Path(path).parts
                or path.endswith("_test.py")
            )
            records.append(FileChurnRecord(
                path=path,
                module_id=module_id,
                commit_count=stats["commit_count"],
                additions=stats["additions"],
                deletions=stats["deletions"],
                authors=dict(stats["authors"]),
                last_modified_ts=stats["last_modified_ts"] or time.time(),
                is_test_file=is_test,
            ))

        return records

    def get_ownership_map(self) -> Dict[str, str]:
        """Return {file_path: dominant_author}."""
        records = self.analyse()
        return {
            r.path: r.dominant_author or "unknown"
            for r in records
            if r.dominant_author
        }

    def get_last_commit_timestamps(self) -> Dict[str, float]:
        """Return {file_path: last_commit_unix_ts}."""
        records = self.analyse()
        return {r.path: r.last_modified_ts for r in records}

    def get_author_activity(self) -> Dict[str, float]:
        """Return {author: last_commit_ts} across all files."""
        records = self.analyse()
        activity: Dict[str, float] = {}
        for rec in records:
            for author, _ in rec.authors.items():
                if rec.last_modified_ts > activity.get(author, 0.0):
                    activity[author] = rec.last_modified_ts
        return activity

    def get_commit_messages(self) -> List[str]:
        """Return list of commit messages for refactor frequency analysis."""
        try:
            from git import Repo
            repo = Repo(str(self.repo_path))
            return [
                str(c.message).strip()
                for c in repo.iter_commits(self.branch, max_count=self.limit)
            ]
        except Exception:
            return []

    def get_churn_map(self) -> Dict[str, int]:
        """Return {file_path: commit_count} for flaky test detection."""
        records = self.analyse()
        return {r.path: r.commit_count for r in records}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _path_to_module_id(path: str) -> str:
        p = Path(path)
        parts = list(p.parts)
        if parts and parts[-1].endswith(".py"):
            parts[-1] = parts[-1][:-3]
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts) if parts else path
