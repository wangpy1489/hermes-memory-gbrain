"""Configuration for the GBrain memory provider.

Reads from ``$HERMES_HOME/gbrain.json``, falling back to defaults.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_CONTEXT_TOKENS = 2000
DEFAULT_COMMAND = "gbrain"
DEFAULT_TIMEOUT = 30.0  # seconds for CLI calls


@dataclass
class GbrainConfig:
    """Configuration for the GBrain memory provider."""

    # Path to gbrain binary
    command: str = DEFAULT_COMMAND

    # Max chars of prefetch context to inject (≈ tokens × 4)
    context_tokens: Optional[int] = DEFAULT_CONTEXT_TOKENS

    # Timeout for gbrain CLI calls (seconds)
    timeout: float = DEFAULT_TIMEOUT

    # Whether to mirror built-in memory writes into gbrain
    write_mirror: bool = True

    # Whether to sync conversation turns into gbrain
    sync_turns: bool = False

    # Raw config dict for anything else
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: Optional[Path] = None) -> GbrainConfig:
        """Load config from JSON file, falling back to defaults.

        Resolution order:
        1. ``$HERMES_HOME/gbrain.json`` (profile-scoped)
        2. Defaults
        """
        resolved: Path
        if path is not None:
            resolved = path
        else:
            try:
                from hermes_constants import get_hermes_home
                resolved = get_hermes_home() / "gbrain.json"
            except ImportError:
                resolved = Path.home() / ".hermes" / "gbrain.json"

        if not resolved.exists():
            return cls()

        try:
            raw = json.loads(resolved.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read %s: %s, using defaults", resolved, e)
            return cls()

        return cls(
            command=raw.get("command", DEFAULT_COMMAND),
            context_tokens=raw.get("context_tokens", DEFAULT_CONTEXT_TOKENS),
            timeout=float(raw.get("timeout", DEFAULT_TIMEOUT)),
            write_mirror=raw.get("write_mirror", True),
            sync_turns=raw.get("sync_turns", False),
            raw=raw,
        )

    def save(self, path: Optional[Path] = None) -> None:
        """Write config to JSON file."""
        resolved: Path
        if path is not None:
            resolved = path
        else:
            try:
                from hermes_constants import get_hermes_home
                resolved = get_hermes_home() / "gbrain.json"
            except ImportError:
                resolved = Path.home() / ".hermes" / "gbrain.json"

        data = {
            "command": self.command,
            "context_tokens": self.context_tokens,
            "timeout": self.timeout,
            "write_mirror": self.write_mirror,
            "sync_turns": self.sync_turns,
        }
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(json.dumps(data, indent=2), encoding="utf-8")
