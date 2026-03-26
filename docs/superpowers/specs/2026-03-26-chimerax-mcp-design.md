# ChimeraX MCP Server — Design Spec

## Overview

A standalone MCP (Model Context Protocol) server that connects Claude Code CLI to UCSF ChimeraX, enabling conversational molecular visualization, structural analysis, and protein science workflows. Built on top of the RBVI official ChimeraX MCP bridge (pre-alpha), extending it with additional tools, improved `run_command` guidance, and a frictionless standalone installation.

## Goals

- Zero-friction setup: `pip install` + one Claude Code CLI command
- Full-spectrum ChimeraX control via 25 tools
- Auto-launch ChimeraX with REST enabled — no manual setup
- Smart error handling that guides Claude to correct mistakes
- Built-in documentation access (atomspec guide, command reference)

## Non-Goals

- ChimeraX bundle installation (no `bundle_info.xml`, no `cmd.py` registration)
- Inline image return (save to file only; Claude reads via Read tool)
- MCP Resources (tools-only approach)
- GUI/web frontend

## Prior Art

Based on the RBVI official MCP server (`RBVI/ChimeraX` develop branch, `src/bundles/mcp_server/`), which provides:
- FastMCP-based bridge with M-to-N multi-instance support
- REST communication via aiohttp
- Contextual error hints
- Comprehensive atomspec guide
- Command documentation system (HTML to markdown)
- Auto-launch with daemon mode

Other existing solutions reviewed:
- ChatMol/molecule-mcp (minimal, 2 tools, XML-RPC)
- GDAmitha/chimerax-alphafold-mcp (AlphaFold-focused, 4 tools)
- jessicalh/chimerax-mcp (15 tools, broadest coverage)
- annihalated/chimerax-cast-mcp (cryo-EM domain-specific)

## Architecture

```
Claude Code CLI
     |
     | MCP protocol (stdio)
     v
chimerax-mcp (standalone Python process)
     |
     | HTTP GET/POST -> localhost:<port>/run
     v
ChimeraX (auto-launched with REST + JSON enabled)
```

### Key Decisions

1. **Standalone Python process** — no ChimeraX bundle installation needed
2. **Auto-launch ChimeraX** — daemon mode via double-fork (Unix) / DETACHED_PROCESS (Windows)
3. **Auto-discovery** — scans common ports for existing ChimeraX instances
4. **Multi-instance support** — tools accept optional `session_id` parameter
5. **FastMCP SDK** — `mcp.server.fastmcp.FastMCP`
6. **Async-first** — all REST communication via `aiohttp`

### Changes from RBVI Base

- Remove ChimeraX bundle dependencies (`bundle_info.xml`, `cmd.py`, `__init__.py` with BundleAPI)
- Standard `pip`-installable Python package
- Standalone `pyproject.toml` (not ChimeraX bundle format)
- Enhanced ChimeraX executable discovery (direct `/Applications/ChimeraX*.app` check on macOS)

## Package Structure

```
chimerax-mcp/
├── pyproject.toml          # Package metadata, dependencies, entry point
├── README.md               # Setup instructions
├── LICENSE                  # MIT
├── src/
│   └── chimerax_mcp/
│       ├── __init__.py     # Version
│       ├── server.py       # FastMCP server + all tool definitions
│       ├── chimera_rest.py # REST client (aiohttp), auto-launch, discovery
│       ├── formatting.py   # Response formatting, error hints
│       └── docs.py         # Command docs (HTML->markdown), atomspec guide
```

### Module Responsibilities

- **`server.py`** — FastMCP instance, all `@mcp.tool()` definitions, entry point
- **`chimera_rest.py`** — `find_chimerax_executable()`, `start_chimerax()`, `is_chimerax_running()`, `run_chimerax_command()`, `find_available_port()`, `find_best_chimerax_instance()`, port scanning, daemon launching, aiohttp session management
- **`formatting.py`** — `format_chimerax_response()`, `add_error_hints()`, all error pattern matching
- **`docs.py`** — `get_docs_path()`, `list_available_commands()`, `get_command_doc()`, atomspec guide text

### Dependencies

```
mcp[cli]          # Official MCP Python SDK with FastMCP
aiohttp           # Async HTTP for REST communication
beautifulsoup4    # HTML doc parsing
html2text         # HTML->markdown conversion
```

### Installation

```bash
pip install chimerax-mcp        # or: pip install -e . (from repo)
claude mcp add chimerax -- python -m chimerax_mcp
```

### Entry Points

```toml
[project.scripts]
chimerax-mcp = "chimerax_mcp.server:main"
```

Both `python -m chimerax_mcp` and `chimerax-mcp` work.

## Tool Inventory (25 tools)

### Retained from RBVI (14 tools)

| Tool | Purpose | Changes |
|------|---------|---------|
| `run_command` | Execute any ChimeraX command | Expanded docstring with common patterns |
| `get_atomspec_guide` | Atomspec syntax reference | Keep as-is |
| `list_models` | List loaded models | Keep as-is |
| `get_shown` | JSON visibility report | Keep as-is |
| `get_model_info` | Detailed model + chain info | Keep as-is |
| `get_chain_info` | Single chain details | Keep as-is |
| `color_models` | Color atomspecs | Keep as-is |
| `superpose_residue` | Align ligands by center-of-rotation | Keep as-is |
| `list_chimerax_commands` | Command discovery | Keep as-is |
| `get_command_documentation` | Command docs (HTML->markdown) | Keep as-is |
| `list_chimerax_instances` | List running sessions | Keep as-is |
| `start_new_chimerax_session` | Launch new instance | Keep as-is |
| `check_chimerax_status` | Health check | Keep as-is |
| `set_default_session` | Change default target | Keep as-is |

### Re-enabled from RBVI (3 tools)

| Tool | Purpose | Changes |
|------|---------|---------|
| `open_structure` | Open PDB/file with optional EMDB map | Un-comment |
| `save_image` | Save screenshot to file | Un-comment, add `transparent_background` param, auto-generated filename default |
| `show_hide_objects` | Show/hide representations with validation | Un-comment |

### New Tools (8 tools)

#### `measure_distance`
```python
async def measure_distance(
    atom1: str,       # Atomspec for first point (e.g., "#1/A:100@CA")
    atom2: str,       # Atomspec for second point (e.g., "#1/A:200@CA")
    session_id: Optional[int] = None
) -> str:
```
Runs `distance {atom1} {atom2}`, parses log output for numeric Angstrom value.

#### `find_hbonds`
```python
async def find_hbonds(
    target: str = "all",
    inter_model: bool = False,
    session_id: Optional[int] = None
) -> str:
```
Runs `hbonds {target} interModel {inter_model}`. Parses bond count and details.

#### `find_clashes`
```python
async def find_clashes(
    target: str,
    restrict: str = "both",
    overlap_cutoff: float = 0.6,
    session_id: Optional[int] = None
) -> str:
```
Runs `clashes {target} restrict {restrict} overlapCutoff {overlap_cutoff}`.

#### `align_structures`
```python
async def align_structures(
    match_model: str,
    ref_model: str,
    chain_pairing: str = "bb",
    session_id: Optional[int] = None
) -> str:
```
Runs `matchmaker {match_model} to {ref_model} pairing {chain_pairing}`. Parses RMSD and pair count.

#### `predict_structure`
```python
async def predict_structure(
    sequence: str,
    method: str = "alphafold",   # "alphafold" or "esmfold"
    session_id: Optional[int] = None
) -> str:
```
Validates sequence, runs `{method} predict {sequence}` with extended timeout (5 min).

#### `set_scene`
```python
async def set_scene(
    background: Optional[str] = None,
    lighting: Optional[str] = None,
    silhouettes: Optional[bool] = None,
    camera: Optional[str] = None,
    session_id: Optional[int] = None
) -> str:
```
Batches: `set bgColor`, `lighting`, `set silhouettes`, `camera`. Only runs commands for non-None params.

#### `close_models`
```python
async def close_models(
    target: str = "all",
    session_id: Optional[int] = None
) -> str:
```
Validates models exist (if not "all"), then runs `close {target}`.

#### `get_session_info`
```python
async def get_session_info(
    session_id: Optional[int] = None
) -> str:
```
Combines `list_models()` + `get_shown()` + instance status into single overview.

### Operations Handled by `run_command`

These are NOT dedicated tools. They're covered by the expanded `run_command` docstring:

- **Surfaces:** `surface #1`, `coulombic #1`, `mlp #1`, `transparency`
- **Labels:** `label #1/A:100 text "..."`, `2dlabels`, `label delete`
- **Camera:** `turn`, `zoom`, `view`, `clip`
- **Selections:** `select`, `~select`, `select zone`
- **Export:** `save ~/file.pdb`, `save ~/session.cxs`
- **Sequences:** `sequence chain #1/A`
- **Maps/Volumes:** `volume`, `fitmap`
- **Misc:** `log metadata`, `minimize`, `morph`, `crosslinks`

## `run_command` Docstring

The expanded docstring includes categorized command patterns:

- **SURFACES:** `surface`, `coulombic`, `mlp`, `transparency`
- **LABELS & ANNOTATIONS:** `label`, `2dlabels`, `label delete`
- **CAMERA & VIEW:** `turn`, `zoom`, `view`, `clip`
- **SELECTION:** `select`, `~select`, `select zone`
- **EXPORT & SAVE:** `save` (PDB, session, movie)
- **SEQUENCE:** `sequence chain`
- **MAPS & VOLUMES:** `volume`, `fitmap`
- **MISC:** `log metadata`, `minimize`, `morph`, `crosslinks`

Each with concrete examples that Claude can use directly.

## Error Handling

### Retained from RBVI

- Contextual error hints via `add_error_hints()` — regex-matches error types and suggests the right tool
- Cascading response formatting (logs -> JSON values -> Python values -> "success")
- Auto-retry on connection failure (starts ChimeraX, retries command)
- Pattern categories: atomspec errors, model errors, command errors, argument errors, file errors

### Improvements

1. **ChimeraX executable discovery** — add direct `/Applications/ChimeraX*.app` glob on macOS as primary fallback for standalone mode
2. **Startup progress** — stderr messages during 30-second startup wait so user knows it's working
3. **JSON mode enforcement** — if REST server responds without JSON, auto-run `remotecontrol rest start json true log true` to reconfigure
4. **Prediction timeouts** — `predict_structure` uses 5-minute aiohttp timeout
5. **Graceful cleanup** — close aiohttp session on exit, don't kill ChimeraX (user may want it open)
6. **Port collision handling** — `find_available_port()` scans upward from requested port
