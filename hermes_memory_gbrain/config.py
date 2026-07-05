"""Configuration for the GBrain memory provider.

Reads from ``$HERMES_HOME/gbrain.json``.  All paths are resolved
relative to the config file or use absolute paths.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class GbrainConfig:
    """Configuration for the GBrain memory provider."""

    def __init__(
        self,
        brain_dir: str = "",
        command: str = "gbrain",
        timeout: float = 30.0,
        raw: Optional[dict] = None,
    ):
        self.brain_dir = Path(brain_dir) if brain_dir else None
        self.command = command
        self.timeout = timeout
        self.raw = raw or {}

    def is_valid(self) -> bool:
        return self.brain_dir is not None and self.brain_dir.is_dir()

    @classmethod
    def from_file(cls, path: Optional[Path] = None) -> GbrainConfig:
        """Load config from JSON file, falling back to defaults."""
        resolved = cls._resolve_path(path)

        if not resolved or not resolved.exists():
            return cls()

        try:
            raw = json.loads(resolved.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read %s: %s", resolved, e)
            return cls()

        brain_dir = raw.get("brain_dir", "")
        if brain_dir:
            brain_dir = str(Path(brain_dir).expanduser().resolve())

        return cls(
            brain_dir=brain_dir,
            command=raw.get("command", "gbrain"),
            timeout=float(raw.get("timeout", 30)),
            raw=raw,
        )

    @classmethod
    def _resolve_path(cls, path: Optional[Path] = None) -> Optional[Path]:
        if path is not None:
            return path
        try:
            from hermes_constants import get_hermes_home
            return get_hermes_home() / "gbrain.json"
        except ImportError:
            return Path.home() / ".hermes" / "gbrain.json"

    def save(self, path: Optional[Path] = None) -> None:
        """Write config to JSON file."""
        resolved = self._resolve_path(path)
        if not resolved:
            return
        data = {
            "brain_dir": str(self.brain_dir) if self.brain_dir else "",
            "command": self.command,
            "timeout": self.timeout,
        }
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(json.dumps(data, indent=2), encoding="utf-8")
