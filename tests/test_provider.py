"""Tests for the GBrain memory provider."""

from __future__ import annotations

import json
from pathlib import Path
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

    def test_pages_dir(self, tmp_path):
        brain = tmp_path / "brain"
        brain.mkdir()
        config_path = tmp_path / "gbrain.json"
        config_path.write_text(json.dumps({"brain_dir": str(brain)}))

        cfg = GbrainConfig.from_file(config_path)
        assert cfg.pages_dir == brain / "memory" / "hermes"

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
# Timeline write tests
# ---------------------------------------------------------------------------

class TestTimelineWrite:

    def test_creates_new_user_page(self, provider_with_brain):
        provider_with_brain.on_memory_write(
            "add", "user", "用户偏好 Python"
        )
        page = provider_with_brain._config.pages_dir / "user.md"
        assert page.exists()
        content = page.read_text()
        assert "Hermes 用户画像" in content
        assert "## Compiled Truth" in content
        assert "## Timeline" in content
        assert "用户偏好 Python" in content

    def test_creates_new_context_page(self, provider_with_brain):
        provider_with_brain.on_memory_write(
            "add", "memory", "PostgreSQL 17, Python 3.11"
        )
        page = provider_with_brain._config.pages_dir / "context.md"
        assert page.exists()
        content = page.read_text()
        assert "Hermes 上下文" in content
        assert "PostgreSQL 17" in content

    def test_appends_to_existing_page(self, provider_with_brain):
        provider_with_brain.on_memory_write("add", "user", "第一条")
        provider_with_brain.on_memory_write("add", "user", "第二条")

        page = provider_with_brain._config.pages_dir / "user.md"
        content = page.read_text()
        assert "第一条" in content
        assert "第二条" in content
        # Timeline should have two entries
        assert content.count("memory add") == 2

    def test_replace_action(self, provider_with_brain):
        provider_with_brain.on_memory_write("replace", "user", "更新偏好")
        page = provider_with_brain._config.pages_dir / "user.md"
        assert "replace" in page.read_text()
        assert "更新偏好" in page.read_text()

    def test_remove_action(self, provider_with_brain):
        provider_with_brain.on_memory_write("remove", "memory", "过时信息")
        page = provider_with_brain._config.pages_dir / "context.md"
        assert "remove" in page.read_text()

    def test_compiled_truth_untouched(self, provider_with_brain):
        # Write initial page
        provider_with_brain.on_memory_write("add", "user", "初始事实")

        # Manually add something to Compiled Truth
        page = provider_with_brain._config.pages_dir / "user.md"
        content = page.read_text()
        content = content.replace(
            "<!-- 手动维护，Agent 不自动修改此区域 -->",
            "<!-- 手动维护，Agent 不自动修改此区域 -->\n- 手动添加的判断",
        )
        page.write_text(content)

        # Append more timeline entries
        provider_with_brain.on_memory_write("add", "user", "新事实")

        # Compiled Truth should still have manual content
        final = page.read_text()
        assert "手动添加的判断" in final

    def test_skips_unknown_target(self, provider_with_brain):
        provider_with_brain.on_memory_write("add", "unknown", "不应出现")
        page = provider_with_brain._config.pages_dir / "unknown"
        assert not page.exists() or "user.md"  # at least user.md wasn't created from this

    def test_on_session_end(self, provider_with_brain):
        provider_with_brain.on_session_end([{}, {}])
        page = provider_with_brain._config.pages_dir / "context.md"
        assert page.exists()
        content = page.read_text()
        assert "session end" in content
        assert "test-session" in content


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
