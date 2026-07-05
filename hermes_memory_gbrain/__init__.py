"""GBrain memory provider for Hermes Agent.

Writes structured pages to the GBrain repository and uses
gbrain CLI for semantic prefetch and explicit tool queries.
"""

from __future__ import annotations

import json as _json
import logging
import subprocess
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Hermes runtime imports — stubs for standalone use (tests)
try:
    from agent.memory_provider import MemoryProvider
    from tools.registry import tool_error
except ImportError:
    class MemoryProvider:  # type: ignore
        pass
    def tool_error(msg: str) -> str:  # type: ignore
        return _json.dumps({"success": False, "error": msg})

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

GBRAIN_SEARCH_SCHEMA = {
    "name": "gbrain_search",
    "description": (
        "Keyword search over the GBrain knowledge base. "
        "Faster than gbrain_query. Returns raw matches. "
        "Use for specific term or name lookups."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Keywords to search for.",
            },
        },
        "required": ["query"],
    },
}

GBRAIN_QUERY_SCHEMA = {
    "name": "gbrain_query",
    "description": (
        "Hybrid semantic search over the GBrain knowledge base. "
        "Returns relevance-ranked results. "
        "Use for conceptual or fuzzy questions."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Natural language question or topic.",
            },
        },
        "required": ["question"],
    },
}

ALL_TOOL_SCHEMAS = [GBRAIN_SEARCH_SCHEMA, GBRAIN_QUERY_SCHEMA]

_SYSTEM_PROMPT_BLOCK = """\
# GBrain Memory
Active. Context from the GBrain knowledge base is auto-injected before each
turn. Use gbrain_search for keyword lookups or gbrain_query for semantic
questions when you need additional context beyond what's already injected."""

# ---------------------------------------------------------------------------
# Page templates
# ---------------------------------------------------------------------------

_USER_PAGE_TEMPLATE = """\
---
type: concept
title: Hermes 用户画像
created: {created}
---

# Hermes 用户画像

## Compiled Truth
<!-- 手动维护，Agent 不自动修改此区域 -->

## Timeline
"""

_CONTEXT_PAGE_TEMPLATE = """\
---
type: concept
title: Hermes 上下文
created: {created}
---

# Hermes 上下文

## Compiled Truth
<!-- 手动维护，Agent 不自动修改此区域 -->

## Timeline
"""

_PAGE_MAP = {
    "user": ("user.md", _USER_PAGE_TEMPLATE),
    "memory": ("context.md", _CONTEXT_PAGE_TEMPLATE),
}

_TIMELINE_ENTRY = """\
### {timestamp} — memory {action}
- **Target:** {target}
- **Content:** {content}
"""

# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class GbrainMemoryProvider(MemoryProvider):
    """Memory provider backed by a GBrain repository."""

    def __init__(self):
        self._config = None      # GbrainConfig
        self._session_id = ""
        self._cron_skipped = False

    # ------------------------------------------------------------------
    # MemoryProvider ABC — required
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "gbrain"

    def is_available(self) -> bool:
        """Check config exists and brain_dir is reachable."""
        try:
            from .config import GbrainConfig
            cfg = GbrainConfig.from_file()
            return cfg.is_valid()
        except Exception:
            return False

    def initialize(self, session_id: str, **kwargs) -> None:
        """Load config and verify the brain directory."""
        agent_context = kwargs.get("agent_context", "")
        platform = kwargs.get("platform", "cli")
        if agent_context in {"cron", "flush"} or platform == "cron":
            self._cron_skipped = True
            return

        try:
            from .config import GbrainConfig
            self._config = GbrainConfig.from_file()
            self._session_id = session_id

            if not self._config.is_valid():
                logger.debug(
                    "GBrain brain_dir not configured or not found. "
                    "Create %s/gbrain.json with 'brain_dir' key.",
                    kwargs.get("hermes_home", "~/.hermes"),
                )
                return

            # Ensure pages directory exists
            if self._config.pages_dir:
                self._config.pages_dir.mkdir(parents=True, exist_ok=True)

            logger.info(
                "GBrain memory provider initialized (brain=%s, session=%s)",
                self._config.brain_dir, session_id,
            )

        except Exception as e:
            logger.warning("GBrain init failed: %s", e)

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        if self._cron_skipped or not self._active():
            return []
        return ALL_TOOL_SCHEMAS

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        if not self._active():
            return tool_error("GBrain not available")

        try:
            if tool_name == "gbrain_search":
                query = args.get("query", "")
                result = self._run_gbrain(["search", query])
                return _json.dumps({"success": True, "content": result})

            elif tool_name == "gbrain_query":
                question = args.get("question", "")
                result = self._run_gbrain(["query", question])
                return _json.dumps({"success": True, "content": result})

            return tool_error(f"Unknown gbrain tool: {tool_name}")

        except Exception as e:
            logger.error("GBrain tool '%s' failed: %s", tool_name, e)
            return tool_error(f"GBrain tool '{tool_name}' failed: {e}")

    def shutdown(self) -> None:
        self._config = None

    # ------------------------------------------------------------------
    # MemoryProvider ABC — optional hooks
    # ------------------------------------------------------------------

    def system_prompt_block(self) -> str:
        if not self._active():
            return ""
        return _SYSTEM_PROMPT_BLOCK

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """Run gbrain query for semantic recall before each turn."""
        if not self._active():
            return ""
        if not query or not query.strip():
            return ""
        if self._is_trivial_prompt(query):
            return ""

        try:
            result = self._run_gbrain(["query", query])
            if not result or not result.strip():
                return ""

            # Wrap for clean context injection
            return f"## GBrain Context\n\n{result}"

        except Exception as e:
            logger.debug("GBrain prefetch failed: %s", e)
            return ""

    def on_memory_write(
        self,
        action: str,
        target: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Append a Timeline entry to the appropriate page.

        target='user'  → user.md
        target='memory' → context.md
        """
        if not self._active():
            return
        if target not in _PAGE_MAP:
            return

        try:
            filename, template = _PAGE_MAP[target]
            page_path = self._config.pages_dir / filename
            now = datetime.now(timezone.utc)

            if page_path.exists():
                self._append_timeline(page_path, action, target, content, now)
            else:
                self._create_page(page_path, template, action, target, content, now)

        except Exception as e:
            logger.debug("GBrain on_memory_write failed: %s", e)

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        """Note session end in the Timeline."""
        if not self._active():
            return
        try:
            now = datetime.now(timezone.utc)
            page_path = self._config.pages_dir / "context.md"

            if not page_path.exists():
                # Create page if it doesn't exist yet
                created = now.isoformat()
                page = _CONTEXT_PAGE_TEMPLATE.format(created=created)
                page += (
                    f"### {now.isoformat()} — session end\n"
                    f"- **Session:** {self._session_id}\n"
                    f"- **Messages:** {len(messages)}\n"
                )
                page_path.write_text(page, encoding="utf-8")
            else:
                entry = (
                    f"### {now.isoformat()} — session end\n"
                    f"- **Session:** {self._session_id}\n"
                    f"- **Messages:** {len(messages)}\n"
                )
                self._append_raw(page_path, entry)

        except Exception as e:
            logger.debug("GBrain on_session_end failed: %s", e)

    def get_config_schema(self) -> List[Dict[str, Any]]:
        return [
            {
                "key": "brain_dir",
                "description": "Path to the GBrain repository (e.g. ~/my-brain)",
                "required": True,
            },
            {
                "key": "command",
                "description": "Path to gbrain CLI binary",
                "default": "gbrain",
            },
            {
                "key": "timeout",
                "description": "Timeout for gbrain CLI calls (seconds)",
                "default": 30,
            },
        ]

    def save_config(self, values: Dict[str, Any], hermes_home: str) -> None:
        from pathlib import Path as _Path
        from .config import GbrainConfig
        path = _Path(hermes_home) / "gbrain.json"
        cfg = GbrainConfig.from_file(path) if path.exists() else GbrainConfig()
        for key, val in values.items():
            if hasattr(cfg, key):
                setattr(cfg, key, val)
        cfg.save(path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _active(self) -> bool:
        return not self._cron_skipped and self._config is not None and self._config.is_valid()

    def _run_gbrain(self, args: list[str]) -> str:
        """Run a gbrain CLI command and return stdout."""
        timeout = self._config.timeout if self._config else 30.0
        cmd = [self._config.command if self._config else "gbrain", *args]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                logger.debug("gbrain %s failed: %s", args[0], result.stderr[:200])
                return ""
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            logger.warning("gbrain %s timed out after %.1fs", args[0], timeout)
            return ""
        except FileNotFoundError:
            logger.debug("gbrain CLI not found: %s", self._config.command if self._config else "gbrain")
            return ""
        except Exception as e:
            logger.warning("gbrain %s error: %s", args[0], e)
            return ""

    def _create_page(
        self,
        path: Path,
        template: str,
        action: str,
        target: str,
        content: str,
        now: datetime,
    ) -> None:
        """Create a new page with frontmatter + initial Timeline entry."""
        created = now.isoformat()
        page = template.format(created=created)
        page += _TIMELINE_ENTRY.format(
            timestamp=now.isoformat(),
            action=action,
            target=target,
            content=content,
        )
        path.write_text(page, encoding="utf-8")

    def _append_timeline(
        self,
        path: Path,
        action: str,
        target: str,
        content: str,
        now: datetime,
    ) -> None:
        """Append a Timeline entry to an existing page."""
        entry = _TIMELINE_ENTRY.format(
            timestamp=now.isoformat(),
            action=action,
            target=target,
            content=content,
        )
        self._append_raw(path, entry)

    def _append_raw(self, path: Path, text: str) -> None:
        """Append raw text to a file, ensuring trailing newline."""
        existing = path.read_text(encoding="utf-8")
        if not existing.endswith("\n"):
            existing += "\n"
        path.write_text(existing + text + "\n", encoding="utf-8")

    @staticmethod
    def _is_trivial_prompt(query: str) -> bool:
        """Skip prefetch for trivial prompts."""
        q = query.strip().lower()
        if len(q) <= 3:
            return True
        if q.startswith("/"):
            return True
        return q in {"ok", "yes", "no", "thanks", "thank you", "got it", "cool"}
