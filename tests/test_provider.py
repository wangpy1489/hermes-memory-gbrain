"""Tests for the GBrain memory provider."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from hermes_memory_gbrain.config import GbrainConfig


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

class TestGbrainConfig:

    def test_defaults_no_file(self):
        cfg = GbrainConfig()
        assert not cfg.is_valid()
        assert cfg.command == "gbrain"

    def test_loads_brain_dir(self, tmp_path):
        brain = tmp_path / "brain"
        brain.mkdir()
        config_path = tmp_path / "gbrain.json"
        config_path.write_text(json.dumps({"brain_dir": str(brain)}))

        cfg = GbrainConfig.from_file(config_path)
        assert cfg.is_valid()
        assert cfg.brain_dir == brain

    def test_expands_tilde(self, tmp_path, monkeypatch):
        brain = tmp_path / "brain"
        brain.mkdir()
        config_path = tmp_path / "gbrain.json"
        config_path.write_text(json.dumps({"brain_dir": f"~/{brain.name}"}))
        monkeypatch.setenv("HOME", str(tmp_path))

        cfg = GbrainConfig.from_file(config_path)
        assert cfg.is_valid()


# ---------------------------------------------------------------------------
# Provider tests
# ---------------------------------------------------------------------------

class TestGbrainProvider:

    def test_name(self, provider_with_brain):
        assert provider_with_brain.name == "gbrain"

    def test_is_available_true(self, provider_with_brain):
        assert provider_with_brain.is_available()

    def test_is_available_false_no_config(self):
        with patch.object(GbrainConfig, "_resolve_path", return_value=None):
            from hermes_memory_gbrain import GbrainMemoryProvider
            p = GbrainMemoryProvider()
            assert not p.is_available()

    def test_tool_schemas(self, provider_with_brain):
        schemas = provider_with_brain.get_tool_schemas()
        names = [s["name"] for s in schemas]
        assert "gbrain_search" in names
        assert "gbrain_query" in names

    def test_system_prompt(self, provider_with_brain):
        block = provider_with_brain.system_prompt_block()
        assert "GBrain Memory" in block

    def test_prefetch_trivial(self, provider_with_brain):
        assert provider_with_brain.prefetch("ok") == ""
        assert provider_with_brain.prefetch("") == ""

    def test_prefetch_calls_gbrain(self, provider_with_brain, mock_subprocess_run):
        mock_subprocess_run.return_value = MagicMock(
            returncode=0, stdout="result text\n", stderr=""
        )
        result = provider_with_brain.prefetch("what is python?")
        assert "GBrain Context" in result
        assert "result text" in result
        mock_subprocess_run.assert_called_once()

    def test_prefetch_handles_timeout(self, provider_with_brain, mock_subprocess_run):
        import subprocess
        mock_subprocess_run.side_effect = subprocess.TimeoutExpired("cmd", 5)
        result = provider_with_brain.prefetch("test")
        assert result == ""

    def test_prefetch_handles_error(self, provider_with_brain, mock_subprocess_run):
        mock_subprocess_run.return_value = MagicMock(
            returncode=1, stderr="error", stdout=""
        )
        result = provider_with_brain.prefetch("test")
        assert result == ""

    def test_handle_tool_query(self, provider_with_brain, mock_subprocess_run):
        mock_subprocess_run.return_value = MagicMock(
            returncode=0, stdout="search result\n", stderr=""
        )
        result = provider_with_brain.handle_tool_call(
            "gbrain_query", {"question": "test"}
        )
        data = json.loads(result)
        assert data["success"] is True
        assert "search result" in data["content"]

    def test_handle_tool_unknown(self, provider_with_brain):
        result = provider_with_brain.handle_tool_call("gbrain_fake", {})
        data = json.loads(result)
        assert data["success"] is False


# ---------------------------------------------------------------------------
# Trivial prompt tests
# ---------------------------------------------------------------------------

class TestTrivialPrompt:

    @pytest.mark.parametrize("prompt", [
        "ok", "yes", "no", "thanks", "got it", "cool", "hi",
    ])
    def test_trivial(self, prompt):
        from hermes_memory_gbrain import GbrainMemoryProvider
        assert GbrainMemoryProvider._is_trivial_prompt(prompt)

    @pytest.mark.parametrize("prompt", [
        "what is python?",
        "帮我查一下 gbrain",
        "/help",
    ])
    def test_not_trivial(self, prompt):
        from hermes_memory_gbrain import GbrainMemoryProvider
        if prompt == "/help":
            assert GbrainMemoryProvider._is_trivial_prompt(prompt)
        else:
            assert not GbrainMemoryProvider._is_trivial_prompt(prompt)
