import json
import os
import stat
import asyncio

from chimerax_mcp.client_setup import (
    _prefer_venv_python_symlink,
    build_stdio_command,
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


class TestVenvSymlinkPreference:
    def test_prefers_bare_python_symlink_in_venv(self, tmp_path):
        bin_dir = tmp_path / ".venv" / "bin"
        bin_dir.mkdir(parents=True)
        real = bin_dir / "python3.14"
        real.write_text("#!/bin/sh\nexit 0\n")
        real.chmod(0o755)
        symlink = bin_dir / "python"
        symlink.symlink_to(real.name)

        resolved = _prefer_venv_python_symlink(str(real))
        assert resolved == str(symlink)

    def test_keeps_path_when_no_sibling_symlink(self, tmp_path):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        real = bin_dir / "python3.14"
        real.write_text("#!/bin/sh\nexit 0\n")
        real.chmod(0o755)

        resolved = _prefer_venv_python_symlink(str(real))
        assert resolved == str(real)

    def test_does_not_substitute_unrelated_symlink(self, tmp_path):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        real = bin_dir / "python3.14"
        real.write_text("#!/bin/sh\nexit 0\n")
        real.chmod(0o755)
        other = bin_dir / "python-other"
        other.write_text("#!/bin/sh\nexit 0\n")
        other.chmod(0o755)
        (bin_dir / "python").symlink_to(other.name)

        resolved = _prefer_venv_python_symlink(str(real))
        assert resolved == str(real)

    def test_build_stdio_command_uses_symlink(self, tmp_path):
        bin_dir = tmp_path / ".venv" / "bin"
        bin_dir.mkdir(parents=True)
        real = bin_dir / "python3.14"
        real.write_text("#!/bin/sh\nexit 0\n")
        real.chmod(0o755)
        (bin_dir / "python").symlink_to(real.name)

        command, args = build_stdio_command(profile="full", python_path=str(real))
        assert command == str(bin_dir / "python")
        assert args == ["-m", "chimerax_mcp", "serve"]


class TestAtomicWritePreservesMode:
    def test_upsert_preserves_0600_mode(self, tmp_path):
        config_path = tmp_path / "config.toml"
        config_path.write_text("[other]\nvalue = 1\n", encoding="utf-8")
        os.chmod(config_path, 0o600)

        setup_client_config(
            "codex",
            path=str(config_path),
            profile="full",
            python_path="/usr/bin/python3",
            timeout_sec=600,
        )

        mode = stat.S_IMODE(config_path.stat().st_mode)
        assert mode == 0o600
        text = config_path.read_text(encoding="utf-8")
        assert "[other]" in text
        assert "[mcp_servers.chimerax]" in text

    def test_json_upsert_preserves_mode(self, tmp_path):
        config_path = tmp_path / "cursor.json"
        config_path.write_text('{"mcpServers": {}}\n', encoding="utf-8")
        os.chmod(config_path, 0o600)

        setup_client_config(
            "cursor",
            path=str(config_path),
            profile="core",
            python_path="/usr/bin/python3",
            timeout_sec=600,
        )

        mode = stat.S_IMODE(config_path.stat().st_mode)
        assert mode == 0o600

    def test_no_tempfile_leftover_on_success(self, tmp_path):
        config_path = tmp_path / "config.toml"
        setup_client_config(
            "codex",
            path=str(config_path),
            profile="full",
            python_path="/usr/bin/python3",
            timeout_sec=600,
        )
        leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".config.toml.")]
        assert leftovers == []


class TestCLIVersionFlag:
    def test_version_flag_prints_version(self, capsys):
        from chimerax_mcp import __version__
        from chimerax_mcp.cli import main

        exit_code = 0
        try:
            main(["--version"])
        except SystemExit as exc:
            exit_code = exc.code or 0

        captured = capsys.readouterr()
        assert __version__ in captured.out
        assert exit_code == 0
