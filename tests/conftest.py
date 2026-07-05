"""Test fixtures for hermes-memory-gbrain."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def tmp_brain(tmp_path):
    """Create a temporary brain directory."""
    brain = tmp_path / "brain"
    brain.mkdir()
    return brain


@pytest.fixture
def provider_with_brain(tmp_brain):
    """Create a provider with a temp brain dir + config."""
    from hermes_memory_gbrain import GbrainMemoryProvider
    from hermes_memory_gbrain.config import GbrainConfig

    # Write config
    config_path = tmp_brain.parent / "gbrain.json"
    config_path.write_text(
        f'{{"brain_dir": "{tmp_brain}", "command": "gbrain", "timeout": 5}}'
    )

    # Monkey-patch config resolution
    with patch.object(GbrainConfig, "_resolve_path", return_value=config_path):
        provider = GbrainMemoryProvider()
        provider.initialize("test-session", platform="cli")
        yield provider


@pytest.fixture
def mock_subprocess_run():
    """Patch subprocess.run."""
    with patch("hermes_memory_gbrain.subprocess.run") as mock:
        yield mock
