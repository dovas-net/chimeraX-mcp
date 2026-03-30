"""Curated core-profile MCP server for lighter-weight clients."""

from __future__ import annotations

import atexit

from mcp.server.fastmcp import FastMCP

from chimerax_mcp.server import _sync_cleanup
import chimerax_mcp.server as full_server


CORE_TOOL_NAMES: tuple[str, ...] = (
    "run_command",
    "get_atomspec_guide",
    "open_structure",
    "close_models",
    "list_models",
    "get_model_info",
    "get_chain_info",
    "get_session_info",
    "list_chimerax_instances",
    "start_new_chimerax_session",
    "check_chimerax_status",
    "set_default_session",
    "show_hide_objects",
    "color_models",
    "set_style",
    "set_cartoon",
    "set_size",
    "set_transparency",
    "set_scene",
    "set_camera",
    "set_lighting",
    "set_clipping",
    "view_residue",
    "measure_distance",
    "measure_angle",
    "measure_torsion",
    "calculate_rmsd",
    "find_hbonds",
    "find_clashes",
    "align_structures",
    "select_atoms",
    "select_zone",
    "label_atoms",
    "label_2d",
    "create_surface",
    "color_surface",
    "set_volume_display",
    "fit_in_map",
    "get_sequence",
    "save_session",
    "open_session",
    "save_image",
    "record_movie",
    "list_chimerax_commands",
    "get_command_documentation",
)

mcp = FastMCP("ChimeraX Bridge (Core)")

for tool_name in CORE_TOOL_NAMES:
    mcp.add_tool(getattr(full_server, tool_name), name=tool_name)


def main() -> None:
    """Run the curated core-profile MCP server."""
    atexit.register(_sync_cleanup)
    mcp.run()
