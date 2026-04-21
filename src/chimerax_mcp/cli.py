"""Command-line interface for running and configuring chimerax-mcp."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from chimerax_mcp import __version__
from chimerax_mcp.chimera_rest import (
    DEFAULT_CHIMERAX_PORT,
    DEFAULT_TIMEOUT,
    check_existing_rest_server,
    cleanup,
    find_chimerax_executable,
    list_running_instances,
)
from chimerax_mcp.client_setup import (
    SUPPORTED_LOCAL_CLIENTS,
    default_config_path,
    normalize_client_name,
    render_config_for_client,
    setup_client_config,
)
from chimerax_mcp.core_server import CORE_TOOL_NAMES
from chimerax_mcp.docs import get_docs_path
import chimerax_mcp.server as full_server


def _serve(profile: str) -> int:
    """Run the selected MCP server profile."""
    if profile == "core":
        from chimerax_mcp.core_server import main as profile_main
    else:
        from chimerax_mcp.server import main as profile_main

    profile_main()
    return 0


async def _doctor_report() -> tuple[int, str]:
    """Collect an environment report for local setup troubleshooting."""
    lines: list[str] = []

    try:
        exe = find_chimerax_executable()
        docs_path = get_docs_path()
        instances = await list_running_instances()
        found_existing, existing_port = await check_existing_rest_server()
        full_tool_count = len(await full_server.mcp.list_tools())
        core_tool_count = len(CORE_TOOL_NAMES)

        lines.append(f"chimerax-mcp version: {__version__}")
        lines.append(f"Python executable: {sys.executable}")
        lines.append(f"Package root: {Path(__file__).resolve().parent}")
        lines.append(f"Default ChimeraX port: {DEFAULT_CHIMERAX_PORT}")
        lines.append(f"Default command timeout: {DEFAULT_TIMEOUT}s")
        lines.append(f"Full profile tools: {full_tool_count}")
        lines.append(f"Core profile tools: {core_tool_count}")
        lines.append("")

        if exe:
            lines.append(f"[OK] ChimeraX executable: {exe}")
        else:
            lines.append("[WARN] ChimeraX executable not found")

        if docs_path:
            lines.append(f"[OK] ChimeraX docs path: {docs_path}")
        else:
            lines.append("[WARN] ChimeraX docs path not found")

        if found_existing:
            lines.append(f"[OK] Reachable ChimeraX REST instance on port {existing_port}")
        else:
            lines.append("[WARN] No reachable ChimeraX REST instance detected")

        if instances:
            lines.append("Running instances:")
            for port, info in sorted(instances.items()):
                label = info.get("session_name") or "unnamed"
                auto = " auto-discovered" if info.get("auto_discovered") else ""
                lines.append(f"  - port {port}: {label}{auto}")
        else:
            lines.append("Running instances: none")

        lines.append("")
        lines.append("Recommended next steps:")
        lines.append("  1. For a first-time install, run `./install.sh <client-name>` from the repo root.")
        lines.append("  2. To preview a config snippet without writing, run `chimerax-mcp print-config codex`.")
        lines.append("  3. To add or re-sync a client config, run `chimerax-mcp setup <client-name>`.")
        lines.append("  4. For lighter clients (Windsurf), use `chimerax-mcp serve --profile core`.")

        exit_code = 0 if exe or found_existing else 1
        return exit_code, "\n".join(lines)
    finally:
        await cleanup()


def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="chimerax-mcp",
        description="Run or configure the ChimeraX MCP server.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"chimerax-mcp {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command")

    serve_parser = subparsers.add_parser("serve", help="Run the MCP server")
    serve_parser.add_argument(
        "--profile",
        choices=("full", "core"),
        default="full",
        help="Tool profile to expose",
    )

    doctor_parser = subparsers.add_parser("doctor", help="Inspect local setup and ChimeraX availability")
    doctor_parser.set_defaults(command="doctor")

    print_parser = subparsers.add_parser("print-config", help="Print an MCP config snippet for a client")
    print_parser.add_argument("client", help="Client name, e.g. codex, claude-desktop, cursor")
    print_parser.add_argument(
        "--profile",
        choices=("full", "core"),
        default=None,
        help="Tool profile to expose (defaults to the recommended profile for the client)",
    )
    print_parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Suggested client timeout in seconds where applicable",
    )
    print_parser.add_argument(
        "--python",
        dest="python_path",
        default=None,
        help="Python executable to embed in the config snippet",
    )

    setup_parser = subparsers.add_parser("setup", help="Install or update a local client MCP config")
    setup_parser.add_argument("client", help="Client name, e.g. codex, claude-desktop, cursor")
    setup_parser.add_argument(
        "--profile",
        choices=("full", "core"),
        default=None,
        help="Tool profile to expose (defaults to the recommended profile for the client)",
    )
    setup_parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Suggested client timeout in seconds where applicable",
    )
    setup_parser.add_argument(
        "--python",
        dest="python_path",
        default=None,
        help="Python executable to embed in the installed config",
    )
    setup_parser.add_argument(
        "--path",
        default=None,
        help="Override the default config path for the client",
    )

    clients_parser = subparsers.add_parser("list-clients", help="List supported local clients")
    clients_parser.set_defaults(command="list-clients")

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        return _serve("full")

    if args.command == "serve":
        return _serve(args.profile)

    if args.command == "doctor":
        code, report = asyncio.run(_doctor_report())
        print(report)
        return code

    if args.command == "list-clients":
        print("\n".join(sorted(SUPPORTED_LOCAL_CLIENTS)))
        return 0

    if args.command == "print-config":
        try:
            client = normalize_client_name(args.client)
            snippet = render_config_for_client(
                client,
                profile=args.profile,
                python_path=args.python_path,
                timeout_sec=args.timeout,
            )
            default_path = default_config_path(client)
            if default_path is not None:
                print(f"# Default config path: {default_path}")
            print(snippet)
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    if args.command == "setup":
        try:
            message = setup_client_config(
                args.client,
                path=args.path,
                profile=args.profile,
                python_path=args.python_path,
                timeout_sec=args.timeout,
            )
            print(message)
            return 0
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    parser.error(f"Unknown command: {args.command}")
    return 2
