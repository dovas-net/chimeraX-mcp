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
    """Query chain attributes via the ChimeraX ``info chains`` command.

    Returns (formatted_text, chain_data_dict).
    """
    attributes = [
        "chain_id",
        "polymer_type",
        "description",
        "num_residues",
        "num_existing_residues",
    ]

    chain_data: dict = {}
    for attr in attributes:
        try:
            result = await run_chimerax_command(
                f"info chains #{model_id}/{chain_id} attribute {attr}",
                session_id,
            )
            json_values = result.get("json_values", [])
            if json_values:
                value = json_values[0]
                if isinstance(value, dict):
                    # The info command returns {atomspec: value} dicts
                    for spec, val in value.items():
                        chain_data[attr] = val
                        break
                else:
                    chain_data[attr] = value
        except Exception:
            chain_data[attr] = "N/A"

    # Format the chain info
    lines = []
    lines.append(f"Chain {chain_data.get('chain_id', chain_id)} of model #{model_id}:")
    lines.append(f"  Polymer type: {chain_data.get('polymer_type', 'N/A')}")
    lines.append(f"  Description: {chain_data.get('description', 'N/A')}")
    lines.append(f"  Residues: {chain_data.get('num_existing_residues', 'N/A')}/{chain_data.get('num_residues', 'N/A')}")

    text = "\n".join(lines)
    return text, chain_data


# ---------------------------------------------------------------------------
# Tool 3: list_models
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_models(session_id: Optional[int] = None) -> str:
    """List all models currently loaded in ChimeraX.

    Returns model IDs, names, types, visibility, and basic stats
    (atoms, bonds, residues, chains for atomic structures; size/step for volumes).

    Args:
        session_id: ChimeraX session port (defaults to primary session)
    """
    result = await run_chimerax_command("info", session_id)
    json_values = result.get("json_values", [])
    if not json_values:
        return "No models loaded"

    models = json_values[0] if json_values else []
    if not isinstance(models, list):
        models = [models]

    if not models:
        return "No models loaded"

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
    """Get visibility/shown status of all models and representations in ChimeraX.

    Returns JSON data showing which models, atoms, bonds, ribbons, and surfaces
    are currently visible.

    Args:
        session_id: ChimeraX session port (defaults to primary session)
    """
    result = await run_chimerax_command("info shown", session_id)
    json_values = result.get("json_values", [])
    if json_values:
        data = json_values[0]
        return json.dumps({"models": data}, indent=2)
    return json.dumps({"models": []}, indent=2)


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
    result = await run_chimerax_command("info", session_id)
    json_values = result.get("json_values", [])
    if not json_values:
        return f"Model #{model_id} not found (no models loaded)"

    models = json_values[0] if json_values else []
    if not isinstance(models, list):
        models = [models]

    # Find the requested model
    target_model = None
    for model in models:
        spec = str(model.get("spec", ""))
        if spec == str(model_id):
            target_model = model
            break

    if target_model is None:
        available = [str(m.get("spec", "?")) for m in models]
        return f"Model #{model_id} not found. Available models: {', '.join(available)}"

    # Format basic model info
    model_lines = format_single_model_info(target_model)
    output_lines = model_lines.copy()

    # Get chain info for each chain if it's an atomic structure
    chains = target_model.get("chains", [])
    if chains:
        output_lines.append("\nChain details:")
        for chain in chains:
            try:
                chain_text, _chain_data = await _get_chain_info_helper(
                    model_id, chain, session_id
                )
                output_lines.append(chain_text)
            except Exception as e:
                output_lines.append(f"  Chain {chain}: error getting details ({e})")

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
