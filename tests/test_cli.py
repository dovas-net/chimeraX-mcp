import json
import asyncio

from chimerax_mcp.client_setup import (
    default_config_path,
    default_profile_for_client,
    normalize_client_name,
    render_config_for_client,
    setup_client_config,
)
from chimerax_mcp.core_server import CORE_TOOL_NAMES, mcp as core_mcp


class TestClientNormalization:
    def test_normalizes_aliases(self):
        assert normalize_client_name("codex-cli") == "codex"
        assert normalize_client_name("ChatGPT-Desktop") == "chatgpt"

    def test_windsurf_defaults_to_core(self):
        assert default_profile_for_client("windsurf") == "core"


class TestConfigRendering:
    def test_renders_codex_config(self):
        snippet = render_config_for_client(
            "codex",
            profile="core",
            python_path="/usr/bin/python3",
            timeout_sec=600,
        )
        assert '[mcp_servers.chimerax]' in snippet
        assert 'command = "/usr/bin/python3"' in snippet
        assert '--profile' in snippet
        assert 'tool_timeout_sec = 600' in snippet

    def test_renders_remote_client_message(self):
        snippet = render_config_for_client("chatgpt")
        assert "hosted remote MCP server" in snippet

    def test_returns_platform_default_path(self):
        path = default_config_path("claude-desktop", platform="darwin")
        assert "claude_desktop_config.json" in str(path)


class TestClientSetup:
    def test_writes_cursor_json_config(self, tmp_path):
        config_path = tmp_path / "cursor.json"
        message = setup_client_config(
            "cursor",
            path=str(config_path),
            profile="core",
            python_path="/usr/bin/python3",
            timeout_sec=600,
        )
        data = json.loads(config_path.read_text(encoding="utf-8"))
        server = data["mcpServers"]["chimerax"]
        assert server["command"] == "/usr/bin/python3"
        assert server["args"] == ["-m", "chimerax_mcp", "serve", "--profile", "core"]
        assert "Updated cursor config" in message

    def test_upserts_codex_config(self, tmp_path):
        config_path = tmp_path / "config.toml"
        config_path.write_text("[other]\nvalue = 1\n", encoding="utf-8")
        setup_client_config(
            "codex",
            path=str(config_path),
            profile="full",
            python_path="/usr/bin/python3",
            timeout_sec=600,
        )
        text = config_path.read_text(encoding="utf-8")
        assert "[other]" in text
        assert "[mcp_servers.chimerax]" in text
        assert 'command = "/usr/bin/python3"' in text


class TestCoreProfile:
    def test_core_profile_is_curated(self):
        assert len(CORE_TOOL_NAMES) < 100
        assert "open_structure" in CORE_TOOL_NAMES
        assert len(asyncio.run(core_mcp.list_tools())) == len(CORE_TOOL_NAMES)
