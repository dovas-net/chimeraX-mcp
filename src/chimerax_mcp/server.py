"""FastMCP server for ChimeraX with all tool definitions."""

import asyncio
import atexit
import json
import logging
import os
from typing import Optional

from mcp.server.fastmcp import FastMCP

from chimerax_mcp.chimera_rest import (
    run_chimerax_command,
    is_chimerax_running,
    start_chimerax,
    find_chimerax_executable,
    list_running_instances,
    cleanup,
    parse_info_json,
)
import chimerax_mcp.chimera_rest as rest
from chimerax_mcp.formatting import (
    format_chimerax_response,
    format_single_model_info,
    quote_chimerax_arg,
    validate_atomspec,
)
from chimerax_mcp.docs import (
    get_atomspec_guide as _get_atomspec_guide,
    list_available_commands,
    get_command_doc,
)

logger = logging.getLogger("chimerax_mcp.tools")

mcp = FastMCP("ChimeraX Bridge")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _sync_cleanup():
    """Synchronously close the shared aiohttp session at exit."""
    try:
        asyncio.run(cleanup())
    except RuntimeError:
        # Event loop may still be running during shutdown; close connector directly
        import chimerax_mcp.chimera_rest as _rest
        if _rest._session is not None and not _rest._session.closed:
            if _rest._session.connector is not None:
                _rest._session.connector.close()


def main():
    atexit.register(_sync_cleanup)
    mcp.run()


def _looks_like_local_path(value: str) -> bool:
    """Heuristically detect when an open target is a local file path."""
    if not value:
        return False

    text = str(value)
    lower = text.lower()
    known_extensions = (
        ".pdb",
        ".cif",
        ".mmcif",
        ".mrc",
        ".map",
        ".ccp4",
        ".pdbqt",
        ".cxs",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".tif",
        ".tiff",
        ".mp4",
        ".mov",
        ".avi",
        ".csv",
        ".defattr",
    )

    return (
        text.startswith(("~", ".", os.sep))
        or "/" in text
        or "\\" in text
        or any(char.isspace() for char in text)
        or lower.endswith(known_extensions)
    )


# ---------------------------------------------------------------------------
# Tool 1: run_command
# ---------------------------------------------------------------------------

@mcp.tool()
async def run_command(command: str, session_id: Optional[int] = None) -> str:
    """Execute any ChimeraX command directly. Use this tool if you don't find another tool
    that suits your needs.

    When constructing commands that specify objects (models, chains, residues, atoms):
    - Use get_atomspec_guide() to learn the correct atomspec syntax
    - Common atomspecs: #1 (model), #1/A (chain), #1/A:100 (residue), @ca (atom type)

    To see a list of all commands, use the list_chimerax_commands() tool.
    For command syntax help, use get_command_documentation(command_name).

    Common command patterns by category:

    SURFACES:
      surface #1                          -- molecular surface for model 1
      surface #1/A                        -- surface for chain A only
      surface close #1                    -- remove surface
      coulombic #1                        -- electrostatic surface coloring
      mlp #1                              -- hydrophobicity surface coloring
      transparency #1 50 target s         -- set surface 50% transparent

    LABELS & ANNOTATIONS:
      label #1/A:100 text "Active Site"   -- label a residue
      label #1/A:100 height 2.0           -- adjust label size
      label delete #1                     -- remove labels
      2dlabels text "Title" x 0.5 y 0.95 size 24 -- 2D text overlay

    CAMERA & VIEW:
      turn y 90                           -- rotate 90 deg around Y axis
      turn x 30                           -- tilt 30 deg around X axis
      zoom 2                              -- zoom in 2x
      zoom 0.5                            -- zoom out
      view #1/A:100                       -- center on residue 100
      view orient                         -- reset to default orientation
      clip near -5 far 5                  -- clipping planes

    SELECTION:
      select ligand                       -- select all ligands
      select #1/A:100-200                 -- select residue range
      ~select                             -- clear selection
      select zone #1:ATP 5 residues true  -- select within 5A of ATP

    EXPORT & SAVE:
      save ~/structure.pdb #1             -- export as PDB
      save ~/session.cxs                  -- save session
      save ~/movie.mp4                    -- save spin movie

    SEQUENCE:
      sequence chain #1/A                 -- show sequence viewer for chain A

    MAPS & VOLUMES:
      volume #2 step 1 sdLevel 5.0        -- set map display level
      volume #2 style mesh                -- mesh representation
      volume #2 transparency 0.5          -- transparent map
      fitmap #1 inMap #2                  -- fit model into map

    MISC:
      log metadata #1                     -- show metadata (EMDB ID, resolution, etc.)
      minimize                            -- energy minimization
      morph #1,2                          -- create morph between conformations

    Args:
        command: ChimeraX command to execute (e.g., 'open 1gcn', 'color #1/A red')
        session_id: ChimeraX session port (defaults to primary session)
    """
    result = await run_chimerax_command(command, session_id)
    session_info = f" on session {session_id}" if session_id else ""
    context = f"Command executed{session_info}: {command}"
    return format_chimerax_response(result, context)


# ---------------------------------------------------------------------------
# Tool 2: get_atomspec_guide
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_atomspec_guide() -> str:
    """Get the complete guide for ChimeraX atomspec (object specification) syntax.

    Use this tool whenever you need to specify objects in ChimeraX commands, such as:
    - Selecting specific models, chains, residues, or atoms
    - Creating distance-based selections (zones)
    - Combining selections with logical operators
    - Using built-in classifications (protein, ligand, helix, etc.)
    - Querying by attributes

    Always consult this when constructing object specifications for commands like:
    color, show, hide, select, style, view, and any command that acts on objects.
    """
    return _get_atomspec_guide()


# ---------------------------------------------------------------------------
# Helper: _get_chain_info_helper
# ---------------------------------------------------------------------------

async def _get_chain_info_helper(
    model_id: str, chain_id: str, session_id: Optional[int] = None
) -> tuple[str, dict]:
    """Query chain info via a single ``info chains`` call.

    ChimeraX 1.11.1 returns all chain data (chain_id, sequence,
    polymer type, residues list) in one response.

    Returns (formatted_text, chain_data_dict).
    """
    result = await run_chimerax_command(
        f"info chains #{model_id}/{chain_id}", session_id
    )
    rows = parse_info_json(result)

    chain_data: dict = {}
    if rows:
        row = rows[0]
        chain_data["chain_id"] = row.get("value", row.get("chain_id", chain_id))
        chain_data["sequence"] = row.get("sequence", "")
        chain_data["polymer_type"] = row.get("polymer type", "unknown")
        residues = row.get("residues", [])
        chain_data["num_residues"] = len(residues)
    else:
        chain_data["chain_id"] = chain_id
        chain_data["sequence"] = ""
        chain_data["polymer_type"] = "N/A"
        chain_data["num_residues"] = 0

    # Format the chain info
    seq_len = len(chain_data["sequence"])
    lines = [
        f"Chain {chain_data['chain_id']} of model #{model_id}:",
        f"  Polymer type: {chain_data['polymer_type']}",
        f"  Residues: {chain_data['num_residues']}",
        f"  Sequence length: {seq_len}",
    ]

    text = "\n".join(lines)
    return text, chain_data


# ---------------------------------------------------------------------------
# Tool 3: list_models
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_models(session_id: Optional[int] = None) -> str:
    """List all models currently loaded in ChimeraX.

    Returns model IDs, names, types, visibility, and basic stats.

    Args:
        session_id: ChimeraX session port (defaults to primary session)
    """
    # Step 1: Get name + class for each model
    info_result = await run_chimerax_command("info models", session_id)
    rows = parse_info_json(info_result)
    if not rows:
        return "No models loaded"

    # Build lookup by spec
    models_by_spec: dict[str, dict] = {}
    for row in rows:
        spec = row.get("spec", "")
        models_by_spec[spec] = {
            "spec": spec,
            "name": row.get("value", row.get("name", "unknown")),
            "class": row.get("class", ""),
        }

    # Step 2: Get visibility (display attribute)
    try:
        display_result = await run_chimerax_command(
            "info models attribute display", session_id
        )
        for row in parse_info_json(display_result):
            spec = row.get("spec", "")
            if spec in models_by_spec:
                models_by_spec[spec]["display"] = row.get("value", False)
    except Exception:
        pass

    # Step 3: Get atom counts
    try:
        atoms_result = await run_chimerax_command(
            "info models attribute num_atoms", session_id
        )
        for row in parse_info_json(atoms_result):
            spec = row.get("spec", "")
            if spec in models_by_spec:
                models_by_spec[spec]["num_atoms"] = row.get("value")
    except Exception:
        pass

    # Format output
    models = list(models_by_spec.values())
    output_lines = [f"Models loaded: {len(models)}\n"]
    for model in models:
        model_lines = format_single_model_info(model)
        output_lines.extend(model_lines)
        output_lines.append("")  # blank line between models

    return "\n".join(output_lines).strip()


# ---------------------------------------------------------------------------
# Tool 4: get_shown
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_shown(session_id: Optional[int] = None) -> str:
    """Get visibility/display status of all models in ChimeraX.

    Returns a JSON summary showing which models are currently displayed.

    Args:
        session_id: ChimeraX session port (defaults to primary session)
    """
    result = await run_chimerax_command("info models attribute display", session_id)
    rows = parse_info_json(result)

    models = []
    for row in rows:
        models.append({
            "spec": row.get("spec", "?"),
            "display": row.get("value", False),
        })

    return json.dumps({"models": models}, indent=2)


# ---------------------------------------------------------------------------
# Tool 5: get_model_info
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_model_info(
    model_id: str, session_id: Optional[int] = None
) -> str:
    """Get detailed information about a specific model, including per-chain details.

    Args:
        model_id: Model identifier (e.g., '1' for model #1)
        session_id: ChimeraX session port (defaults to primary session)
    """
    spec = f"#{model_id}"
    model_data: dict = {"spec": spec}

    # Query 1: name + class
    try:
        result = await run_chimerax_command(f"info models {spec}", session_id)
        rows = parse_info_json(result)
        if not rows:
            return f"Model {spec} not found (no models loaded)"
        row = rows[0]
        model_data["name"] = row.get("value", row.get("name", "unknown"))
        model_data["class"] = row.get("class", "")
    except Exception as e:
        return f"Model {spec} not found: {e}"

    # Queries 2-5: individual attributes
    attr_queries = [
        ("num_atoms", "num_atoms"),
        ("num_residues", "num_residues"),
        ("num_bonds", "num_bonds"),
        ("display", "display"),
    ]
    for attr_name, key in attr_queries:
        try:
            result = await run_chimerax_command(
                f"info models {spec} attribute {attr_name}", session_id
            )
            rows = parse_info_json(result)
            if rows:
                model_data[key] = rows[0].get("value")
        except Exception:
            pass

    # Format summary
    output_lines = format_single_model_info(model_data)
    num_residues = model_data.get("num_residues")
    num_bonds = model_data.get("num_bonds")
    if num_residues is not None:
        output_lines.append(f"  {num_residues} residues")
    if num_bonds is not None:
        output_lines.append(f"  {num_bonds} bonds")

    # Query 6: chain details in one call
    try:
        chain_result = await run_chimerax_command(
            f"info chains {spec}", session_id
        )
        chain_rows = parse_info_json(chain_result)
        if chain_rows:
            output_lines.append(f"\nChain details ({len(chain_rows)} chains):")
            for crow in chain_rows:
                cid = crow.get("value", crow.get("chain_id", "?"))
                ptype = crow.get("polymer type", "unknown")
                seq = crow.get("sequence", "")
                residues = crow.get("residues", [])
                output_lines.append(
                    f"  Chain {cid} ({ptype}): {len(residues)} residues, "
                    f"sequence length {len(seq)}"
                )
    except Exception:
        pass

    return "\n".join(output_lines)


# ---------------------------------------------------------------------------
# Tool 6: get_chain_info
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_chain_info(
    model_id: str, chain_id: str, session_id: Optional[int] = None
) -> str:
    """Get detailed information about a specific chain in a model.

    Args:
        model_id: Model identifier (e.g., '1' for model #1)
        chain_id: Chain identifier (e.g., 'A')
        session_id: ChimeraX session port (defaults to primary session)
    """
    text, _data = await _get_chain_info_helper(model_id, chain_id, session_id)
    return text


# ---------------------------------------------------------------------------
# Tool 7: color_models
# ---------------------------------------------------------------------------

@mcp.tool()
async def color_models(
    color: str, target: str = "#1", session_id: Optional[int] = None
) -> str:
    """Color models, chains, residues, or atoms in ChimeraX.

    Args:
        color: Color name or hex value (e.g., 'red', 'blue', '#FF0000', 'cornflowerblue')
        target: Atomspec of what to color (default: '#1', the first model).
                Use get_atomspec_guide() for syntax.
        session_id: ChimeraX session port (defaults to primary session)
    """
    target = validate_atomspec(target)
    command = f"color {target} {color}"
    result = await run_chimerax_command(command, session_id)
    context = f"Colored {target} with {color}"
    return format_chimerax_response(result, context)


# ---------------------------------------------------------------------------
# Tool 8: view_residue
# ---------------------------------------------------------------------------

@mcp.tool()
async def view_residue(
    model: str,
    chain: str,
    residue: str,
    session_id: Optional[int] = None,
) -> str:
    """Center the view on a specific residue and set it as the center of rotation.

    Args:
        model: Model ID (e.g., '1')
        chain: Chain ID (e.g., 'A')
        residue: Residue number (e.g., '100')
        session_id: ChimeraX session port (defaults to primary session)
    """
    spec = f"#{model}/{chain}:{residue}"

    # Center view on residue
    await run_chimerax_command(f"view {spec}", session_id)

    # Set center of rotation
    result = await run_chimerax_command(f"cofr {spec}", session_id)

    context = f"View centered on {spec}"
    return format_chimerax_response(result, context)


# ---------------------------------------------------------------------------
# Tool 9: list_chimerax_commands
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_chimerax_commands() -> str:
    """List all available ChimeraX commands.

    Returns a list of command names that can be used with run_command()
    or looked up with get_command_documentation().
    """
    commands = list_available_commands()
    if not commands:
        return (
            "Could not find ChimeraX command documentation. "
            "ChimeraX may not be installed or the documentation directory was not found."
        )
    header = f"Available ChimeraX commands ({len(commands)}):\n"
    return header + ", ".join(commands)


# ---------------------------------------------------------------------------
# Tool 10: get_command_documentation
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_command_documentation(command_name: str) -> str:
    """Get detailed documentation for a specific ChimeraX command.

    Args:
        command_name: Name of the ChimeraX command (e.g., 'open', 'color', 'surface').
                      Use list_chimerax_commands() to see available commands.
    """
    return get_command_doc(command_name)


# ---------------------------------------------------------------------------
# Tool 11: list_chimerax_instances
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_chimerax_instances() -> str:
    """List all detected running ChimeraX instances.

    Scans known instances and common ports (8080-8089) for running
    ChimeraX REST servers.
    """
    instances = await list_running_instances()
    if not instances:
        return "No running ChimeraX instances detected"

    lines = [f"Running ChimeraX instances: {len(instances)}\n"]
    for port, info in instances.items():
        name = info.get("session_name", "unnamed")
        auto = " (auto-discovered)" if info.get("auto_discovered") else ""
        is_default = " [DEFAULT]" if port == rest._default_port else ""
        lines.append(f"  Port {port}: {name}{auto}{is_default}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool 12: start_new_chimerax_session
# ---------------------------------------------------------------------------

@mcp.tool()
async def start_new_chimerax_session(
    session_name: Optional[str] = None, port: Optional[int] = None
) -> str:
    """Start a new ChimeraX instance with REST API enabled.

    Args:
        session_name: Optional name for the session (for identification)
        port: Optional specific port to use (auto-selects if not given)
    """
    exe = find_chimerax_executable()
    if exe is None:
        return (
            "ChimeraX executable not found. Please ensure ChimeraX is installed. "
            "On macOS, it should be in /Applications/ChimeraX*.app"
        )

    success, actual_port = await start_chimerax(
        port=port, session_name=session_name, force_new=True
    )

    if success:
        name_str = f" ({session_name})" if session_name else ""
        return (
            f"ChimeraX session started successfully{name_str} on port {actual_port}.\n"
            f"Use session_id={actual_port} to target this instance, "
            f"or set_default_session({actual_port}) to make it the default."
        )
    else:
        return (
            f"Failed to start ChimeraX on port {actual_port}. "
            "The instance may not have started within the timeout period. "
            "Try starting ChimeraX manually and running: "
            f"remotecontrol rest start port {actual_port} json true log true"
        )


# ---------------------------------------------------------------------------
# Tool 13: check_chimerax_status
# ---------------------------------------------------------------------------

@mcp.tool()
async def check_chimerax_status(session_id: Optional[int] = None) -> str:
    """Check if a ChimeraX instance is running and responsive.

    Args:
        session_id: Port to check (defaults to primary session)
    """
    port = session_id if session_id is not None else rest._default_port
    running = await is_chimerax_running(port)

    if running:
        is_default = " (default session)" if port == rest._default_port else ""
        return f"ChimeraX is running on port {port}{is_default}"
    else:
        return (
            f"ChimeraX is NOT running on port {port}. "
            "Use start_new_chimerax_session() to start one, "
            "or list_chimerax_instances() to find running instances."
        )


# ---------------------------------------------------------------------------
# Tool 14: set_default_session
# ---------------------------------------------------------------------------

@mcp.tool()
async def set_default_session(session_id: int) -> str:
    """Set the default ChimeraX session for commands without explicit session_id.

    Args:
        session_id: ChimeraX session port to use as default
    """
    if not await is_chimerax_running(session_id):
        return f"No ChimeraX instance running on port {session_id}"

    old_default = rest._default_port
    rest._default_port = session_id

    session_name = "unknown session"
    if session_id in rest._instances:
        session_name = rest._instances[session_id].get(
            "session_name", f"session_{session_id}"
        )

    return (
        f"Default session changed from port {old_default} "
        f"to port {session_id} ({session_name})"
    )


# ---------------------------------------------------------------------------
# Tool 15: open_structure
# ---------------------------------------------------------------------------

@mcp.tool()
async def open_structure(
    identifier: str,
    format: str = "auto-detect",
    fetch_emdb_map: bool = False,
    session_id: Optional[int] = None,
) -> str:
    """Open a molecular structure file or fetch from PDB

    Hints:
    - If your user wants to look at both a structure and the density map, set fetch_emdb_map=True
    - After opening a structure, run get_shown() to see the default representation

    Args:
        identifier: PDB ID (e.g., '1gcn') or file path to open
        format: File format if needed (pdb, cif, etc.), defaults to auto-detect
        fetch_emdb_map: If True, also fetch the corresponding EMDB map
        session_id: ChimeraX session port (defaults to primary session)
    """
    if fetch_emdb_map:
        valid_formats = ["auto-detect", "pdb", "cif", "mmcif"]
        if format not in valid_formats:
            return f"Error: fetch_emdb_map=True only works with PDB or mmCIF formats. Specified format '{format}' is not compatible."

    open_target = quote_chimerax_arg(identifier) if _looks_like_local_path(identifier) else identifier
    command = f"open {open_target}" if format == "auto-detect" else f"open {open_target} format {format}"
    if fetch_emdb_map:
        command += " fetchEmdbMap true"

    result = await run_chimerax_command(command, session_id)
    session_info = f" in session {session_id}" if session_id else ""
    context = f"Opened structure: {identifier}{session_info}"
    if fetch_emdb_map:
        context += " (with EMDB map)"
    return format_chimerax_response(result, context)


# ---------------------------------------------------------------------------
# Tool 16: save_image
# ---------------------------------------------------------------------------

@mcp.tool()
async def save_image(
    filename: str = "",
    width: int = 1920,
    height: int = 1080,
    supersample: int = 3,
    transparent_background: bool = False,
    session_id: Optional[int] = None,
) -> str:
    """Save a screenshot of the current view

    Before saving, clear selection with run_command('~select') to avoid green highlights.

    Args:
        filename: Output filename (e.g., 'structure.png'). If empty, auto-generates a timestamped name in /tmp.
        width: Image width in pixels (default: 1920)
        height: Image height in pixels (default: 1080)
        supersample: Supersampling factor for higher quality (default: 3)
        transparent_background: If True, save with transparent background (default: False)
        session_id: ChimeraX session port (defaults to primary session)
    """
    if not filename:
        import time
        filename = f"/tmp/chimerax_{int(time.time())}.png"

    command = (
        f"save {quote_chimerax_arg(filename)} width {width} height {height} "
        f"supersample {supersample}"
    )
    if transparent_background:
        command += " transparentBackground true"

    result = await run_chimerax_command(command, session_id)
    session_info = f" from session {session_id}" if session_id else ""
    context = f"Saved image: {filename}{session_info} ({width}x{height}, supersample {supersample})"
    return format_chimerax_response(result, context)


# ---------------------------------------------------------------------------
# Tool 17: show_hide_objects
# ---------------------------------------------------------------------------

@mcp.tool()
async def show_hide_objects(
    action: str,
    atomspec: str,
    target: str,
    session_id: Optional[int] = None,
) -> str:
    """Show or hide a specified selection of objects' representation.

    For the target, use one or more of the following letters:
    - a: atoms
    - b: bonds
    - c: cartoons/ribbons
    - s: surfaces
    - p: pseudobonds
    - m: models (use for hiding maps)

    Examples:
        - Show atoms+bonds in model 1: action='show', atomspec='#1', target='ab'
        - Hide everything in chain A: action='hide', atomspec='#1/A', target='abcs'
        - Show ribbons in residues 1-50: action='show', atomspec='#2/B:1-50', target='c'

    Important:
        - Before showing a representation for the first time, hide all representations first
        - After show/hide, check the response for affected count to verify correctness

    Args:
        action: 'show' or 'hide'
        atomspec: Object specification (use get_atomspec_guide() for syntax)
        target: What to show/hide (combination of a, b, c, s, p, m)
        session_id: ChimeraX session port (defaults to primary session)
    """
    if action not in ["show", "hide"]:
        raise ValueError("Action must be 'show' or 'hide'")
    atomspec = validate_atomspec(atomspec)
    if any(letter not in "abcpsm" for letter in target):
        raise ValueError("Target must be one or more of 'a', 'b', 'p', 'c', 's', 'm'")

    # Select first for feedback on affected count
    import re as _re
    select_result = await run_chimerax_command(f"select {atomspec}", session_id)
    note_logs = select_result.get("logs", {}).get("note", [])
    counts_string = "unknown count"
    for note in note_logs:
        if note and _re.search(r"\d+\s+(atom|bond|residue|model|pseudobond)", note):
            counts_string = note.replace(" selected", "")
            break
        elif note and "Nothing" in note:
            counts_string = "Nothing"
            break

    if counts_string == "Nothing":
        raise ValueError(f"No objects found matching atomspec: {atomspec}")

    command = f"{action} {atomspec} target {target}"
    result = await run_chimerax_command(command, session_id)

    if action == "show":
        model_result = await run_chimerax_command(f"show {atomspec} target m", session_id)
        # Merge logs
        combined_logs = {}
        for res in [result, model_result]:
            for level, messages in res.get("logs", {}).items():
                combined_logs.setdefault(level, []).extend(messages)
        result = {
            "return_values": result.get("return_values", []) + model_result.get("return_values", []),
            "json_values": result.get("json_values", []) + model_result.get("json_values", []),
            "logs": combined_logs,
        }

    # Clear the feedback selection so it does not leave green highlights in
    # subsequent renders (see the save_image guidance about clearing selection).
    await run_chimerax_command("~select", session_id)

    context = f"Success: {command}\nThis action affected {counts_string}"
    return format_chimerax_response(result, context)


# ---------------------------------------------------------------------------
# Tool 18: measure_distance
# ---------------------------------------------------------------------------

@mcp.tool()
async def measure_distance(atom1: str, atom2: str, session_id: Optional[int] = None) -> str:
    """Measure the distance between two atoms or atomspecs.

    Args:
        atom1: Atomspec for first point (e.g., '#1/A:100@CA')
        atom2: Atomspec for second point (e.g., '#1/A:200@CA')
        session_id: ChimeraX session port (defaults to primary session)
    """
    atom1, atom2 = validate_atomspec(atom1), validate_atomspec(atom2)
    command = f"distance {atom1} {atom2}"
    result = await run_chimerax_command(command, session_id)
    context = f"Distance measurement: {atom1} to {atom2}"
    return format_chimerax_response(result, context)


# ---------------------------------------------------------------------------
# Tool 19: find_hbonds
# ---------------------------------------------------------------------------

@mcp.tool()
async def find_hbonds(target: str = "all", inter_model: bool = False, session_id: Optional[int] = None) -> str:
    """Find hydrogen bonds in a structure.

    Args:
        target: Atomspec to analyze (default: 'all')
        inter_model: If True, find H-bonds between different models (default: False)
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"hbonds {target}"
    if inter_model:
        command += " interModel true"
    result = await run_chimerax_command(command, session_id)
    context = f"Hydrogen bond analysis for {target}"
    return format_chimerax_response(result, context)


# ---------------------------------------------------------------------------
# Tool 20: find_clashes
# ---------------------------------------------------------------------------

@mcp.tool()
async def find_clashes(target: str, restrict: str = "both", overlap_cutoff: float = 0.6, session_id: Optional[int] = None) -> str:
    """Find steric clashes or contacts in a structure.

    Args:
        target: Atomspec to check for clashes
        restrict: 'both' (clashes within target) or 'any' (clashes with anything)
        overlap_cutoff: Minimum overlap in Angstroms for a clash (default: 0.6)
        session_id: ChimeraX session port (defaults to primary session)
    """
    target = validate_atomspec(target)
    command = f"clashes {target} restrict {restrict} overlapCutoff {overlap_cutoff}"
    result = await run_chimerax_command(command, session_id)
    context = f"Clash analysis for {target} (restrict={restrict}, cutoff={overlap_cutoff})"
    return format_chimerax_response(result, context)


# ---------------------------------------------------------------------------
# Tool 21: align_structures
# ---------------------------------------------------------------------------

@mcp.tool()
async def align_structures(match_model: str, ref_model: str, chain_pairing: str = "bb", session_id: Optional[int] = None) -> str:
    """Align two structures using matchmaker (structural alignment).

    Args:
        match_model: Model to move (e.g., '#2')
        ref_model: Reference model to align to (e.g., '#1')
        chain_pairing: 'bb' (best-best chain pairing) or 'sc' (specific chain)
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"matchmaker {match_model} to {ref_model} pairing {chain_pairing}"
    result = await run_chimerax_command(command, session_id)
    context = f"Structural alignment: {match_model} aligned to {ref_model}"
    return format_chimerax_response(result, context)


# ---------------------------------------------------------------------------
# Tool 22: predict_structure
# ---------------------------------------------------------------------------

@mcp.tool()
async def predict_structure(sequence: str, method: str = "alphafold", session_id: Optional[int] = None) -> str:
    """Predict a protein structure from an amino acid sequence.

    Args:
        sequence: Amino acid sequence (e.g., 'MKTLLILAVL...')
        method: Prediction method - 'alphafold' or 'esmfold' (default: 'alphafold')
        session_id: ChimeraX session port (defaults to primary session)
    """
    if method not in ("alphafold", "esmfold"):
        raise ValueError(f"Method must be 'alphafold' or 'esmfold', got '{method}'")

    valid_aa = set("ACDEFGHIKLMNPQRSTVWY")
    seq_upper = sequence.upper().strip()
    if not seq_upper or not all(c in valid_aa for c in seq_upper):
        raise ValueError(f"Invalid amino acid sequence. Use only standard amino acid letters: {''.join(sorted(valid_aa))}")

    command = f"{method} predict {seq_upper}"
    result = await run_chimerax_command(command, session_id, timeout=300)
    context = f"Structure prediction ({method}) for sequence ({len(seq_upper)} residues)"
    return format_chimerax_response(result, context)


# ---------------------------------------------------------------------------
# Tool 23: set_scene
# ---------------------------------------------------------------------------

@mcp.tool()
async def set_scene(
    background: Optional[str] = None,
    lighting: Optional[str] = None,
    silhouettes: Optional[bool] = None,
    camera: Optional[str] = None,
    session_id: Optional[int] = None,
) -> str:
    """Set scene properties for publication-quality rendering.

    Only specified parameters are changed; others remain unchanged.

    Args:
        background: Background color (e.g., 'white', 'black', '#f0f0f0')
        lighting: Lighting preset ('default', 'soft', 'full', 'flat')
        silhouettes: Enable edge outlines (True/False)
        camera: Camera type - 'perspective' (mono) or 'orthographic' (ortho);
            native ChimeraX modes ('mono', 'ortho', '360', 'stereo') also accepted
        session_id: ChimeraX session port (defaults to primary session)
    """
    commands = []
    if background is not None:
        commands.append(f"set bgColor {background}")
    if lighting is not None:
        commands.append(f"lighting {lighting}")
    if silhouettes is not None:
        commands.append(f"set silhouettes {'true' if silhouettes else 'false'}")
    if camera is not None:
        # ChimeraX's `camera` command uses 'mono'/'ortho', not the human-friendly
        # 'perspective'/'orthographic' this tool documents — map them.
        camera_mode = {"perspective": "mono", "orthographic": "ortho"}.get(
            camera.lower(), camera
        )
        commands.append(f"camera {camera_mode}")

    if not commands:
        return "No scene properties specified. Provide at least one of: background, lighting, silhouettes, camera."

    all_logs: dict = {}
    for cmd in commands:
        result = await run_chimerax_command(cmd, session_id)
        for level, messages in result.get("logs", {}).items():
            all_logs.setdefault(level, []).extend(messages)

    summary = "Scene updated:\n" + "\n".join(f"  - {cmd}" for cmd in commands)
    combined_result = {"return_values": [], "json_values": [], "logs": all_logs}
    return format_chimerax_response(combined_result, summary)


# ---------------------------------------------------------------------------
# Tool 24: close_models
# ---------------------------------------------------------------------------

@mcp.tool()
async def close_models(target: str = "all", session_id: Optional[int] = None) -> str:
    """Close (remove) models from the ChimeraX session.

    Args:
        target: Atomspec of models to close (e.g., '#1', '#2,3', 'all')
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"close {target}"
    result = await run_chimerax_command(command, session_id)
    context = f"Closed models: {target}"
    return format_chimerax_response(result, context)


# ---------------------------------------------------------------------------
# Tool 25: get_session_info
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_session_info(session_id: Optional[int] = None) -> str:
    """Get a complete overview of the current ChimeraX session.

    Combines model list, visibility state, and instance status in one call.
    Use this as a first call to understand what's currently loaded and displayed.

    Args:
        session_id: ChimeraX session port (defaults to primary session)
    """
    output = []

    # Instance status
    port = session_id if session_id is not None else None
    if port:
        running = await is_chimerax_running(port)
        output.append(f"Session on port {port}: {'running' if running else 'not running'}")
    else:
        output.append("Using auto-discovered session")

    # Model list (reuse list_models for complete info including atom counts)
    try:
        models_text = await list_models(session_id)
        output.append(f"\n{models_text}")
    except Exception as e:
        output.append(f"\nCould not retrieve model info: {e}")

    return "\n".join(output)


# ---------------------------------------------------------------------------
# Tool 26: measure_angle
# ---------------------------------------------------------------------------

@mcp.tool()
async def measure_angle(atom1: str, atom2: str, atom3: str, session_id: Optional[int] = None) -> str:
    """Measure the angle formed by three atoms.

    Args:
        atom1: Atomspec for first atom
        atom2: Atomspec for vertex atom (center of angle)
        atom3: Atomspec for third atom
        session_id: ChimeraX session port (defaults to primary session)
    """
    atom1, atom2, atom3 = validate_atomspec(atom1), validate_atomspec(atom2), validate_atomspec(atom3)
    command = f"angle {atom1} {atom2} {atom3}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Angle: {atom1} - {atom2} - {atom3}")


# ---------------------------------------------------------------------------
# Tool 27: measure_torsion
# ---------------------------------------------------------------------------

@mcp.tool()
async def measure_torsion(atom1: str, atom2: str, atom3: str, atom4: str, session_id: Optional[int] = None) -> str:
    """Measure the dihedral (torsion) angle formed by four atoms.

    Args:
        atom1: Atomspec for first atom
        atom2: Atomspec for second atom
        atom3: Atomspec for third atom
        atom4: Atomspec for fourth atom
        session_id: ChimeraX session port (defaults to primary session)
    """
    atom1, atom2, atom3, atom4 = (validate_atomspec(a) for a in [atom1, atom2, atom3, atom4])
    command = f"torsion {atom1} {atom2} {atom3} {atom4}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Torsion: {atom1} - {atom2} - {atom3} - {atom4}")


# ---------------------------------------------------------------------------
# Tool 28: measure_sasa
# ---------------------------------------------------------------------------

@mcp.tool()
async def measure_sasa(target: str = "all", session_id: Optional[int] = None) -> str:
    """Calculate solvent-accessible surface area (SASA).

    Args:
        target: Atomspec to measure (default: 'all')
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"measure sasa {target}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"SASA for {target}")


# ---------------------------------------------------------------------------
# Tool 29: measure_center
# ---------------------------------------------------------------------------

@mcp.tool()
async def measure_center(target: str = "all", session_id: Optional[int] = None) -> str:
    """Calculate the center of mass of a selection.

    Args:
        target: Atomspec to measure (default: 'all')
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"measure center {target}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Center of mass for {target}")


# ---------------------------------------------------------------------------
# Tool 30: measure_buried_area
# ---------------------------------------------------------------------------

@mcp.tool()
async def measure_buried_area(target1: str, target2: str, session_id: Optional[int] = None) -> str:
    """Calculate buried solvent-accessible surface area between two sets of atoms.

    Args:
        target1: Atomspec for first group of atoms
        target2: Atomspec for second group of atoms
        session_id: ChimeraX session port (defaults to primary session)
    """
    target1, target2 = validate_atomspec(target1), validate_atomspec(target2)
    command = f"measure buriedarea {target1} withAtoms2 {target2}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Buried area between {target1} and {target2}")


# ---------------------------------------------------------------------------
# Tool 31: get_sequence
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_sequence(model_id: str, chain_id: str, session_id: Optional[int] = None) -> str:
    """Get the amino acid or nucleotide sequence of a chain.

    Returns the sequence in FASTA-like format with chain metadata.

    Args:
        model_id: Model identifier (e.g., '1' for #1)
        chain_id: Chain identifier (e.g., 'A')
        session_id: ChimeraX session port (defaults to primary session)
    """
    result = await run_chimerax_command(f"info chains #{model_id}/{chain_id}", session_id)
    rows = parse_info_json(result)
    if not rows:
        return f"No sequence data for chain {chain_id} in model #{model_id}"

    row = rows[0]
    sequence = row.get("sequence", "")
    polymer_type = row.get("polymer type", "unknown")
    chain_name = row.get("value", chain_id)

    if not sequence:
        return f"Chain {chain_name} has no sequence data"

    header = f">Chain {chain_name} | Model #{model_id} | {polymer_type} | {len(sequence)} residues"
    seq_lines = [sequence[i:i+80] for i in range(0, len(sequence), 80)]
    return header + "\n" + "\n".join(seq_lines)


# ---------------------------------------------------------------------------
# Tool 32: blast_search
# ---------------------------------------------------------------------------

@mcp.tool()
async def blast_search(query: str, database: str = "pdb", session_id: Optional[int] = None) -> str:
    """Run a BLAST protein search from a sequence or chain.

    Args:
        query: Amino acid sequence or atomspec (e.g., '#1/A')
        database: Database to search ('pdb' or 'nr', default: 'pdb')
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"blastprotein {query} database {database}"
    result = await run_chimerax_command(command, session_id, timeout=120)
    query_display = f"{query[:50]}..." if len(query) > 50 else query
    return format_chimerax_response(result, f"BLAST search ({database}): {query_display}")


# ---------------------------------------------------------------------------
# Tool 33: swap_residue
# ---------------------------------------------------------------------------

@mcp.tool()
async def swap_residue(atomspec: str, new_residue: str, session_id: Optional[int] = None) -> str:
    """Mutate a residue to a different amino acid type (swap sidechain).

    Args:
        atomspec: Atomspec for the residue to mutate (e.g., '#1/A:100')
        new_residue: Three-letter code for the new residue (e.g., 'ALA', 'GLY', 'PHE')
        session_id: ChimeraX session port (defaults to primary session)
    """
    atomspec = validate_atomspec(atomspec)
    command = f"swapaa {atomspec} {new_residue}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Swapped {atomspec} to {new_residue}")


# ---------------------------------------------------------------------------
# Tool 34: add_hydrogens
# ---------------------------------------------------------------------------

@mcp.tool()
async def add_hydrogens(target: str = "all", session_id: Optional[int] = None) -> str:
    """Add hydrogen atoms to a structure.

    Args:
        target: Atomspec to add hydrogens to (default: 'all')
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"addh {target}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Added hydrogens to {target}")


# ---------------------------------------------------------------------------
# Tool 35: minimize_structure
# ---------------------------------------------------------------------------

@mcp.tool()
async def minimize_structure(target: str = "all", steps: int = 100, session_id: Optional[int] = None) -> str:
    """Run energy minimization on a structure.

    Args:
        target: Atomspec to minimize (default: 'all')
        steps: Number of minimization steps (default: 100)
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"minimize {target} steps {steps}"
    result = await run_chimerax_command(command, session_id, timeout=300)
    return format_chimerax_response(result, f"Minimized {target} ({steps} steps)")


# ---------------------------------------------------------------------------
# Tool 36: fit_in_map
# ---------------------------------------------------------------------------

@mcp.tool()
async def fit_in_map(model: str, map_model: str, session_id: Optional[int] = None) -> str:
    """Fit an atomic model into a density map.

    Args:
        model: Atomspec for the atomic model to fit (e.g., '#1')
        map_model: Atomspec for the map/volume (e.g., '#2')
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"fitmap {model} inMap {map_model}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Fit {model} into map {map_model}")


# ---------------------------------------------------------------------------
# Tool 37: measure_surface_area
# ---------------------------------------------------------------------------

@mcp.tool()
async def measure_surface_area(target: str, session_id: Optional[int] = None) -> str:
    """Measure the surface area of a molecular surface.

    Args:
        target: Atomspec for the surface to measure (e.g., '#1')
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"measure area {target}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Surface area of {target}")


# ---------------------------------------------------------------------------
# Tool 38: measure_map_stats
# ---------------------------------------------------------------------------

@mcp.tool()
async def measure_map_stats(map_model: str, session_id: Optional[int] = None) -> str:
    """Get statistics for a density map (min, max, mean, RMS, etc.).

    Args:
        map_model: Atomspec for the map/volume model (e.g., '#2')
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"measure mapstats {map_model}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Map statistics for {map_model}")


# ---------------------------------------------------------------------------
# Tool 39: select_atoms
# ---------------------------------------------------------------------------

@mcp.tool()
async def select_atoms(
    atomspec: str, mode: str = "set", session_id: Optional[int] = None
) -> str:
    """Select atoms, residues, chains, or models in ChimeraX.

    Args:
        atomspec: What to select (e.g., '#1/A', 'ligand', '#1/A:100-200')
        mode: Selection mode - 'set' (replace), 'add' (extend), 'subtract' (remove), 'clear' (deselect all)
        session_id: ChimeraX session port (defaults to primary session)
    """
    if mode == "clear":
        result = await run_chimerax_command("~select", session_id)
        return format_chimerax_response(result, "Selection cleared")

    atomspec = validate_atomspec(atomspec)
    if mode == "set":
        command = f"select {atomspec}"
    elif mode == "add":
        command = f"select add {atomspec}"
    elif mode == "subtract":
        command = f"select subtract {atomspec}"
    else:
        raise ValueError(f"Mode must be 'set', 'add', 'subtract', or 'clear', got '{mode}'")

    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Selected ({mode}): {atomspec}")


# ---------------------------------------------------------------------------
# Tool 40: select_zone
# ---------------------------------------------------------------------------

@mcp.tool()
async def select_zone(
    origin: str,
    distance: float,
    target_type: str = "residues",
    session_id: Optional[int] = None,
) -> str:
    """Select everything within a distance of a target specification.

    Args:
        origin: Atomspec for the center of the zone (e.g., '#1:ATP', '#1/A:100')
        distance: Distance in Angstroms for the selection zone
        target_type: What to select - 'atoms' or 'residues' (default: 'residues')
        session_id: ChimeraX session port (defaults to primary session)
    """
    origin = validate_atomspec(origin)
    if target_type not in ("atoms", "residues"):
        raise ValueError(f"target_type must be 'atoms' or 'residues', got '{target_type}'")

    command = f"select zone {origin} {distance} {target_type} true"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Selected {target_type} within {distance}A of {origin}")


# ---------------------------------------------------------------------------
# Tool 41: label_atoms
# ---------------------------------------------------------------------------

@mcp.tool()
async def label_atoms(
    atomspec: str,
    text: str = "",
    attribute: str = "",
    height: float = 1.0,
    color: str = "",
    delete: bool = False,
    session_id: Optional[int] = None,
) -> str:
    """Add or remove text labels on atoms or residues.

    Args:
        atomspec: What to label (e.g., '#1/A:100', 'ligand')
        text: Label text (if empty, uses default atom/residue name)
        attribute: Show an attribute instead of text (e.g., 'residue_name', 'bfactor')
        height: Label height in Angstroms (default: 1.0)
        color: Label color (e.g., 'white', 'black')
        delete: If True, remove labels instead of adding them
        session_id: ChimeraX session port (defaults to primary session)
    """
    atomspec = validate_atomspec(atomspec)
    if delete:
        command = f"label delete {atomspec}"
    else:
        command = f"label {atomspec}"
        if text:
            command += f" text {quote_chimerax_arg(text)}"
        if attribute:
            command += f" attribute {attribute}"
        command += f" height {height}"
        if color:
            command += f" color {color}"

    result = await run_chimerax_command(command, session_id)
    action = "Removed labels from" if delete else "Labeled"
    return format_chimerax_response(result, f"{action} {atomspec}")


# ---------------------------------------------------------------------------
# Tool 42: label_2d
# ---------------------------------------------------------------------------

@mcp.tool()
async def label_2d(
    text: str,
    x: float = 0.5,
    y: float = 0.95,
    size: int = 24,
    color: str = "white",
    session_id: Optional[int] = None,
) -> str:
    """Add a 2D text overlay on the viewport (for titles, annotations).

    Coordinates are fractional: (0,0) is bottom-left, (1,1) is top-right.

    Args:
        text: Text to display
        x: Horizontal position (0.0-1.0, default: 0.5 = center)
        y: Vertical position (0.0-1.0, default: 0.95 = near top)
        size: Font size in points (default: 24)
        color: Text color (default: 'white')
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = (
        f"2dlabels text {quote_chimerax_arg(text)} xpos {x} ypos {y} "
        f"size {size} color {color}"
    )
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Added 2D label: \"{text}\"")


# ---------------------------------------------------------------------------
# Tool 43: save_session
# ---------------------------------------------------------------------------

@mcp.tool()
async def save_session(
    filename: str, session_id: Optional[int] = None
) -> str:
    """Save the current ChimeraX session to a file.

    Args:
        filename: Path to save the session (e.g., '~/my_session.cxs'). Extension .cxs is added if missing.
        session_id: ChimeraX session port (defaults to primary session)
    """
    if not filename.endswith(".cxs"):
        filename += ".cxs"
    command = f"save {quote_chimerax_arg(filename)}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Session saved: {filename}")


# ---------------------------------------------------------------------------
# Tool 44: open_session
# ---------------------------------------------------------------------------

@mcp.tool()
async def open_session(
    filename: str, session_id: Optional[int] = None
) -> str:
    """Open a previously saved ChimeraX session file.

    Args:
        filename: Path to the session file (e.g., '~/my_session.cxs')
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"open {quote_chimerax_arg(filename)}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Session opened: {filename}")


# ---------------------------------------------------------------------------
# Tool 45: create_surface
# ---------------------------------------------------------------------------

@mcp.tool()
async def create_surface(
    target: str = "all",
    style: str = "solid",
    resolution: float = 0.0,
    session_id: Optional[int] = None,
) -> str:
    """Generate a molecular surface for the specified atoms.

    Args:
        target: Atomspec for what to create a surface of (default: 'all')
        style: Surface style - 'solid', 'mesh', or 'dot' (default: 'solid')
        resolution: Surface resolution in Angstroms (0 = default)
        session_id: ChimeraX session port (defaults to primary session)
    """
    if style not in ("solid", "mesh", "dot"):
        raise ValueError(f"Style must be 'solid', 'mesh', or 'dot', got '{style}'")

    command = f"surface {target}"
    if resolution > 0:
        command += f" resolution {resolution}"
    result = await run_chimerax_command(command, session_id)

    if style != "solid":
        await run_chimerax_command(f"surface style {target} {style}", session_id)

    return format_chimerax_response(result, f"Surface created for {target} (style={style})")


# ---------------------------------------------------------------------------
# Tool 46: color_surface
# ---------------------------------------------------------------------------

@mcp.tool()
async def color_surface(
    target: str,
    method: str = "coulombic",
    palette: str = "",
    session_id: Optional[int] = None,
) -> str:
    """Color a surface by electrostatic potential, hydrophobicity, or B-factor.

    Args:
        target: Atomspec for the surface to color (e.g., '#1')
        method: Coloring method - 'coulombic' (electrostatics), 'mlp' (hydrophobicity), 'bfactor'
        palette: Custom color palette (e.g., 'red-white-blue'). Uses method default if empty.
        session_id: ChimeraX session port (defaults to primary session)
    """
    target = validate_atomspec(target)
    if method not in ("coulombic", "mlp", "bfactor"):
        raise ValueError(f"Method must be 'coulombic', 'mlp', or 'bfactor', got '{method}'")

    if method == "bfactor":
        command = f"color bfactor {target}"
    else:
        command = f"{method} {target}"

    if palette:
        command += f" palette {palette}"

    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Colored surface of {target} by {method}")


# ---------------------------------------------------------------------------
# Tool 47: set_transparency
# ---------------------------------------------------------------------------

@mcp.tool()
async def set_transparency(
    target: str,
    percent: int,
    what: str = "s",
    session_id: Optional[int] = None,
) -> str:
    """Set transparency on surfaces, cartoons, or atoms.

    Args:
        target: Atomspec for the object (e.g., '#1', '#1/A')
        percent: Transparency percentage (0 = opaque, 100 = invisible)
        what: What to make transparent - 's' (surfaces), 'c' (cartoons), 'a' (atoms)
        session_id: ChimeraX session port (defaults to primary session)
    """
    target = validate_atomspec(target)
    if not (0 <= percent <= 100):
        raise ValueError(f"Percent must be 0-100, got {percent}")
    if any(c not in "sca" for c in what):
        raise ValueError(f"'what' must be one or more of 's', 'c', 'a', got '{what}'")

    command = f"transparency {target} {percent} target {what}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Set {target} transparency to {percent}%")


# ---------------------------------------------------------------------------
# Tool 48: undo_redo
# ---------------------------------------------------------------------------

@mcp.tool()
async def undo_redo(
    action: str = "undo", count: int = 1, session_id: Optional[int] = None
) -> str:
    """Undo or redo recent actions in ChimeraX.

    Args:
        action: 'undo' or 'redo' (default: 'undo')
        count: Number of steps to undo/redo (default: 1)
        session_id: ChimeraX session port (defaults to primary session)
    """
    if action not in ("undo", "redo"):
        raise ValueError(f"Action must be 'undo' or 'redo', got '{action}'")
    if count < 1:
        raise ValueError(f"Count must be >= 1, got {count}")

    command = f"{action} {count}" if count > 1 else action
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"{action.capitalize()} ({count} step{'s' if count > 1 else ''})")


# ===========================================================================
# TIER 1 — High Impact
# ===========================================================================


# ---------------------------------------------------------------------------
# Tool 49: set_style
# ---------------------------------------------------------------------------

@mcp.tool()
async def set_style(
    target: str = "all",
    style: str = "stick",
    session_id: Optional[int] = None,
) -> str:
    """Change the atomic display style (ball-and-stick, sphere, stick).

    Args:
        target: Atomspec to restyle (e.g., '#1', 'ligand', '#1/A')
        style: Display style - 'stick', 'ball' (ball-and-stick), 'sphere' (space-filling)
        session_id: ChimeraX session port (defaults to primary session)
    """
    if style not in ("stick", "ball", "sphere"):
        raise ValueError(f"Style must be 'stick', 'ball', or 'sphere', got '{style}'")
    command = f"style {target} {style}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Set style of {target} to {style}")


# ---------------------------------------------------------------------------
# Tool 50: set_cartoon
# ---------------------------------------------------------------------------

@mcp.tool()
async def set_cartoon(
    target: str = "all",
    xsection: str = "",
    hide_backbone: bool = True,
    session_id: Optional[int] = None,
) -> str:
    """Control cartoon/ribbon display and style.

    Args:
        target: Atomspec for the cartoon (e.g., '#1', '#1/A')
        xsection: Cross-section shape - 'oval' (round), 'rectangle' (square), 'barbell' (piping), or '' for default
        hide_backbone: Hide backbone atoms when showing cartoon (default: True)
        session_id: ChimeraX session port (defaults to primary session)
    """
    # Show the cartoon
    command = f"cartoon {target}"
    if hide_backbone:
        command += " suppressBackboneDisplay true"
    result = await run_chimerax_command(command, session_id)

    # Apply style as a separate subcommand if requested
    if xsection:
        if xsection not in ("oval", "rectangle", "barbell"):
            raise ValueError(f"xsection must be 'oval', 'rectangle', or 'barbell'")
        await run_chimerax_command(f"cartoon style {target} xsection {xsection}", session_id)

    return format_chimerax_response(result, f"Cartoon set for {target}")


# ---------------------------------------------------------------------------
# Tool 51: set_clipping
# ---------------------------------------------------------------------------

@mcp.tool()
async def set_clipping(
    plane: str = "near",
    offset: float = 0.0,
    enable: bool = True,
    session_id: Optional[int] = None,
) -> str:
    """Control view clipping planes to slice through structures.

    Args:
        plane: Which plane - 'near', 'far', 'front', 'back', 'slab'
        offset: Distance offset in Angstroms (positive = further from camera)
        enable: Enable (True) or disable (False) the clipping plane
        session_id: ChimeraX session port (defaults to primary session)
    """
    if not enable:
        command = f"clip off {plane}"
    elif offset != 0:
        command = f"clip {plane} {offset}"
    else:
        command = f"clip {plane}"
    result = await run_chimerax_command(command, session_id)
    action = "Disabled" if not enable else "Set"
    return format_chimerax_response(result, f"{action} {plane} clipping plane")


# ---------------------------------------------------------------------------
# Tool 52: calculate_rmsd
# ---------------------------------------------------------------------------

@mcp.tool()
async def calculate_rmsd(
    atoms1: str,
    atoms2: str,
    session_id: Optional[int] = None,
) -> str:
    """Calculate RMSD between two sets of atoms.

    Args:
        atoms1: First atomspec (e.g., '#1/A')
        atoms2: Second atomspec (e.g., '#2/A')
        session_id: ChimeraX session port (defaults to primary session)
    """
    atoms1, atoms2 = validate_atomspec(atoms1), validate_atomspec(atoms2)
    command = f"rmsd {atoms1} to {atoms2}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"RMSD between {atoms1} and {atoms2}")


# ---------------------------------------------------------------------------
# Tool 53: set_volume_display
# ---------------------------------------------------------------------------

@mcp.tool()
async def set_volume_display(
    map_model: str,
    level: float = 0.0,
    style: str = "",
    step: int = 0,
    color: str = "",
    session_id: Optional[int] = None,
) -> str:
    """Control density map display — contour level, style, step size, color.

    Args:
        map_model: Volume model spec (e.g., '#2')
        level: Contour level (0 = use current)
        style: Display style - 'surface', 'mesh', 'solid', or '' for current
        step: Step size for display (higher = faster but coarser; 0 = auto)
        color: Volume color (e.g., 'blue', '#80808080' for semi-transparent gray)
        session_id: ChimeraX session port (defaults to primary session)
    """
    map_model = validate_atomspec(map_model)
    command = f"volume {map_model}"
    if level != 0:
        command += f" level {level}"
    if style:
        if style not in ("surface", "mesh", "solid"):
            raise ValueError(f"Style must be 'surface', 'mesh', or 'solid'")
        command += f" style {style}"
    if step > 0:
        command += f" step {step}"
    if color:
        command += f" color {color}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Volume display updated for {map_model}")


# ---------------------------------------------------------------------------
# Tool 54: atoms_to_map
# ---------------------------------------------------------------------------

@mcp.tool()
async def atoms_to_map(
    target: str,
    resolution: float = 5.0,
    grid_spacing: float = 0.0,
    session_id: Optional[int] = None,
) -> str:
    """Generate a simulated density map from atomic coordinates.

    Args:
        target: Atomspec for atoms to convert (e.g., '#1')
        resolution: Map resolution in Angstroms (default: 5.0)
        grid_spacing: Grid spacing in Angstroms (0 = auto, typically resolution/3)
        session_id: ChimeraX session port (defaults to primary session)
    """
    target = validate_atomspec(target)
    command = f"molmap {target} {resolution}"
    if grid_spacing > 0:
        command += f" gridSpacing {grid_spacing}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Simulated map from {target} at {resolution}A resolution")


# ---------------------------------------------------------------------------
# Tool 55: show_contacts
# ---------------------------------------------------------------------------

@mcp.tool()
async def show_contacts(
    target: str = "all",
    both: bool = True,
    session_id: Optional[int] = None,
) -> str:
    """Find and display protein-protein or molecular interfaces.

    Args:
        target: Atomspec for the model(s) to analyze (e.g., '#1')
        both: Show contacts from both sides of the interface (default: True)
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"interfaces {target}"
    if both:
        command += " bothSides true"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Interfaces for {target}")


# ---------------------------------------------------------------------------
# Tool 56: show_nucleotides
# ---------------------------------------------------------------------------

@mcp.tool()
async def show_nucleotides(
    target: str = "all",
    style: str = "ladder",
    session_id: Optional[int] = None,
) -> str:
    """Display nucleic acid (RNA/DNA) base representations.

    Args:
        target: Atomspec for nucleic acid (e.g., '#1')
        style: Display style - 'ladder', 'slab', 'tube', 'stubs', 'fill'
        session_id: ChimeraX session port (defaults to primary session)
    """
    if style not in ("ladder", "slab", "tube", "stubs", "fill"):
        raise ValueError(f"Style must be 'ladder', 'slab', 'tube', 'stubs', or 'fill'")
    command = f"nucleotides {target} {style}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Nucleotide display for {target} ({style})")


# ===========================================================================
# TIER 2 — Publication & Animation
# ===========================================================================


# ---------------------------------------------------------------------------
# Tool 57: rotate_view
# ---------------------------------------------------------------------------

@mcp.tool()
async def rotate_view(
    axis: str = "y",
    angle: float = 90.0,
    frames: int = 0,
    rock: bool = False,
    session_id: Optional[int] = None,
) -> str:
    """Rotate the view around an axis, optionally animated.

    Args:
        axis: Rotation axis - 'x', 'y', 'z' (default: 'y')
        angle: Rotation angle in degrees (default: 90)
        frames: Number of animation frames (0 = instant)
        rock: If True, rock back and forth instead of one-way turn
        session_id: ChimeraX session port (defaults to primary session)
    """
    if rock:
        command = f"rock {axis} {angle}"
        if frames > 0:
            command += f" {frames}"
    else:
        command = f"turn {axis} {angle}"
        if frames > 0:
            command += f" {frames}"
    result = await run_chimerax_command(command, session_id)
    action = "Rocking" if rock else "Rotated"
    return format_chimerax_response(result, f"{action} view {angle} degrees around {axis}")


# ---------------------------------------------------------------------------
# Tool 58: zoom_view
# ---------------------------------------------------------------------------

@mcp.tool()
async def zoom_view(
    factor: float = 1.5,
    frames: int = 0,
    pixel_size: float = 0.0,
    session_id: Optional[int] = None,
) -> str:
    """Zoom the camera in or out.

    Args:
        factor: Zoom factor (>1 = zoom in, <1 = zoom out, e.g., 2.0 = 2x closer)
        frames: Number of animation frames (0 = instant)
        pixel_size: Set exact pixel size in Angstroms (overrides factor; 0 = use factor)
        session_id: ChimeraX session port (defaults to primary session)
    """
    if pixel_size > 0:
        command = f"zoom pixelSize {pixel_size}"
    else:
        command = f"zoom {factor}"
    if frames > 0:
        command += f" {frames}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Zoomed by factor {factor}")


# ---------------------------------------------------------------------------
# Tool 59: record_movie
# ---------------------------------------------------------------------------

@mcp.tool()
async def record_movie(
    action: str = "record",
    filename: str = "",
    framerate: int = 25,
    format: str = "h264",
    session_id: Optional[int] = None,
) -> str:
    """Record or encode a movie of the ChimeraX viewport.

    Workflow: record → (perform actions / animations) → encode

    Args:
        action: 'record' (start recording), 'stop' (stop recording), 'encode' (save movie)
        filename: Output filename (for encode action, e.g., 'movie.mp4')
        framerate: Frames per second for encoding (default: 25)
        format: Video format for encoding - 'h264', 'vp8', 'apng', 'gif' (default: 'h264')
        session_id: ChimeraX session port (defaults to primary session)
    """
    if action == "record":
        command = "movie record"
    elif action == "stop":
        command = "movie stop"
    elif action == "encode":
        if not filename:
            filename = "/tmp/chimerax_movie.mp4"
        command = (
            f"movie encode {quote_chimerax_arg(filename)} framerate {framerate} "
            f"format {format}"
        )
    else:
        raise ValueError(f"Action must be 'record', 'stop', or 'encode', got '{action}'")
    result = await run_chimerax_command(command, session_id, timeout=300)
    return format_chimerax_response(result, f"Movie {action}: {filename or 'started'}")


# ---------------------------------------------------------------------------
# Tool 60: manage_scenes
# ---------------------------------------------------------------------------

@mcp.tool()
async def manage_scenes(
    action: str = "list",
    name: str = "",
    session_id: Optional[int] = None,
) -> str:
    """Save, restore, or list named viewpoints (scenes).

    Args:
        action: 'save' (save current view), 'restore' (go to saved view), 'list', 'delete'
        name: Scene name (required for save, restore, delete)
        session_id: ChimeraX session port (defaults to primary session)
    """
    if action == "list":
        command = "scenes list"
    elif action in ("save", "restore", "delete"):
        if not name:
            raise ValueError(f"Scene name required for '{action}'")
        command = f"scenes {action} {quote_chimerax_arg(name)}"
    else:
        raise ValueError(f"Action must be 'save', 'restore', 'list', or 'delete'")
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Scenes {action}: {name or 'all'}")


# ---------------------------------------------------------------------------
# Tool 61: apply_preset
# ---------------------------------------------------------------------------

@mcp.tool()
async def apply_preset(
    preset_name: str,
    session_id: Optional[int] = None,
) -> str:
    """Apply a built-in visualization preset.

    Args:
        preset_name: Preset name. Common presets:
            'initial styles' - default representation
            'publication 1 (silhouettes)' - publication with edge outlines
            'publication 2 (depth-cued)' - publication with depth fog
            'interactive 1 (ribbons)' - interactive ribbon view
            'interactive 2 (sticks)' - interactive stick view
            'sticks', 'cylinders', 'licorice', 'ball-and-stick', 'space-filling'
            Note: use full names to avoid ambiguity (e.g., 'publication 1' not 'publication')
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"preset {quote_chimerax_arg(preset_name)}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Applied preset: {preset_name}")


# ---------------------------------------------------------------------------
# Tool 62: add_scalebar
# ---------------------------------------------------------------------------

@mcp.tool()
async def add_scalebar(
    length: float = 0.0,
    color: str = "white",
    thickness: float = 3.0,
    show: bool = True,
    session_id: Optional[int] = None,
) -> str:
    """Add or remove a distance scale bar on the image.

    Args:
        length: Scale bar length in Angstroms (0 = auto)
        color: Scale bar color (default: 'white')
        thickness: Line thickness in pixels (default: 3.0)
        show: Show (True) or hide (False) the scale bar
        session_id: ChimeraX session port (defaults to primary session)
    """
    if not show:
        command = "scalebar delete"
    else:
        command = f"scalebar color {color} thickness {thickness}"
        if length > 0:
            command += f" length {length}"
    result = await run_chimerax_command(command, session_id)
    action = "Removed" if not show else "Added"
    return format_chimerax_response(result, f"{action} scale bar")


# ---------------------------------------------------------------------------
# Tool 63: add_marker
# ---------------------------------------------------------------------------

@mcp.tool()
async def add_marker(
    x: float,
    y: float,
    z: float,
    color: str = "yellow",
    radius: float = 1.0,
    model_id: int = 200,
    session_id: Optional[int] = None,
) -> str:
    """Place a 3D marker/sphere at a specific coordinate.

    Args:
        x: X coordinate in Angstroms
        y: Y coordinate in Angstroms
        z: Z coordinate in Angstroms
        color: Marker color (default: 'yellow')
        radius: Marker radius in Angstroms (default: 1.0)
        model_id: Marker set model ID (default: 200; reuse to group markers)
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"marker #{model_id} position {x},{y},{z} color {color} radius {radius}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Marker placed at ({x}, {y}, {z})")


# ---------------------------------------------------------------------------
# Tool 64: add_shape
# ---------------------------------------------------------------------------

@mcp.tool()
async def add_shape(
    shape_type: str = "sphere",
    center: str = "0,0,0",
    radius: float = 5.0,
    color: str = "gray",
    session_id: Optional[int] = None,
) -> str:
    """Add a geometric shape (sphere, cylinder, arrow) to the scene.

    Args:
        shape_type: Shape - 'sphere', 'cylinder', 'arrow', 'tube', 'rectangle'
        center: Center position as 'x,y,z' (default: '0,0,0')
        radius: Shape radius in Angstroms (default: 5.0)
        color: Shape color (default: 'gray')
        session_id: ChimeraX session port (defaults to primary session)
    """
    if shape_type not in ("sphere", "cylinder", "arrow", "tube", "rectangle"):
        raise ValueError(f"Shape must be 'sphere', 'cylinder', 'arrow', 'tube', or 'rectangle'")
    command = f"shape {shape_type} center {center} radius {radius} color {color}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Added {shape_type} at {center}")


# ===========================================================================
# TIER 3 — Specialized Workflows
# ===========================================================================


# ---------------------------------------------------------------------------
# Tool 65: prep_for_docking
# ---------------------------------------------------------------------------

@mcp.tool()
async def prep_for_docking(
    target: str = "all",
    session_id: Optional[int] = None,
) -> str:
    """Prepare a structure for docking (adds hydrogens, charges, repairs).

    Args:
        target: Atomspec for the model to prepare (e.g., '#1')
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"dockprep {target}"
    result = await run_chimerax_command(command, session_id, timeout=120)
    return format_chimerax_response(result, f"Docking prep completed for {target}")


# ---------------------------------------------------------------------------
# Tool 66: assign_secondary_structure
# ---------------------------------------------------------------------------

@mcp.tool()
async def assign_secondary_structure(
    target: str = "all",
    session_id: Optional[int] = None,
) -> str:
    """Calculate and assign secondary structure (helix/sheet/coil) using DSSP algorithm.

    Args:
        target: Atomspec for the model (e.g., '#1')
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"dssp {target}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Secondary structure assigned for {target}")


# ---------------------------------------------------------------------------
# Tool 67: find_cavities
# ---------------------------------------------------------------------------

@mcp.tool()
async def find_cavities(
    target: str = "all",
    session_id: Optional[int] = None,
) -> str:
    """Detect binding pockets and cavities in a structure using KVFinder.

    Args:
        target: Atomspec for the model (e.g., '#1')
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"kvfinder {target}"
    result = await run_chimerax_command(command, session_id, timeout=120)
    return format_chimerax_response(result, f"Cavities detected in {target}")


# ---------------------------------------------------------------------------
# Tool 68: morph_structures
# ---------------------------------------------------------------------------

@mcp.tool()
async def morph_structures(
    models: str,
    frames: int = 20,
    session_id: Optional[int] = None,
) -> str:
    """Create a morph animation between conformations.

    Args:
        models: Atomspec for models to morph between (e.g., '#1-3')
        frames: Number of interpolation frames between each pair (default: 20)
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"morph {models} frames {frames}"
    result = await run_chimerax_command(command, session_id, timeout=120)
    return format_chimerax_response(result, f"Morph created for {models}")


# ---------------------------------------------------------------------------
# Tool 69: split_model
# ---------------------------------------------------------------------------

@mcp.tool()
async def split_model(
    model: str,
    by: str = "chains",
    session_id: Optional[int] = None,
) -> str:
    """Split a model into separate sub-models.

    Args:
        model: Model spec to split (e.g., '#1')
        by: How to split - 'chains', 'ligands', 'connected', 'atoms'
        session_id: ChimeraX session port (defaults to primary session)
    """
    model = validate_atomspec(model)
    command = f"split {model}"
    if by == "chains":
        pass  # default behavior
    elif by in ("ligands", "connected", "atoms"):
        command += f" {by}"
    else:
        raise ValueError(f"'by' must be 'chains', 'ligands', 'connected', or 'atoms'")
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Split {model} by {by}")


# ---------------------------------------------------------------------------
# Tool 70: combine_models
# ---------------------------------------------------------------------------

@mcp.tool()
async def combine_models(
    models: str,
    name: str = "",
    close_originals: bool = False,
    session_id: Optional[int] = None,
) -> str:
    """Merge multiple models into a single model.

    Args:
        models: Models to combine (e.g., '#1,2' or '#1-3')
        name: Name for the combined model (optional)
        close_originals: Close the original models after combining (default: False)
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"combine {models}"
    if name:
        command += f" name {quote_chimerax_arg(name)}"
    if close_originals:
        command += " close true"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Combined models {models}")


# ---------------------------------------------------------------------------
# Tool 71: set_attribute
# ---------------------------------------------------------------------------

@mcp.tool()
async def set_attribute(
    target: str,
    attribute: str,
    value: str,
    attr_type: str = "atoms",
    session_id: Optional[int] = None,
) -> str:
    """Set a custom attribute on atoms, residues, or models (for custom coloring, etc.).

    Args:
        target: Atomspec to set attribute on (e.g., '#1/A:100-200')
        attribute: Attribute name (e.g., 'binding_score')
        value: Attribute value (number or string)
        attr_type: Level - 'atoms', 'residues', 'models'
        session_id: ChimeraX session port (defaults to primary session)
    """
    target = validate_atomspec(target)
    if attr_type not in ("atoms", "residues", "models"):
        raise ValueError(f"attr_type must be 'atoms', 'residues', or 'models'")
    command = f"setattr {target} {attr_type} {attribute} {value} create true"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Set {attribute}={value} on {target}")


# ---------------------------------------------------------------------------
# Tool 72: show_crosslinks
# ---------------------------------------------------------------------------

@mcp.tool()
async def show_crosslinks(
    filename: str,
    color: str = "dodgerblue",
    radius: float = 0.5,
    session_id: Optional[int] = None,
) -> str:
    """Visualize crosslinking mass spectrometry data.

    Args:
        filename: Path to crosslinks file (CSV or pseudobond format)
        color: Crosslink color (default: 'dodgerblue')
        radius: Pseudobond radius (default: 0.5)
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"crosslinks {quote_chimerax_arg(filename)} color {color} radius {radius}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Crosslinks loaded from {filename}")


# ---------------------------------------------------------------------------
# Tool 73: show_crystal_contacts
# ---------------------------------------------------------------------------

@mcp.tool()
async def show_crystal_contacts(
    model: str = "#1",
    distance: float = 3.0,
    session_id: Optional[int] = None,
) -> str:
    """Show crystal packing contacts and symmetry-related neighbors.

    Args:
        model: Model spec (e.g., '#1')
        distance: Contact distance threshold in Angstroms (default: 3.0)
        session_id: ChimeraX session port (defaults to primary session)
    """
    model = validate_atomspec(model)
    command = f"crystalcontacts {model} distance {distance}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Crystal contacts for {model}")


# ---------------------------------------------------------------------------
# Tool 74: build_structure
# ---------------------------------------------------------------------------

@mcp.tool()
async def build_structure(
    structure_type: str,
    value: str,
    session_id: Optional[int] = None,
) -> str:
    """Build atoms, fragments, or peptides from scratch.

    Args:
        structure_type: What to build - 'atom' (single atom), 'peptide' (from sequence),
                       'nucleic' (from sequence)
        value: For 'atom': element symbol. For 'peptide'/'nucleic': sequence string.
        session_id: ChimeraX session port (defaults to primary session)
    """
    if structure_type == "atom":
        command = f"build start atom {value}"
    elif structure_type == "peptide":
        command = f"build start peptide {value}"
    elif structure_type == "nucleic":
        command = f"build start nucleic {value}"
    else:
        raise ValueError(f"type must be 'atom', 'peptide', or 'nucleic'")
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Built {structure_type}: {value[:30]}")


# ---------------------------------------------------------------------------
# Tool 75: show_symmetry
# ---------------------------------------------------------------------------

@mcp.tool()
async def show_symmetry(
    model: str = "#1",
    sym_type: str = "assembly",
    assembly_id: str = "1",
    session_id: Optional[int] = None,
) -> str:
    """Show biological assembly or crystallographic symmetry copies.

    Args:
        model: Model spec (e.g., '#1')
        sym_type: Symmetry type - 'assembly' (biological unit), 'unitcell', 'contacts'
        assembly_id: Assembly ID for biological units (default: '1')
        session_id: ChimeraX session port (defaults to primary session)
    """
    model = validate_atomspec(model)
    if sym_type == "assembly":
        command = f"sym {model} assembly {assembly_id}"
    elif sym_type == "unitcell":
        command = f"unitcell {model}"
    elif sym_type == "contacts":
        command = f"sym {model} contacts true"
    else:
        raise ValueError(f"sym_type must be 'assembly', 'unitcell', or 'contacts'")
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Symmetry shown for {model} ({sym_type})")


# ---------------------------------------------------------------------------
# Tool 76: add_charges
# ---------------------------------------------------------------------------

@mcp.tool()
async def add_charges(
    target: str = "all",
    method: str = "am1-bcc",
    session_id: Optional[int] = None,
) -> str:
    """Add partial charges to atoms (required for electrostatic calculations).

    Args:
        target: Atomspec to charge (e.g., '#1')
        method: Charge method - 'am1-bcc' (default for small molecules), 'gasteiger'
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"addcharge {target} method {method}"
    result = await run_chimerax_command(command, session_id, timeout=120)
    return format_chimerax_response(result, f"Charges added to {target} ({method})")


# ---------------------------------------------------------------------------
# Tool 77: rename_model
# ---------------------------------------------------------------------------

@mcp.tool()
async def rename_model(
    model: str,
    new_name: str,
    session_id: Optional[int] = None,
) -> str:
    """Rename a model.

    Args:
        model: Model spec to rename (e.g., '#1')
        new_name: New name for the model
        session_id: ChimeraX session port (defaults to primary session)
    """
    model = validate_atomspec(model)
    command = f"rename {model} {quote_chimerax_arg(new_name)}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Renamed {model} to '{new_name}'")


# ---------------------------------------------------------------------------
# Tool 78: change_chain_ids
# ---------------------------------------------------------------------------

@mcp.tool()
async def change_chain_ids(
    target: str,
    new_id: str,
    session_id: Optional[int] = None,
) -> str:
    """Change chain ID(s) for a selection.

    Args:
        target: Atomspec of the chain(s) to rename (e.g., '#1/A')
        new_id: New chain ID (e.g., 'B')
        session_id: ChimeraX session port (defaults to primary session)
    """
    target = validate_atomspec(target)
    command = f"changechains {target} {new_id}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Changed chain ID of {target} to {new_id}")


# ---------------------------------------------------------------------------
# Tool 79: renumber_residues
# ---------------------------------------------------------------------------

@mcp.tool()
async def renumber_residues(
    target: str,
    start: int = 1,
    session_id: Optional[int] = None,
) -> str:
    """Renumber residues starting from a given number.

    Args:
        target: Atomspec of residues to renumber (e.g., '#1/A')
        start: Starting residue number (default: 1)
        session_id: ChimeraX session port (defaults to primary session)
    """
    target = validate_atomspec(target)
    command = f"renumber {target} start {start}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Renumbered {target} starting from {start}")


# ---------------------------------------------------------------------------
# Tool 80: delete_atoms
# ---------------------------------------------------------------------------

@mcp.tool()
async def delete_atoms(
    target: str,
    session_id: Optional[int] = None,
) -> str:
    """Delete atoms, residues, or bonds from a model.

    Args:
        target: Atomspec of atoms to delete (e.g., '#1/A:100', 'solvent')
        session_id: ChimeraX session port (defaults to primary session)
    """
    target = validate_atomspec(target)
    command = f"delete {target}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Deleted {target}")


# ---------------------------------------------------------------------------
# Tool 81: manage_bonds
# ---------------------------------------------------------------------------

@mcp.tool()
async def manage_bonds(
    action: str,
    target: str,
    session_id: Optional[int] = None,
) -> str:
    """Add or remove bonds between atoms.

    Args:
        action: 'add' or 'delete'
        target: Atomspec for the bond atoms (e.g., '#1/A:100@CA #1/A:200@CA')
        session_id: ChimeraX session port (defaults to primary session)
    """
    target = validate_atomspec(target)
    if action == "add":
        command = f"bond {target}"
    elif action == "delete":
        command = f"~bond {target}"
    else:
        raise ValueError(f"Action must be 'add' or 'delete'")
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Bond {action}: {target}")


# ---------------------------------------------------------------------------
# Tool 82: define_axis_plane
# ---------------------------------------------------------------------------

@mcp.tool()
async def define_axis_plane(
    what: str = "axis",
    target: str = "all",
    session_id: Optional[int] = None,
) -> str:
    """Define an axis, plane, or centroid for a set of atoms.

    Args:
        what: 'axis', 'plane', or 'centroid'
        target: Atomspec to compute over (e.g., '#1/A')
        session_id: ChimeraX session port (defaults to primary session)
    """
    if what not in ("axis", "plane", "centroid"):
        raise ValueError(f"'what' must be 'axis', 'plane', or 'centroid'")
    target = validate_atomspec(target)
    command = f"define {what} {target}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Defined {what} for {target}")


# ---------------------------------------------------------------------------
# Tool 83: set_lighting
# ---------------------------------------------------------------------------

@mcp.tool()
async def set_lighting(
    preset: str = "default",
    shadows: bool = False,
    session_id: Optional[int] = None,
) -> str:
    """Control the lighting environment.

    Args:
        preset: Lighting preset - 'default', 'simple', 'soft', 'full', 'flat'
        shadows: Enable shadow rendering (default: False)
        session_id: ChimeraX session port (defaults to primary session)
    """
    if preset not in ("default", "simple", "soft", "full", "flat"):
        raise ValueError(f"Preset must be 'default', 'simple', 'soft', 'full', or 'flat'")
    command = f"lighting {preset}"
    if shadows:
        command += " shadows true"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Lighting set to {preset}")


# ---------------------------------------------------------------------------
# Tool 84: set_camera
# ---------------------------------------------------------------------------

@mcp.tool()
async def set_camera(
    mode: str = "mono",
    field_of_view: float = 0.0,
    session_id: Optional[int] = None,
) -> str:
    """Control the camera mode and field of view.

    Args:
        mode: Camera mode - 'mono' (default), 'ortho' (orthographic), 'stereo', '360'
        field_of_view: Horizontal field of view in degrees (0 = keep current)
        session_id: ChimeraX session port (defaults to primary session)
    """
    if mode not in ("mono", "ortho", "stereo", "360", "sbs"):
        raise ValueError(f"Mode must be 'mono', 'ortho', 'stereo', '360', or 'sbs'")
    command = f"camera {mode}"
    if field_of_view > 0:
        command += f" fieldOfView {field_of_view}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Camera set to {mode}")


# ---------------------------------------------------------------------------
# Tool 85: set_window_size
# ---------------------------------------------------------------------------

@mcp.tool()
async def set_window_size(
    width: int,
    height: int,
    session_id: Optional[int] = None,
) -> str:
    """Set the ChimeraX viewport window size.

    Args:
        width: Width in pixels
        height: Height in pixels
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"windowsize {width} {height}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Window resized to {width}x{height}")


# ---------------------------------------------------------------------------
# Tool 86: tile_models
# ---------------------------------------------------------------------------

@mcp.tool()
async def tile_models(
    models: str = "all",
    columns: int = 0,
    spacing_factor: float = 0.0,
    session_id: Optional[int] = None,
) -> str:
    """Arrange models side-by-side in a grid layout.

    Args:
        models: Models to tile (e.g., '#1-4' or 'all')
        columns: Number of columns (0 = auto)
        spacing_factor: Spacing between models as fraction of size (0 = auto)
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"tile {models}"
    if columns > 0:
        command += f" columns {columns}"
    if spacing_factor > 0:
        command += f" spacingFactor {spacing_factor}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Tiled models: {models}")


# ---------------------------------------------------------------------------
# Tool 87: copy_model
# ---------------------------------------------------------------------------

@mcp.tool()
async def copy_model(
    model: str,
    session_id: Optional[int] = None,
) -> str:
    """Create a duplicate of a model (as a new model).

    Args:
        model: Model spec to copy (e.g., '#1')
        session_id: ChimeraX session port (defaults to primary session)
    """
    model = validate_atomspec(model)
    command = f"combine {model}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Copied model {model}")


# ---------------------------------------------------------------------------
# Tool 88: set_size
# ---------------------------------------------------------------------------

@mcp.tool()
async def set_size(
    target: str = "all",
    atom_radius: float = 0.0,
    stick_radius: float = 0.0,
    ball_scale: float = 0.0,
    session_id: Optional[int] = None,
) -> str:
    """Change the display size of atoms, sticks, or balls.

    Args:
        target: Atomspec to resize (e.g., '#1', 'ligand')
        atom_radius: Atom sphere radius in Angstroms (0 = no change)
        stick_radius: Stick bond radius (0 = no change)
        ball_scale: Ball-and-stick scale factor (0 = no change)
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"size {target}"
    if atom_radius > 0:
        command += f" atomRadius {atom_radius}"
    if stick_radius > 0:
        command += f" stickRadius {stick_radius}"
    if ball_scale > 0:
        command += f" ballScale {ball_scale}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Resized {target}")


# ---------------------------------------------------------------------------
# Tool 89: move_model
# ---------------------------------------------------------------------------

@mcp.tool()
async def move_model(
    axis: str = "x",
    distance: float = 10.0,
    models: str = "",
    frames: int = 0,
    session_id: Optional[int] = None,
) -> str:
    """Translate models or the camera along an axis.

    Args:
        axis: Translation axis - 'x', 'y', 'z'
        distance: Distance in Angstroms
        models: Models to move (empty = move camera)
        frames: Animate over N frames (0 = instant)
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"move {axis} {distance}"
    if models:
        command += f" models {models}"
    if frames > 0:
        command += f" {frames}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Moved {axis} by {distance}A")


# ---------------------------------------------------------------------------
# Tool 90: color_key
# ---------------------------------------------------------------------------

@mcp.tool()
async def color_key(
    palette: str = "rainbow",
    label_side: str = "right",
    show: bool = True,
    session_id: Optional[int] = None,
) -> str:
    """Add or remove a color key (legend) to the display.

    Args:
        palette: Color palette to show (e.g., 'rainbow', 'red-white-blue')
        label_side: Label position - 'left', 'right', 'top', 'bottom'
        show: Show (True) or delete (False) the color key
        session_id: ChimeraX session port (defaults to primary session)
    """
    if not show:
        command = "key delete"
    else:
        command = f"key {palette} labelSide {label_side}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, "Color key " + ("removed" if not show else "added"))


# ---------------------------------------------------------------------------
# Tool 91: foldseek_search
# ---------------------------------------------------------------------------

@mcp.tool()
async def foldseek_search(
    target: str,
    database: str = "pdb100",
    session_id: Optional[int] = None,
) -> str:
    """Search for structurally similar proteins using Foldseek.

    Args:
        target: Atomspec for the query structure (e.g., '#1')
        database: Database to search - 'pdb100', 'afdb50', 'afdb-swissprot', 'afdb-proteome'
        session_id: ChimeraX session port (defaults to primary session)
    """
    target = validate_atomspec(target)
    command = f"foldseek {target} database {database}"
    result = await run_chimerax_command(command, session_id, timeout=120)
    return format_chimerax_response(result, f"Foldseek search for {target} in {database}")


# ---------------------------------------------------------------------------
# Tool 92: altlocs
# ---------------------------------------------------------------------------

@mcp.tool()
async def altlocs(
    target: str,
    altloc: str = "",
    session_id: Optional[int] = None,
) -> str:
    """Show or change alternate conformations (altlocs) for atoms.

    Args:
        target: Atomspec for atoms with altlocs (e.g., '#1/A:100')
        altloc: Which altloc to display ('A', 'B', etc.; empty = list available)
        session_id: ChimeraX session port (defaults to primary session)
    """
    target = validate_atomspec(target)
    if altloc:
        command = f"altlocs change {target} {altloc}"
    else:
        command = f"altlocs list {target}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Altlocs for {target}")


# ---------------------------------------------------------------------------
# Tool 93: coordset
# ---------------------------------------------------------------------------

@mcp.tool()
async def coordset(
    model: str,
    frame: int = 1,
    play: bool = False,
    session_id: Optional[int] = None,
) -> str:
    """Navigate multi-frame structures (NMR ensembles, MD trajectories).

    Args:
        model: Model spec (e.g., '#1')
        frame: Frame number to display (starting from 1)
        play: If True, play through all frames as animation
        session_id: ChimeraX session port (defaults to primary session)
    """
    model = validate_atomspec(model)
    if play:
        command = f"coordset {model}"
    else:
        command = f"coordset {model} {frame}"
    result = await run_chimerax_command(command, session_id)
    action = "Playing all frames" if play else f"Frame {frame}"
    return format_chimerax_response(result, f"{action} of {model}")


# ---------------------------------------------------------------------------
# Tool 94: swap_nucleic_acid
# ---------------------------------------------------------------------------

@mcp.tool()
async def swap_nucleic_acid(
    atomspec: str,
    new_base: str,
    session_id: Optional[int] = None,
) -> str:
    """Mutate a nucleic acid residue to a different base.

    Args:
        atomspec: Atomspec for the residue to mutate (e.g., '#1/A:10')
        new_base: New base ('A', 'G', 'C', 'T', 'U', 'DA', 'DG', 'DC', 'DT')
        session_id: ChimeraX session port (defaults to primary session)
    """
    atomspec = validate_atomspec(atomspec)
    command = f"swapna {atomspec} {new_base}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Swapped {atomspec} to {new_base}")


# ---------------------------------------------------------------------------
# Tool 95: set_material
# ---------------------------------------------------------------------------

@mcp.tool()
async def set_material(
    reflectivity: float = 0.0,
    specular_exponent: float = 0.0,
    transparency_cast_shadows: bool = False,
    session_id: Optional[int] = None,
) -> str:
    """Control material properties for rendering (reflectivity, shininess).

    Args:
        reflectivity: Surface reflectivity 0-1 (0 = no change)
        specular_exponent: Shininess exponent (higher = tighter highlight; 0 = no change)
        transparency_cast_shadows: Transparent objects cast shadows (default: False)
        session_id: ChimeraX session port (defaults to primary session)
    """
    parts = ["material"]
    if reflectivity > 0:
        parts.append(f"reflectivity {reflectivity}")
    if specular_exponent > 0:
        parts.append(f"specularExponent {specular_exponent}")
    if transparency_cast_shadows:
        parts.append("transparencyCastShadows true")
    if len(parts) == 1:
        return "No material properties specified."
    command = " ".join(parts)
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, "Material properties updated")


# ---------------------------------------------------------------------------
# Tool 96: name_selection
# ---------------------------------------------------------------------------

@mcp.tool()
async def name_selection(
    name: str,
    atomspec: str = "",
    session_id: Optional[int] = None,
) -> str:
    """Create a named selection for reuse in other commands.

    Args:
        name: Name for the selection (e.g., 'binding_site', 'active_loop')
        atomspec: What to name (e.g., '#1/A:100-120'). Empty = name current selection.
        session_id: ChimeraX session port (defaults to primary session)
    """
    if atomspec:
        command = f"name {name} {atomspec}"
    else:
        command = f"name {name} sel"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Named selection: {name}")


# ---------------------------------------------------------------------------
# Tool 97: similar_structures
# ---------------------------------------------------------------------------

@mcp.tool()
async def similar_structures(
    target: str,
    session_id: Optional[int] = None,
) -> str:
    """Find structurally similar entries in PDB using the Similar Structures tool.

    Args:
        target: Atomspec for the query chain (e.g., '#1/A')
        session_id: ChimeraX session port (defaults to primary session)
    """
    target = validate_atomspec(target)
    command = f"similarstructures {target}"
    result = await run_chimerax_command(command, session_id, timeout=120)
    return format_chimerax_response(result, f"Similar structures for {target}")


# ---------------------------------------------------------------------------
# Tool 98: struts
# ---------------------------------------------------------------------------

@mcp.tool()
async def struts(
    target: str = "all",
    show: bool = True,
    length: float = 7.0,
    session_id: Optional[int] = None,
) -> str:
    """Add or remove struts (thin rods connecting nearby atoms for 3D printing support).

    Args:
        target: Atomspec to add struts to (e.g., '#1')
        show: Add (True) or remove (False) struts
        length: Maximum strut length in Angstroms (default: 7.0)
        session_id: ChimeraX session port (defaults to primary session)
    """
    if not show:
        command = f"~struts {target}"
    else:
        command = f"struts {target} length {length}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Struts {'removed from' if not show else 'added to'} {target}")


# ===========================================================================
# REMAINING COMMANDS — Full Coverage
# ===========================================================================


# ---------------------------------------------------------------------------
# Tool 99: create_alias
# ---------------------------------------------------------------------------

@mcp.tool()
async def create_alias(
    name: str,
    command_text: str = "",
    delete: bool = False,
    session_id: Optional[int] = None,
) -> str:
    """Create, list, or delete command aliases (shortcuts/macros).

    Args:
        name: Alias name (e.g., 'showsite'). Use '*' to list all.
        command_text: Command(s) to execute when alias is invoked (e.g., 'select #1/A:100-120; show sel target ab')
        delete: If True, delete the alias instead of creating it
        session_id: ChimeraX session port (defaults to primary session)
    """
    if delete:
        command = f"alias delete {name}"
    elif name == "*" or not command_text:
        command = f"alias list"
    else:
        command = f"alias {name} {command_text}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Alias {'deleted' if delete else 'set'}: {name}")


# ---------------------------------------------------------------------------
# Tool 100: show_aniso
# ---------------------------------------------------------------------------

@mcp.tool()
async def show_aniso(
    target: str = "all",
    show: bool = True,
    scale: float = 1.0,
    session_id: Optional[int] = None,
) -> str:
    """Show or hide thermal ellipsoids (anisotropic displacement parameters).

    Args:
        target: Atomspec for atoms with anisotropic data (e.g., '#1')
        show: Show (True) or hide (False) ellipsoids
        scale: Ellipsoid scale factor (default: 1.0)
        session_id: ChimeraX session port (defaults to primary session)
    """
    if not show:
        command = f"~aniso {target}"
    else:
        command = f"aniso {target} scale {scale}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Thermal ellipsoids {'hidden' if not show else 'shown'} for {target}")


# ---------------------------------------------------------------------------
# Tool 101: predict_boltz
# ---------------------------------------------------------------------------

@mcp.tool()
async def predict_boltz(
    sequence: str,
    session_id: Optional[int] = None,
) -> str:
    """Predict protein structure using Boltz (local structure prediction).

    Args:
        sequence: Amino acid sequence or atomspec chain reference
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"boltz predict {sequence}"
    result = await run_chimerax_command(command, session_id, timeout=600)
    return format_chimerax_response(result, f"Boltz prediction for {sequence[:40]}")


# ---------------------------------------------------------------------------
# Tool 102: show_bumps
# ---------------------------------------------------------------------------

@mcp.tool()
async def show_bumps(
    target: str = "all",
    show: bool = True,
    session_id: Optional[int] = None,
) -> str:
    """Show or hide steric bump indicators between close atoms.

    Args:
        target: Atomspec to check (e.g., '#1')
        show: Show (True) or hide (False) bump display
        session_id: ChimeraX session port (defaults to primary session)
    """
    if not show:
        command = f"~bumps {target}"
    else:
        command = f"bumps {target}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Bumps {'hidden' if not show else 'shown'} for {target}")


# ---------------------------------------------------------------------------
# Tool 103: check_chirality
# ---------------------------------------------------------------------------

@mcp.tool()
async def check_chirality(
    target: str = "all",
    session_id: Optional[int] = None,
) -> str:
    """Check and report chirality of residues (detect mis-built stereocenters).

    Args:
        target: Atomspec to check (e.g., '#1')
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"chirality {target}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Chirality check for {target}")


# ---------------------------------------------------------------------------
# Tool 104: crossfade
# ---------------------------------------------------------------------------

@mcp.tool()
async def crossfade(
    frames: int = 30,
    session_id: Optional[int] = None,
) -> str:
    """Create a smooth visual crossfade transition (for movies/presentations).

    Args:
        frames: Number of frames for the transition (default: 30)
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"crossfade {frames}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Crossfade over {frames} frames")


# ---------------------------------------------------------------------------
# Tool 105: load_attributes
# ---------------------------------------------------------------------------

@mcp.tool()
async def load_attributes(
    filename: str,
    session_id: Optional[int] = None,
) -> str:
    """Load custom attributes from a file (for custom coloring, analysis).

    Args:
        filename: Path to the attributes file (.defattr format)
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"defattr {quote_chimerax_arg(filename)}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Loaded attributes from {filename}")


# ---------------------------------------------------------------------------
# Tool 106: fly_camera
# ---------------------------------------------------------------------------

@mcp.tool()
async def fly_camera(
    positions: str,
    frames: int = 50,
    session_id: Optional[int] = None,
) -> str:
    """Smooth camera fly-through between named views.

    Views must be saved first with run_command('view name <name>').
    Use 'start' to include the current view.

    Args:
        positions: Space-separated list of named view positions (e.g., 'start pos1 pos2')
        frames: Frames per leg of the journey (default: 50)
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"fly {frames} {positions}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Camera fly-through: {positions}")


# ---------------------------------------------------------------------------
# Tool 107: get_coordinates
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_coordinates(
    target: str,
    session_id: Optional[int] = None,
) -> str:
    """Get XYZ coordinates for atoms (as centroid position).

    Note: Uses 'define centroid' internally because the 'getcrd' command
    returns numpy arrays that crash the REST JSON serializer.

    Args:
        target: Atomspec for atoms to get coordinates of (e.g., '#1/A:100@CA')
        session_id: ChimeraX session port (defaults to primary session)
    """
    target = validate_atomspec(target)
    command = f"define centroid {target}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Coordinates for {target}")


# ---------------------------------------------------------------------------
# Tool 108: set_graphics
# ---------------------------------------------------------------------------

@mcp.tool()
async def set_graphics(
    quality: float = 0.0,
    max_frame_rate: int = 0,
    silhouettes: bool = False,
    session_id: Optional[int] = None,
) -> str:
    """Control rendering quality and graphics settings.

    Each setting is a separate subcommand — multiple can be applied at once.

    Args:
        quality: Quality scale factor (1.0 = default, 2.0 = higher, 0.5 = lower; 0 = report current)
        max_frame_rate: Target max frame rate (0 = don't change)
        silhouettes: Enable edge silhouettes (default: False)
        session_id: ChimeraX session port (defaults to primary session)
    """
    results = []
    if quality > 0:
        r = await run_chimerax_command(f"graphics quality {quality}", session_id)
        results.append(r)
    if max_frame_rate > 0:
        r = await run_chimerax_command(f"graphics rate maxFrameRate {max_frame_rate}", session_id)
        results.append(r)
    if silhouettes:
        r = await run_chimerax_command("graphics silhouettes true", session_id)
        results.append(r)
    if not results:
        r = await run_chimerax_command("graphics", session_id)
        results.append(r)
    # Return the last result with all logs merged
    all_logs: dict = {}
    for r in results:
        for level, msgs in r.get("logs", {}).items():
            all_logs.setdefault(level, []).extend(msgs)
    combined = {"return_values": [], "json_values": [], "logs": all_logs}
    return format_chimerax_response(combined, "Graphics settings")


# ---------------------------------------------------------------------------
# Tool 109: show_hkcage
# ---------------------------------------------------------------------------

@mcp.tool()
async def show_hkcage(
    h: int = 1,
    k: int = 0,
    radius: float = 100.0,
    session_id: Optional[int] = None,
) -> str:
    """Display an icosahedral cage for virus capsid analysis.

    Args:
        h: H index of Caspar-Klug T-number (default: 1)
        k: K index (default: 0). T-number = h*h + h*k + k*k
        radius: Cage radius in Angstroms (default: 100)
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"hkcage {h} {k} radius {radius}"
    result = await run_chimerax_command(command, session_id)
    t = h*h + h*k + k*k
    return format_chimerax_response(result, f"Icosahedral cage T={t} (h={h}, k={k})")


# ---------------------------------------------------------------------------
# Tool 110: manage_log
# ---------------------------------------------------------------------------

@mcp.tool()
async def manage_log(
    action: str = "show",
    filename: str = "",
    session_id: Optional[int] = None,
) -> str:
    """Control the ChimeraX log panel.

    Args:
        action: 'show', 'hide', 'clear', 'save', 'errors' (show only errors)
        filename: File path for 'save' action
        session_id: ChimeraX session port (defaults to primary session)
    """
    if action == "save" and filename:
        command = f"log save {quote_chimerax_arg(filename)}"
    elif action in ("show", "hide", "clear", "errors"):
        command = f"log {action}"
    else:
        raise ValueError(f"Action must be 'show', 'hide', 'clear', 'save', or 'errors'")
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Log {action}")


# ---------------------------------------------------------------------------
# Tool 111: run_modeller
# ---------------------------------------------------------------------------

@mcp.tool()
async def run_modeller(
    target: str,
    action: str = "comparative",
    session_id: Optional[int] = None,
) -> str:
    """Run Modeller for homology modeling or loop refinement.

    Requires Modeller license key configured in ChimeraX.

    Args:
        target: Atomspec or sequence alignment reference
        action: 'comparative' (homology modeling) or 'loops' (loop refinement)
        session_id: ChimeraX session port (defaults to primary session)
    """
    if action not in ("comparative", "loops"):
        raise ValueError(f"Action must be 'comparative' or 'loops'")
    command = f"modeller {action} {target}"
    result = await run_chimerax_command(command, session_id, timeout=600)
    return format_chimerax_response(result, f"Modeller {action} for {target}")


# ---------------------------------------------------------------------------
# Tool 112: play_map_series
# ---------------------------------------------------------------------------

@mcp.tool()
async def play_map_series(
    model: str,
    action: str = "play",
    session_id: Optional[int] = None,
) -> str:
    """Play through a density map series (time-resolved data, morphs).

    Args:
        model: Model spec for the map series (e.g., '#2')
        action: 'play' (play forward), 'stop', 'slider' (show slider)
        session_id: ChimeraX session port (defaults to primary session)
    """
    model = validate_atomspec(model)
    if action not in ("play", "stop", "slider"):
        raise ValueError(f"Action must be 'play', 'stop', or 'slider'")
    command = f"mseries {model} {action}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Map series {action}: {model}")


# ---------------------------------------------------------------------------
# Tool 113: show_mutation_scores
# ---------------------------------------------------------------------------

@mcp.tool()
async def show_mutation_scores(
    target: str,
    session_id: Optional[int] = None,
) -> str:
    """Display mutation fitness/conservation scores on a structure.

    Args:
        target: Atomspec for the model (e.g., '#1')
        session_id: ChimeraX session port (defaults to primary session)
    """
    target = validate_atomspec(target)
    command = f"mutationscores {target}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Mutation scores for {target}")


# ---------------------------------------------------------------------------
# Tool 114: manage_pseudobonds
# ---------------------------------------------------------------------------

@mcp.tool()
async def manage_pseudobonds(
    target: str = "",
    color: str = "",
    radius: float = 0.0,
    dashes: int = 0,
    show: bool = True,
    session_id: Optional[int] = None,
) -> str:
    """Style or hide pseudobonds (H-bonds, crosslinks, distance monitors, etc.).

    Pseudobonds are styled via color/size commands on the pseudobond model.
    Use list_models() to find the pseudobond model spec (e.g., '#1.3').

    Args:
        target: Pseudobond model spec (e.g., '#1.3' for H-bond pseudobonds)
        color: Pseudobond color (e.g., 'cyan')
        radius: Pseudobond stick radius (0 = no change)
        dashes: Number of dashes (0 = solid; default = no change)
        show: Show (True) or hide (False) pseudobonds
        session_id: ChimeraX session port (defaults to primary session)
    """
    results = []
    if not show and target:
        results.append(await run_chimerax_command(f"hide {target} target pb", session_id))
    elif target:
        results.append(await run_chimerax_command(f"show {target} target pb", session_id))
        if color:
            results.append(await run_chimerax_command(f"color {target} {color}", session_id))
        if radius > 0:
            results.append(await run_chimerax_command(f"size {target} stickRadius {radius}", session_id))
        if dashes > 0:
            results.append(await run_chimerax_command(f"style {target} dashes {dashes}", session_id))
    all_logs: dict = {}
    for r in results:
        for level, msgs in r.get("logs", {}).items():
            all_logs.setdefault(level, []).extend(msgs)
    combined = {"return_values": [], "json_values": [], "logs": all_logs}
    return format_chimerax_response(combined, f"Pseudobonds {'hidden' if not show else 'styled'}")


# ---------------------------------------------------------------------------
# Tool 115: residue_fit_density
# ---------------------------------------------------------------------------

@mcp.tool()
async def residue_fit_density(
    model: str,
    map_model: str,
    session_id: Optional[int] = None,
) -> str:
    """Calculate per-residue density fit scores (for model validation).

    Args:
        model: Atomic model spec (e.g., '#1')
        map_model: Density map spec (e.g., '#2')
        session_id: ChimeraX session port (defaults to primary session)
    """
    model, map_model = validate_atomspec(model), validate_atomspec(map_model)
    command = f"resfit {model} inMap {map_model}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Residue fit scores: {model} in {map_model}")


# ---------------------------------------------------------------------------
# Tool 116: show_rna
# ---------------------------------------------------------------------------

@mcp.tool()
async def build_rna(
    pairs: str,
    sequence: str = "",
    length: int = 0,
    pattern: str = "circle",
    session_id: Optional[int] = None,
) -> str:
    """Build a rough 3D model of single-stranded RNA from base-pairing data.

    Args:
        pairs: Base-pairing info as comma-separated triples (e.g., '1,50,10,60,70,2')
               Each triple is: start1, start2, stem_length
        sequence: Amino acid sequence string or path to FASTA file (for atomic model)
        length: Total number of nucleotides (0 = auto from pairs)
        pattern: Layout pattern - 'circle', 'helix', 'line', 'sphere'
        session_id: ChimeraX session port (defaults to primary session)
    """
    if sequence:
        command = f"rna model {sequence} pairs {pairs}"
    else:
        command = f"rna path {pairs}"
    if length > 0:
        command += f" length {length}"
    if pattern != "circle":
        command += f" pattern {pattern}"
    result = await run_chimerax_command(command, session_id, timeout=120)
    return format_chimerax_response(result, f"RNA model built")


# ---------------------------------------------------------------------------
# Tool 117: roll_view
# ---------------------------------------------------------------------------

@mcp.tool()
async def roll_view(
    axis: str = "y",
    angle: float = 1.0,
    frames: int = 360,
    session_id: Optional[int] = None,
) -> str:
    """Continuous rotation (spin) around an axis.

    Args:
        axis: Rotation axis - 'x', 'y', 'z' (default: 'y')
        angle: Degrees per frame (default: 1.0)
        frames: Number of frames (default: 360 = one full rotation)
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"roll {axis} {angle} {frames}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Rolling {angle} deg/frame around {axis} for {frames} frames")


# ---------------------------------------------------------------------------
# Tool 118: show_topography
# ---------------------------------------------------------------------------

@mcp.tool()
async def show_topography(
    map_model: str,
    height: float = 0.0,
    session_id: Optional[int] = None,
) -> str:
    """Create a height-field surface from a 2D slice of volume data.

    Args:
        map_model: Volume model spec (e.g., '#2')
        height: Height scale factor (0 = auto)
        session_id: ChimeraX session port (defaults to primary session)
    """
    map_model = validate_atomspec(map_model)
    command = f"topography {map_model}"
    if height > 0:
        command += f" height {height}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Topography surface for {map_model}")


# ---------------------------------------------------------------------------
# Tool 119: wobble_view
# ---------------------------------------------------------------------------

@mcp.tool()
async def wobble_view(
    axis: str = "y",
    angle: float = 3.0,
    frames: int = 0,
    session_id: Optional[int] = None,
) -> str:
    """Oscillating rotation for depth perception (stereo-like effect).

    Args:
        axis: Primary wobble axis - 'x', 'y', 'z' (default: 'y')
        angle: Wobble angle in degrees (default: 3.0)
        frames: Duration in frames (0 = continuous until stopped)
        session_id: ChimeraX session port (defaults to primary session)
    """
    command = f"wobble {axis} {angle}"
    if frames > 0:
        command += f" {frames}"
    result = await run_chimerax_command(command, session_id)
    return format_chimerax_response(result, f"Wobble {angle} deg around {axis}")
