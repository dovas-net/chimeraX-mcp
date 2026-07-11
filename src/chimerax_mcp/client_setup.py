"""Helpers for generating and installing client-specific MCP configs."""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
import tempfile
from pathlib import Path


SERVER_NAME = "chimerax"
SUPPORTED_PROFILES = ("full", "core")

REMOTE_ONLY_CLIENTS = {
    "chatgpt": "ChatGPT custom connectors/apps require a hosted remote MCP server.",
    "claude-remote": "Claude remote connectors require a hosted remote MCP server.",
}

CLIENT_ALIASES = {
    "claude-code": "claude-code",
    "claude_code": "claude-code",
    "claude desktop": "claude-desktop",
    "claude-desktop": "claude-desktop",
    "codex": "codex",
    "codex-cli": "codex",
    "codex-ide": "codex",
    "cursor": "cursor",
    "copilot": "copilot",
    "github-copilot": "copilot",
    "vscode-copilot": "copilot",
    "windsurf": "windsurf",
    "cline": "cline",
    "gemini": "gemini",
    "gemini-cli": "gemini",
    "continue": "continue",
    "continue.dev": "continue",
    "chatgpt": "chatgpt",
    "chatgpt-desktop": "chatgpt",
    "claude-remote": "claude-remote",
    "claude-web": "claude-remote",
    "claude-mobile": "claude-remote",
}

SUPPORTED_LOCAL_CLIENTS = (
    "claude-code",
    "claude-desktop",
    "codex",
    "cursor",
    "copilot",
    "windsurf",
    "cline",
    "gemini",
    "continue",
)


def normalize_client_name(client: str) -> str:
    """Normalize client aliases to a canonical identifier."""
    normalized = CLIENT_ALIASES.get(str(client).strip().lower())
    if normalized is None:
        valid = ", ".join(sorted(set(SUPPORTED_LOCAL_CLIENTS) | set(REMOTE_ONLY_CLIENTS)))
        raise ValueError(f"Unknown client '{client}'. Valid clients: {valid}")
    return normalized


def default_profile_for_client(client: str) -> str:
    """Return the recommended profile for a given client."""
    client = normalize_client_name(client)
    return "core" if client == "windsurf" else "full"


def _prefer_venv_python_symlink(python_path: str) -> str:
    """Prefer `.venv/bin/python` over `.venv/bin/python3.X` when both point to the same binary.

    `sys.executable` on macOS and Linux reports the fully-versioned name
    (e.g. `.../python3.14`). If the user later rebuilds their venv with a
    newer interpreter, a config pinned to `python3.14` breaks. The bare
    `python` symlink in the same directory is the stable handle.

    Only *fully-versioned* names (`python3.14`) are rewritten. Bare `python`
    and `python3` are already stable handles, so an explicitly-provided path
    like `/usr/bin/python3` is preserved verbatim.
    """
    try:
        p = Path(python_path)
        name = p.name
        if not re.match(r"^python\d+\.\d", name):
            return python_path
        symlink = p.parent / "python"
        if symlink.exists() and symlink.resolve() == p.resolve():
            return str(symlink)
    except OSError:
        pass
    return python_path


def build_stdio_command(
    profile: str = "full",
    python_path: str | None = None,
) -> tuple[str, list[str]]:
    """Return the local command and args for launching this MCP server."""
    if profile not in SUPPORTED_PROFILES:
        raise ValueError(f"Profile must be one of {SUPPORTED_PROFILES}")

    resolved = str(Path(python_path or sys.executable).expanduser())
    command = _prefer_venv_python_symlink(resolved)
    args = ["-m", "chimerax_mcp", "serve"]
    if profile == "core":
        args.extend(["--profile", "core"])
    return command, args


def default_config_path(client: str, platform: str | None = None) -> Path | None:
    """Return the default config path for a supported local client."""
    client = normalize_client_name(client)
    platform = platform or sys.platform
    home = Path.home()
    appdata = os.environ.get("APPDATA")

    if client == "claude-code":
        return None
    if client == "claude-desktop":
        if platform == "darwin":
            return home / "Library/Application Support/Claude/claude_desktop_config.json"
        if platform == "win32" and appdata:
            return Path(appdata) / "Claude/claude_desktop_config.json"
        return home / ".config/Claude/claude_desktop_config.json"
    if client == "cursor":
        return home / ".cursor/mcp.json"
    if client == "codex":
        return home / ".codex/config.toml"
    if client == "windsurf":
        return home / ".codeium/windsurf/mcp_config.json"
    if client == "gemini":
        return home / ".gemini/settings.json"
    if client == "continue":
        return home / ".continue/config.yaml"
    if client == "copilot":
        if platform == "darwin":
            return home / "Library/Application Support/Code/User/mcp.json"
        if platform == "win32" and appdata:
            return Path(appdata) / "Code/User/mcp.json"
        return home / ".config/Code/User/mcp.json"
    if client == "cline":
        if platform == "darwin":
            return (
                home
                / "Library/Application Support/Code/User/globalStorage"
                / "saoudrizwan.claude-dev/settings/cline_mcp_settings.json"
            )
        if platform == "win32" and appdata:
            return (
                Path(appdata)
                / "Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json"
            )
        return (
            home
            / ".config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json"
        )
    return None


def _json_server_config(
    client: str,
    command: str,
    args: list[str],
    timeout_sec: int,
) -> tuple[str, dict]:
    """Return (root_key, server_config) for JSON-based clients."""
    if client == "copilot":
        return "servers", {
            SERVER_NAME: {
                "type": "stdio",
                "command": command,
                "args": args,
            }
        }

    config: dict[str, object] = {
        "command": command,
        "args": args,
    }
    if client == "cline":
        config["disabled"] = False
    if client == "gemini":
        config["timeout"] = timeout_sec * 1000

    return "mcpServers", {SERVER_NAME: config}


def _render_json_document(client: str, command: str, args: list[str], timeout_sec: int) -> str:
    root_key, server_config = _json_server_config(client, command, args, timeout_sec)
    return json.dumps({root_key: server_config}, indent=2)


def _render_codex_toml(command: str, args: list[str], timeout_sec: int) -> str:
    args_text = json.dumps(args)
    return (
        f"[mcp_servers.{SERVER_NAME}]\n"
        f"command = {json.dumps(command)}\n"
        f"args = {args_text}\n"
        "enabled = true\n"
        f"tool_timeout_sec = {timeout_sec}\n"
    )


def _render_continue_yaml(command: str, args: list[str]) -> str:
    args_lines = "\n".join(f"      - {arg}" for arg in args)
    return (
        "mcpServers:\n"
        f"  - name: {SERVER_NAME}\n"
        f"    command: {command}\n"
        "    args:\n"
        f"{args_lines}\n"
    )


def render_config_for_client(
    client: str,
    *,
    profile: str | None = None,
    python_path: str | None = None,
    timeout_sec: int = 600,
) -> str:
    """Render a config snippet or setup command for a client."""
    client = normalize_client_name(client)
    if client in REMOTE_ONLY_CLIENTS:
        return REMOTE_ONLY_CLIENTS[client]

    profile = profile or default_profile_for_client(client)
    command, args = build_stdio_command(profile=profile, python_path=python_path)

    if client == "claude-code":
        escaped_command = shlex.quote(command)
        escaped_args = " ".join(shlex.quote(arg) for arg in args)
        return f"claude mcp add {SERVER_NAME} -- {escaped_command} {escaped_args}"
    if client in {"claude-desktop", "cursor", "copilot", "windsurf", "cline", "gemini"}:
        return _render_json_document(client, command, args, timeout_sec)
    if client == "codex":
        return _render_codex_toml(command, args, timeout_sec)
    if client == "continue":
        return _render_continue_yaml(command, args)

    raise ValueError(f"No config renderer implemented for client '{client}'")


def _atomic_write(path: Path, content: str) -> None:
    """Write text to `path` atomically, preserving the existing file's mode if any.

    Uses a temp file in the same directory so the final `os.replace` is atomic
    on POSIX (same filesystem, same inode-directory). If a file already exists
    at `path`, its permission bits are carried over to the replacement so that
    e.g. a 0600 `~/.codex/config.toml` stays 0600 after upsert.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    existing_mode: int | None = None
    try:
        existing_mode = path.stat().st_mode & 0o777
    except FileNotFoundError:
        pass

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        if existing_mode is not None:
            os.chmod(tmp_path, existing_mode)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def _upsert_json_config(
    path: Path,
    client: str,
    command: str,
    args: list[str],
    timeout_sec: int,
) -> None:
    """Merge a server entry into a JSON config file."""
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        data = json.loads(text) if text else {}
    else:
        data = {}

    root_key, server_config = _json_server_config(client, command, args, timeout_sec)
    existing_root = data.get(root_key)
    if not isinstance(existing_root, dict):
        existing_root = {}
    existing_root.update(server_config)
    data[root_key] = existing_root

    _atomic_write(path, json.dumps(data, indent=2) + "\n")


def _upsert_toml_section(path: Path, section_name: str, section_body: str) -> None:
    """Replace or append a TOML section by name."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    replacement = section_body.strip() + "\n"
    pattern = re.compile(
        rf"(?ms)^\[{re.escape(section_name)}\]\n.*?(?=^\[|\Z)"
    )

    if pattern.search(text):
        updated = pattern.sub(replacement, text).rstrip() + "\n"
    else:
        updated = text.rstrip()
        if updated:
            updated += "\n\n"
        updated += replacement

    _atomic_write(path, updated)


def _upsert_continue_yaml(path: Path, command: str, args: list[str]) -> None:
    """Append a Continue config block when one does not already exist."""
    block = _render_continue_yaml(command, args)

    if not path.exists():
        _atomic_write(path, block)
        return

    text = path.read_text(encoding="utf-8")
    if f"name: {SERVER_NAME}" in text:
        return

    entry = (
        f"  - name: {SERVER_NAME}\n"
        f"    command: {command}\n"
        "    args:\n"
        + "\n".join(f"      - {arg}" for arg in args)
        + "\n"
    )

    if "mcpServers:" in text:
        updated = text.rstrip() + "\n" + entry
    else:
        updated = text.rstrip() + "\n\n" + block
    _atomic_write(path, updated)


def setup_client_config(
    client: str,
    *,
    path: str | None = None,
    profile: str | None = None,
    python_path: str | None = None,
    timeout_sec: int = 600,
) -> str:
    """Install or update a local client config for this MCP server."""
    client = normalize_client_name(client)
    if client in REMOTE_ONLY_CLIENTS:
        raise ValueError(REMOTE_ONLY_CLIENTS[client])

    profile = profile or default_profile_for_client(client)
    command, args = build_stdio_command(profile=profile, python_path=python_path)

    if client == "claude-code":
        return render_config_for_client(
            client,
            profile=profile,
            python_path=python_path,
            timeout_sec=timeout_sec,
        )

    target_path = Path(path).expanduser() if path else default_config_path(client)
    if target_path is None:
        raise ValueError(
            f"No default config path is known for '{client}'. Use print-config or pass --path explicitly."
        )

    if client in {"claude-desktop", "cursor", "copilot", "windsurf", "cline", "gemini"}:
        _upsert_json_config(target_path, client, command, args, timeout_sec)
    elif client == "codex":
        _upsert_toml_section(
            target_path,
            f"mcp_servers.{SERVER_NAME}",
            _render_codex_toml(command, args, timeout_sec),
        )
    elif client == "continue":
        _upsert_continue_yaml(target_path, command, args)
    else:
        raise ValueError(f"Setup is not implemented for '{client}'")

    return f"Updated {client} config at {target_path}"
