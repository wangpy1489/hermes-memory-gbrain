"""Tests for the GBrain memory provider."""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from hermes_memory_gbrain.client import GbrainClient
from hermes_memory_gbrain.config import GbrainConfig


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

class TestGbrainConfig:

    def test_defaults(self):
        cfg = GbrainConfig()
        assert cfg.command == "gbrain"
        assert cfg.context_tokens == 2000
        assert cfg.write_mirror is True
        assert cfg.sync_turns is False

    def test_from_file_defaults_when_no_file(self, tmp_path):
        cfg = GbrainConfig.from_file(tmp_path / "nonexistent.json")
        assert cfg.command == "gbrain"

    def test_from_file_reads_values(self, tmp_path):
        path = tmp_path / "gbrain.json"
        path.write_text(json.dumps({
            "command": "/opt/gbrain",
            "context_tokens": 1000,
            "write_mirror": False,
        }))
        cfg = GbrainConfig.from_file(path)
        assert cfg.command == "/opt/gbrain"
        assert cfg.context_tokens == 1000
        assert cfg.write_mirror is False

    def test_save_and_reload(self, tmp_path):
        path = tmp_path / "gbrain.json"
        cfg = GbrainConfig(command="my-gbrain", timeout=10.0)
        cfg.save(path)

        loaded = GbrainConfig.from_file(path)
        assert loaded.command == "my-gbrain"
        assert loaded.timeout == 10.0


# ---------------------------------------------------------------------------
# Client tests
# ---------------------------------------------------------------------------

class TestGbrainClient:

    def test_is_available_when_binary_found(self, gbrain_client, mock_which):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert gbrain_client.is_available() is True

    def test_is_available_when_binary_not_found(self, gbrain_client):
        with patch("shutil.which", return_value=None):
            assert gbrain_client.is_available() is False

    def test_query_returns_formatted_context(self, gbrain_client, mock_subprocess_run):
        from tests.conftest import make_query_result, FakeCompletedProcess

        mock_subprocess_run.return_value = FakeCompletedProcess(
            returncode=0,
            stdout=make_query_result(["python-tips", "project-notes"]),
        )

        result = gbrain_client.query("python tips")
        assert "GBrain Context" in result
        assert "python-tips" in result
        assert "project-notes" in result

    def test_query_handles_timeout(self, gbrain_client):
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 5)):
            result = gbrain_client.query("test")
            assert result == ""

    def test_query_handles_error(self, gbrain_client, mock_subprocess_run):
        mock_subprocess_run.return_value = MagicMock(
            returncode=1, stderr="connection refused"
        )
        result = gbrain_client.query("test")
        assert result == ""

    def test_put_writes_content(self, gbrain_client, mock_subprocess_run):
        mock_subprocess_run.return_value = MagicMock(returncode=0)
        ok = gbrain_client.put("test/page", "# Hello\nWorld")
        assert ok is True

    def test_put_handles_failure(self, gbrain_client, mock_subprocess_run):
        mock_subprocess_run.return_value = MagicMock(returncode=1, stderr="error")
        ok = gbrain_client.put("test/page", "# Hello")
        assert ok is False

    def test_search_returns_results(self, gbrain_client, mock_subprocess_run):
        from tests.conftest import make_query_result, FakeCompletedProcess

        mock_subprocess_run.return_value = FakeCompletedProcess(
            returncode=0,
            stdout=make_query_result(["keyword-match"]),
        )
        result = gbrain_client.search("keyword")
        assert "GBrain Context" in result


# ---------------------------------------------------------------------------
# Provider tests
# ---------------------------------------------------------------------------

class TestGbrainProvider:

    def test_name(self, gbrain_provider):
        assert gbrain_provider.name == "gbrain"

    def test_is_available_false_when_no_gbrain(self, gbrain_provider):
        with patch("shutil.which", return_value=None):
            assert gbrain_provider.is_available() is False

    def test_get_tool_schemas_returns_two_tools(self, gbrain_provider):
        # Pretend client is available
        gbrain_provider._client = MagicMock()
        schemas = gbrain_provider.get_tool_schemas()
        names = [s["name"] for s in schemas]
        assert "gbrain_search" in names
        assert "gbrain_query" in names

    def test_get_tool_schemas_empty_when_no_client(self, gbrain_provider):
        schemas = gbrain_provider.get_tool_schemas()
        assert schemas == []

    def test_system_prompt_block_empty_when_no_client(self, gbrain_provider):
        assert gbrain_provider.system_prompt_block() == ""

    def test_system_prompt_block_returns_text(self, gbrain_provider):
        gbrain_provider._client = MagicMock()
        gbrain_provider._config = GbrainConfig()
        block = gbrain_provider.system_prompt_block()
        assert "GBrain Memory" in block

    def test_prefetch_skips_trivial_prompts(self, gbrain_provider):
        gbrain_provider._client = MagicMock()
        gbrain_provider._config = GbrainConfig()
        result = gbrain_provider.prefetch("ok")
        assert result == ""

    def test_prefetch_empty_when_no_client(self, gbrain_provider):
        assert gbrain_provider.prefetch("test query") == ""

    def test_prefetch_calls_query(self, gbrain_provider):
        gbrain_provider._client = MagicMock()
        # client.query() returns formatted text, not raw JSON
        gbrain_provider._client.query.return_value = (
            "## GBrain Context\n\n### Test Page\nContent about test-page."
        )
        gbrain_provider._config = GbrainConfig(context_tokens=2000)

        result = gbrain_provider.prefetch("what is python?")
        assert "GBrain Context" in result
        gbrain_provider._client.query.assert_called_once_with("what is python?")

    def test_on_memory_write_mirrors_to_gbrain(self, gbrain_provider):
        gbrain_provider._client = MagicMock()
        gbrain_provider._config = GbrainConfig(write_mirror=True)

        gbrain_provider.on_memory_write(
            action="add", target="memory", content="User prefers Python"
        )
        gbrain_provider._client.put.assert_called_once()

    def test_on_memory_write_skips_when_disabled(self, gbrain_provider):
        gbrain_provider._client = MagicMock()
        gbrain_provider._config = GbrainConfig(write_mirror=False)

        gbrain_provider.on_memory_write(
            action="add", target="memory", content="User prefers Python"
        )
        gbrain_provider._client.put.assert_not_called()

    def test_handle_tool_call_gbrain_search(self, gbrain_provider):
        gbrain_provider._client = MagicMock()
        gbrain_provider._client.search.return_value = "Found: result"

        result = gbrain_provider.handle_tool_call(
            "gbrain_search", {"query": "test", "max_results": 3}
        )
        data = json.loads(result)
        assert data["success"] is True
        assert "Found" in data["content"]

    def test_handle_tool_call_unknown(self, gbrain_provider):
        gbrain_provider._client = MagicMock()
        result = gbrain_provider.handle_tool_call("gbrain_fake", {})
        data = json.loads(result)
        assert data["success"] is False


# ---------------------------------------------------------------------------
# is_trivial_prompt tests
# ---------------------------------------------------------------------------

class TestTrivialPrompt:

    @pytest.mark.parametrize("prompt", [
        "ok", "yes", "no", "thanks", "got it", "cool",
        "/reset", "/new", "hi", "/help",
    ])
    def test_trivial(self, prompt):
        from hermes_memory_gbrain import GbrainMemoryProvider
        assert GbrainMemoryProvider._is_trivial_prompt(prompt) is True

    @pytest.mark.parametrize("prompt", [
        "what is python?",
        "帮我查一下 gbrain 怎么配置",
        "how do I set up a memory provider?",
    ])
    def test_not_trivial(self, prompt):
        from hermes_memory_gbrain import GbrainMemoryProvider
        assert GbrainMemoryProvider._is_trivial_prompt(prompt) is False
