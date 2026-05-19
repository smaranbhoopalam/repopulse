"""
DriftGuard Git Integration — Safe commit traversal and churn extraction.

walker.py: Reads commit trees in-memory (no working-tree checkout).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Generator, Iterator, List, Optional, Set


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CommitSnapshot:
    """A single commit's metadata and file contents (loaded in-memory)."""
    sha: str
    short_sha: str
    author: str
    author_email: str
    timestamp: float            # unix epoch
    message: str
    files_changed: List[str]    # list of changed file paths
    stats_additions: int
    stats_deletions: int
    # Lazy-loaded file content map: path -> source text
    _file_contents: Dict[str, str] = field(default_factory=dict, repr=False)

    @property
    def datetime_str(self) -> str:
        import datetime
        return datetime.datetime.utcfromtimestamp(self.timestamp).strftime(
            "%Y-%m-%d %H:%M"
        )

    def get_python_files(self) -> Dict[str, str]:
        """Return {path: source} for all Python files in this snapshot."""
        return {
            path: src
            for path, src in self._file_contents.items()
            if path.endswith(".py")
        }


# ---------------------------------------------------------------------------
# GitWalker
# ---------------------------------------------------------------------------

class GitWalker:
    """
    Safe, incremental Git commit traversal.

    Reads file content from commit trees **in-memory** using GitPython's
    ``tree.traverse()`` API. The working tree is never modified.

    Parameters
    ----------
    repo_path:
        Path to the Git repository root.
    branch:
        Branch or ref to walk (default "HEAD").
    limit:
        Maximum number of commits to process (default 50).
    cache_enabled:
        If True, caches already-seen SHAs to avoid re-processing.
    file_size_limit:
        Maximum file size in bytes to load into memory (default 512 KB).
    """

    def __init__(
        self,
        repo_path: str,
        branch: str = "HEAD",
        limit: int = 50,
        cache_enabled: bool = True,
        file_size_limit: int = 512 * 1024,
    ) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.branch = branch
        self.limit = limit
        self.cache_enabled = cache_enabled
        self.file_size_limit = file_size_limit
        self._seen_shas: Set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def walk(self) -> Generator[CommitSnapshot, None, None]:
        """
        Yield ``CommitSnapshot`` objects from oldest to newest.

        Raises
        ------
        ImportError:
            If GitPython is not installed.
        RuntimeError:
            If the path is not a valid Git repository.
        """
        try:
            from git import Repo, InvalidGitRepositoryError
        except ImportError as exc:
            raise ImportError("GitPython is required: pip install gitpython") from exc

        try:
            repo = Repo(str(self.repo_path))
        except Exception as exc:
            raise RuntimeError(f"Not a valid git repo: {self.repo_path}") from exc

        commits = list(repo.iter_commits(self.branch, max_count=self.limit))
        commits.reverse()  # oldest → newest

        for commit in commits:
            sha = commit.hexsha
            if self.cache_enabled and sha in self._seen_shas:
                continue

            snapshot = self._build_snapshot(commit)
            self._seen_shas.add(sha)
            yield snapshot

    def walk_with_progress(self) -> Generator[tuple, None, None]:
        """Yield (index, total, snapshot) for progress reporting."""
        snapshots = list(self.walk())
        total = len(snapshots)
        for i, snap in enumerate(snapshots):
            yield i, total, snap

    # ------------------------------------------------------------------
    # Snapshot construction
    # ------------------------------------------------------------------

    def _build_snapshot(self, commit: Any) -> CommitSnapshot:
        """Build a CommitSnapshot from a GitPython commit object."""
        try:
            additions = commit.stats.total.get("insertions", 0)
            deletions = commit.stats.total.get("deletions", 0)
            files_changed = list(commit.stats.files.keys())
        except Exception:
            additions = deletions = 0
            files_changed = []

        # Load file contents in-memory from the commit tree
        file_contents: Dict[str, str] = {}
        try:
            for blob in commit.tree.traverse():
                if (
                    hasattr(blob, "data_stream")
                    and blob.path.endswith(".py")
                    and blob.size <= self.file_size_limit
                ):
                    try:
                        src = blob.data_stream.read().decode("utf-8", errors="ignore")
                        file_contents[blob.path] = src
                    except Exception:
                        pass
        except Exception:
            pass

        author = commit.author
        return CommitSnapshot(
            sha=commit.hexsha,
            short_sha=commit.hexsha[:8],
            author=str(author.name) if author else "unknown",
            author_email=str(author.email) if author else "",
            timestamp=float(commit.committed_date),
            message=str(commit.message).strip(),
            files_changed=files_changed,
            stats_additions=additions,
            stats_deletions=deletions,
            _file_contents=file_contents,
        )
