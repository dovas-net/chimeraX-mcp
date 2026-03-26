"""FastMCP server for ChimeraX with all tool definitions."""

import asyncio
import atexit
import json
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
from chimerax_mcp.formatting import format_chimerax_response, format_single_model_info
from chimerax_mcp.docs import (
    get_atomspec_guide as _get_atomspec_guide,
    list_available_commands,
    get_command_doc,
)

mcp = FastMCP("ChimeraX Bridge")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    atexit.register(lambda: asyncio.run(cleanup()))
    mcp.run()


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
    command = f"color {target} {color}"
    result = await run_chimerax_command(command, session_id)
    context = f"Colored {target} with {color}"
    return format_chimerax_response(result, context)


# ---------------------------------------------------------------------------
# Tool 8: superpose_residue
# ---------------------------------------------------------------------------

@mcp.tool()
async def superpose_residue(
    source_model: str,
    source_chain: str,
    source_residue: str,
    target_model: str,
    target_chain: str,
    target_residue: str,
    session_id: Optional[int] = None,
) -> str:
    """Superpose view on a specific residue by aligning source to target position.

    This performs a two-step operation:
    1. Centers the view on the target residue
    2. Moves the center of rotation to that position

    Args:
        source_model: Source model ID (e.g., '1')
        source_chain: Source chain ID (e.g., 'A')
        source_residue: Source residue number (e.g., '100')
        target_model: Target model ID (e.g., '2')
        target_chain: Target chain ID (e.g., 'A')
        target_residue: Target residue number (e.g., '100')
        session_id: ChimeraX session port (defaults to primary session)
    """
    source_spec = f"#{source_model}/{source_chain}:{source_residue}"
    target_spec = f"#{target_model}/{target_chain}:{target_residue}"

    # Step 1: Center view on target residue
    view_command = f"view {target_spec}"
    await run_chimerax_command(view_command, session_id)

    # Step 2: Move center of rotation
    cofr_command = f"cofr {target_spec}"
    result = await run_chimerax_command(cofr_command, session_id)

    context = f"Superposed view: {source_spec} aligned to {target_spec}"
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

    command = f"open {identifier}" if format == "auto-detect" else f"open {identifier} format {format}"
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

    command = f"save {filename} width {width} height {height} supersample {supersample}"
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
    if any(letter not in "abcpsm" for letter in target):
        raise ValueError("Target must be one or more of 'a', 'b', 'p', 'c', 's', 'm'")

    # Select first for feedback on affected count
    select_result = await run_chimerax_command(f"select {atomspec}", session_id)
    note_logs = select_result.get("logs", {}).get("note", [])
    counts_string = note_logs[1] if len(note_logs) > 1 else "unknown count"
    counts_string = counts_string.replace(" selected", "")

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
    result = await run_chimerax_command(command, session_id)
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
        camera: Camera type ('perspective' or 'orthographic')
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
        commands.append(f"camera {camera}")

    if not commands:
        return "No scene properties specified. Provide at least one of: background, lighting, silhouettes, camera."

    results = []
    for cmd in commands:
        await run_chimerax_command(cmd, session_id)
        results.append(cmd)

    return f"Scene updated:\n" + "\n".join(f"  - {cmd}" for cmd in results)


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

    # Model list
    try:
        info_result = await run_chimerax_command("info models", session_id)
        model_rows = parse_info_json(info_result)
        if model_rows:
            output.append(f"\nModels ({len(model_rows)} loaded):")
            for row in model_rows:
                model = {
                    "spec": row.get("spec", "?"),
                    "name": row.get("value", row.get("name", "unknown")),
                    "class": row.get("class", ""),
                }
                lines = format_single_model_info(model)
                for line in lines:
                    output.append(f"  {line}")
        else:
            output.append("\nNo models loaded.")
    except Exception as e:
        output.append(f"\nCould not retrieve model info: {e}")

    # Visibility state
    try:
        display_result = await run_chimerax_command(
            "info models attribute display", session_id
        )
        display_rows = parse_info_json(display_result)
        if display_rows:
            visible_count = sum(
                1 for r in display_rows if r.get("value", False)
            )
            output.append(
                f"\nVisibility: {visible_count}/{len(display_rows)} "
                f"model(s) displayed"
            )
        else:
            output.append("\nNo visibility data available.")
    except Exception as e:
        output.append(f"\nCould not retrieve visibility info: {e}")

    return "\n".join(output)
