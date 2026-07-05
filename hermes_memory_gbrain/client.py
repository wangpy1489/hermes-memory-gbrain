"""Thin wrapper around the gbrain CLI for search, query, and write operations.

All calls use ``subprocess.run`` with configurable timeouts.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class GbrainPage:
    """A single result from gbrain search/query."""

    slug: str
    title: str = ""
    snippet: str = ""
    score: float = 0.0


class GbrainClient:
    """Wraps the gbrain CLI for programmatic access."""

    def __init__(self, command: str = "gbrain", timeout: float = 30.0):
        self._command = command
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Check if gbrain CLI is installed and reachable.

        Does not make network calls — just checks binary + basic health.
        """
        if not shutil.which(self._command):
            return False
        try:
            result = self._run(["--version"], timeout=5)
            return result.returncode == 0
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Search / Query (read path)
    # ------------------------------------------------------------------

    def query(self, question: str, max_results: int = 5) -> str:
        """Hybrid semantic search via ``gbrain query``.

        Returns markdown-formatted context suitable for injection.
        """
        try:
            result = self._run(
                ["query", question, "--json"],
                timeout=self._timeout,
            )
            if result.returncode != 0:
                logger.debug("gbrain query failed: %s", result.stderr)
                return ""
            return self._format_query_result(result.stdout, max_results)
        except subprocess.TimeoutExpired:
            logger.warning("gbrain query timed out after %.1fs", self._timeout)
            return ""
        except Exception as e:
            logger.warning("gbrain query error: %s", e)
            return ""

    def search(self, keyword: str, max_results: int = 5) -> str:
        """Keyword search via ``gbrain search`` (tsvector)."""
        try:
            result = self._run(
                ["search", keyword, "--json"],
                timeout=self._timeout,
            )
            if result.returncode != 0:
                logger.debug("gbrain search failed: %s", result.stderr)
                return ""
            return self._format_query_result(result.stdout, max_results)
        except subprocess.TimeoutExpired:
            logger.warning("gbrain search timed out")
            return ""
        except Exception as e:
            logger.warning("gbrain search error: %s", e)
            return ""

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def put(self, slug: str, content: str) -> bool:
        """Write a page to gbrain."""
        try:
            result = self._run(
                ["put", slug],
                input_text=content,
                timeout=self._timeout,
            )
            ok = result.returncode == 0
            if not ok:
                logger.debug("gbrain put failed: %s", result.stderr)
            return ok
        except Exception as e:
            logger.warning("gbrain put error: %s", e)
            return False

    def get(self, slug: str) -> Optional[str]:
        """Read a page from gbrain."""
        try:
            result = self._run(["get", slug], timeout=self._timeout)
            if result.returncode != 0:
                return None
            return result.stdout
        except Exception as e:
            logger.warning("gbrain get error: %s", e)
            return None

    def list_pages(self, limit: int = 20) -> str:
        """List recent pages."""
        try:
            result = self._run(
                ["list", "-n", str(limit), "--json"],
                timeout=self._timeout,
            )
            if result.returncode != 0:
                return ""
            return result.stdout
        except Exception as e:
            logger.warning("gbrain list error: %s", e)
            return ""

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run(
        self,
        args: list[str],
        *,
        timeout: float = 30,
        input_text: Optional[str] = None,
    ) -> subprocess.CompletedProcess:
        """Run a gbrain CLI command."""
        cmd = [self._command, *args]

        # Strip --json if the gbrain version doesn't support it
        # We try with --json first; if it fails, retry without
        env = {**os.environ, "GBRAIN_JSON": "1"}

        return subprocess.run(
            cmd,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )

    @staticmethod
    def _format_query_result(stdout: str, max_results: int) -> str:
        """Format gbrain query output as context block."""
        if not stdout or not stdout.strip():
            return ""

        # Try JSON first (gbrain query --json)
        try:
            data = json.loads(stdout)
            return GbrainClient._format_json_result(data, max_results)
        except json.JSONDecodeError:
            pass

        # Fallback: plain text output — truncate
        lines = stdout.strip().split("\n")
        if len(lines) > max_results * 3:
            lines = lines[: max_results * 3]
        return "\n".join(lines)

    @staticmethod
    def _format_json_result(data: dict, max_results: int) -> str:
        """Format JSON query result into readable markdown."""
        items = []
        if isinstance(data, dict):
            # Try common gbrain JSON shapes
            results = data.get("results") or data.get("pages") or data.get("items") or []
            if isinstance(results, list):
                items = results[:max_results]
            elif isinstance(data, list):
                items = data[:max_results]

        if not items:
            return ""

        parts = ["## GBrain Context\n"]
        for i, item in enumerate(items):
            if isinstance(item, dict):
                title = item.get("title") or item.get("slug", f"Result {i+1}")
                content = item.get("content") or item.get("snippet") or item.get("text", "")
                score = item.get("score", item.get("relevance", ""))
                score_str = f" (score: {score})" if score else ""
                parts.append(f"### {title}{score_str}")
                if content:
                    # Truncate long content
                    if len(content) > 500:
                        content = content[:500] + "..."
                    parts.append(content)
            elif isinstance(item, str):
                parts.append(f"- {item[:300]}")
            parts.append("")
        return "\n".join(parts)
