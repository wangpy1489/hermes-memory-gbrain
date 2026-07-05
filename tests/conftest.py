"""Test fixtures and helpers for hermes-memory-gbrain."""

from __future__ import annotations

import sys
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class FakeCompletedProcess:
    """Mock for subprocess.CompletedProcess."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture
def mock_subprocess_run():
    """Patch subprocess.run to return fake results."""
    with patch("subprocess.run") as mock_run:
        yield mock_run


@pytest.fixture
def mock_which():
    """Patch shutil.which to find gbrain."""
    with patch("shutil.which", return_value="/usr/local/bin/gbrain"):
        yield


@pytest.fixture
def gbrain_client():
    """Create a GbrainClient with a short timeout."""
    from hermes_memory_gbrain.client import GbrainClient
    return GbrainClient(command="gbrain", timeout=5.0)


@pytest.fixture
def gbrain_provider():
    """Create a GbrainMemoryProvider for testing."""
    from hermes_memory_gbrain import GbrainMemoryProvider
    return GbrainMemoryProvider()


def make_query_result(slugs=None):
    """Build a fake gbrain query JSON result."""
    if slugs is None:
        slugs = []
    items = []
    for i, slug in enumerate(slugs):
        items.append({
            "slug": slug,
            "title": f"Test {slug}",
            "content": f"Content of {slug} for testing purposes.",
            "score": 0.95 - (i * 0.1),
        })
    return json.dumps({"results": items})
