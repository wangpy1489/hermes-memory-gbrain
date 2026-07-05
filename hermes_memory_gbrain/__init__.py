"""GBrain memory provider for Hermes Agent.

Bridges Hermes' memory pipeline (prefetch injection, write-through, tools)
to a GBrain knowledge base.

Usage (auto-discovered by Hermes):
    hermes config set memory.provider gbrain
    hermes memory status
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

# Hermes runtime imports — only available when loaded inside Hermes.
# When running standalone (tests), provide stubs.
try:
    from agent.memory_manager import sanitize_context
    from agent.memory_provider import MemoryProvider
    from tools.registry import tool_error
except ImportError:
    def sanitize_context(text: str) -> str:  # type: ignore
        return text

    class MemoryProvider:  # type: ignore
        pass

    def tool_error(msg: str) -> str:  # type: ignore
        import json
        return json.dumps({"success": False, "error": msg})

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

GBRAIN_SEARCH_SCHEMA = {
    "name": "gbrain_search",
    "description": (
        "Keyword search over the GBrain knowledge base (tsvector). "
        "Faster and cheaper than gbrain_query. Returns raw matches. "
        "Use for specific term lookups."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Keywords to search for.",
            },
            "max_results": {
                "type": "integer",
                "description": "Max results (default 5, max 10).",
            },
        },
        "required": ["query"],
    },
}

GBRAIN_QUERY_SCHEMA = {
    "name": "gbrain_query",
    "description": (
        "Hybrid semantic search over the GBrain knowledge base "
        "(RRF + vector + query expansion). Returns synthesized, "
        "relevance-ranked results. Use for conceptual or fuzzy queries."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Natural language question or topic to search for.",
            },
            "max_results": {
                "type": "integer",
                "description": "Max results (default 5, max 10).",
            },
        },
        "required": ["question"],
    },
}

ALL_TOOL_SCHEMAS = [GBRAIN_SEARCH_SCHEMA, GBRAIN_QUERY_SCHEMA]

_SYSTEM_PROMPT_BLOCK = """\
# GBrain Memory
Active. The GBrain knowledge base provides semantic recall. Context from \
gbrain is auto-injected before each turn. Use gbrain_search for keyword \
lookups or gbrain_query for semantic questions when you need additional \
context beyond what's already injected."""


# ---------------------------------------------------------------------------
# MemoryProvider implementation
# ---------------------------------------------------------------------------

class GbrainMemoryProvider(MemoryProvider):
    """Memory provider backed by a local GBrain knowledge base."""

    def __init__(self):
        self._client = None       # GbrainClient
        self._config = None       # GbrainConfig
        self._hermes_home = ""
        self._session_id = ""
        self._prefetch_cache: str = ""
        self._prefetch_lock = threading.Lock()
        self._cron_skipped = False

    # ------------------------------------------------------------------
    # MemoryProvider ABC — required
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "gbrain"

    def is_available(self) -> bool:
        """Check gbrain CLI + DB are accessible. No network calls."""
        try:
            from .client import GbrainClient
            from .config import GbrainConfig

            cfg = GbrainConfig.from_file()
            client = GbrainClient(command=cfg.command, timeout=5.0)
            return client.is_available()
        except Exception:
            return False

    def initialize(self, session_id: str, **kwargs) -> None:
        """Connect to gbrain and warm up.

        Skips initialization for cron/flush contexts.
        """
        agent_context = kwargs.get("agent_context", "")
        platform = kwargs.get("platform", "cli")
        if agent_context in {"cron", "flush"} or platform == "cron":
            logger.debug("GBrain skipped: cron/flush context")
            self._cron_skipped = True
            return

        try:
            from .client import GbrainClient
            from .config import GbrainConfig

            self._config = GbrainConfig.from_file()
            self._client = GbrainClient(
                command=self._config.command,
                timeout=self._config.timeout,
            )
            self._hermes_home = kwargs.get("hermes_home", "")
            self._session_id = session_id

            if not self._client.is_available():
                logger.debug("GBrain not available — plugin inactive")
                self._client = None
                return

            logger.info("GBrain memory provider initialized (session=%s)", session_id)

        except ImportError:
            logger.debug("GBrain plugin deps not available")
        except Exception as e:
            logger.warning("GBrain init failed: %s", e)
            self._client = None

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        if self._cron_skipped or not self._client:
            return []
        return ALL_TOOL_SCHEMAS

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        if not self._client:
            return tool_error("GBrain not available")

        import json as _json

        try:
            if tool_name == "gbrain_search":
                query = args.get("query", "")
                max_results = min(int(args.get("max_results", 5)), 10)
                result = self._client.search(query, max_results=max_results)
                return _json.dumps({
                    "success": True,
                    "tool": tool_name,
                    "content": result or "(no results)",
                })

            elif tool_name == "gbrain_query":
                question = args.get("question", "")
                max_results = min(int(args.get("max_results", 5)), 10)
                result = self._client.query(question, max_results=max_results)
                return _json.dumps({
                    "success": True,
                    "tool": tool_name,
                    "content": result or "(no results)",
                })

            return tool_error(f"Unknown gbrain tool: {tool_name}")

        except Exception as e:
            logger.error("GBrain tool '%s' failed: %s", tool_name, e)
            return tool_error(f"GBrain tool '{tool_name}' failed: {e}")

    def shutdown(self) -> None:
        self._client = None
        self._config = None

    # ------------------------------------------------------------------
    # MemoryProvider ABC — optional hooks
    # ------------------------------------------------------------------

    def system_prompt_block(self) -> str:
        """Return static system prompt text (prompt-cache friendly)."""
        if self._cron_skipped or not self._client:
            return ""
        if not self._config:
            return ""
        return _SYSTEM_PROMPT_BLOCK

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """Recall relevant gbrain context for the upcoming turn.

        Called before each API call. Returns formatted context to inject,
        or empty string if nothing relevant.
        """
        if self._cron_skipped or not self._client:
            return ""

        if not query or not query.strip():
            return ""

        # Skip trivial prompts
        if self._is_trivial_prompt(query):
            return ""

        try:
            result = self._client.query(query)
            if not result:
                return ""

            # Truncate to context_tokens budget
            if self._config and self._config.context_tokens:
                budget_chars = self._config.context_tokens * 4
                if len(result) > budget_chars:
                    result = result[:budget_chars] + "\n\n[...truncated]"

            return sanitize_context(result)

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
        """Mirror built-in memory writes into gbrain."""
        if self._cron_skipped or not self._client:
            return
        if not self._config or not self._config.write_mirror:
            return

        try:
            import time

            timestamp = int(time.time())
            action_label = {"add": "added", "replace": "updated", "remove": "removed"}.get(
                action, action
            )

            slug = f"memory/{target}/{action_label}-{timestamp}"
            page = (
                f"# Hermes {target} memory: {action_label}\n\n"
                f"**Action:** {action}\n"
                f"**Target:** {target}\n"
                f"**Timestamp:** {timestamp}\n\n"
                f"{content}\n"
            )
            self._client.put(slug, page)

        except Exception as e:
            logger.debug("GBrain on_memory_write failed: %s", e)

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Optionally sync conversation turns to gbrain."""
        if self._cron_skipped or not self._client:
            return
        if not self._config or not self._config.sync_turns:
            return

        try:
            import time

            timestamp = int(time.time())
            slug = f"hermes/sessions/{self._session_id}/turn-{timestamp}"

            # Truncate long messages
            user_short = user_content[:1000] if len(user_content) > 1000 else user_content
            asst_short = assistant_content[:2000] if len(assistant_content) > 2000 else assistant_content

            page = (
                f"# Turn {timestamp}\n\n"
                f"**User:** {user_short}\n\n"
                f"**Assistant:** {asst_short}\n"
            )
            self._client.put(slug, page)

        except Exception as e:
            logger.debug("GBrain sync_turn failed: %s", e)

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        """Extract session summary to gbrain on session end."""
        if self._cron_skipped or not self._client:
            return

        # No LLM summarization here — just note the session end.
        # The model can use gbrain_put explicitly for richer summaries.
        try:
            import time
            timestamp = int(time.time())
            msg_count = len(messages)
            slug = f"hermes/sessions/{self._session_id}/end-{timestamp}"
            page = (
                f"# Session ended\n\n"
                f"**Session:** {self._session_id}\n"
                f"**Messages:** {msg_count}\n"
                f"**Ended:** {timestamp}\n"
            )
            self._client.put(slug, page)
        except Exception as e:
            logger.debug("GBrain on_session_end failed: %s", e)

    def get_config_schema(self) -> List[Dict[str, Any]]:
        return [
            {
                "key": "command",
                "description": "Path to gbrain CLI binary",
                "default": "gbrain",
            },
            {
                "key": "context_tokens",
                "description": "Max tokens of prefetch context to inject (≈ chars / 4)",
                "default": 2000,
            },
            {
                "key": "timeout",
                "description": "Timeout for gbrain CLI calls (seconds)",
                "default": 30,
            },
            {
                "key": "write_mirror",
                "description": "Mirror Hermes memory() writes into gbrain",
                "default": True,
            },
            {
                "key": "sync_turns",
                "description": "Sync conversation turns to gbrain",
                "default": False,
            },
        ]

    def save_config(self, values: Dict[str, Any], hermes_home: str) -> None:
        """Write config to gbrain.json."""
        from pathlib import Path
        from .config import GbrainConfig

        path = Path(hermes_home) / "gbrain.json"
        cfg = GbrainConfig.from_file(path) if path.exists() else GbrainConfig()
        for key, val in values.items():
            if hasattr(cfg, key):
                setattr(cfg, key, val)
        cfg.save(path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_trivial_prompt(query: str) -> bool:
        """Skip prefetch for trivial prompts (one-word, slash commands)."""
        q = query.strip().lower()
        if len(q) <= 3:
            return True
        if q.startswith("/"):
            return True
        trivial = {"ok", "yes", "no", "thanks", "thank you", "good", "got it", "cool"}
        return q in trivial
