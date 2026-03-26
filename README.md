# ChimeraX MCP Server

A standalone [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server that connects AI coding assistants to [UCSF ChimeraX](https://www.cgl.ucsf.edu/chimerax/) for molecular visualization and structural biology workflows.

## About

ChimeraX MCP bridges the gap between conversational AI and molecular visualization. Instead of manually typing ChimeraX commands, you describe what you want in natural language — open structures, run analyses, generate publication figures — and the MCP server translates your intent into precise ChimeraX operations via its REST API.

The server handles everything automatically: discovering or launching ChimeraX instances, managing sessions across multiple ports, formatting results, and providing contextual error hints when something goes wrong.

**Key capabilities:**
- **48 specialized tools** covering the full structural biology workflow
- **Auto-launch** — ChimeraX starts automatically when needed, no manual setup
- **Multi-session** — work with multiple ChimeraX instances simultaneously
- **Input validation** — atomspec validation and error hints for common mistakes
- **Configurable** — environment variables for ports, paths, timeouts, and debug logging

```
AI Assistant  -->  MCP (stdio)  -->  chimerax-mcp (Python)  -->  HTTP REST  -->  ChimeraX
```

Inspired by the [RBVI official ChimeraX MCP bridge](https://github.com/RBVI/ChimeraX/tree/develop/src/bundles/mcp_server).

## Prerequisites

- [UCSF ChimeraX](https://www.cgl.ucsf.edu/chimerax/download.html) installed
- Python 3.11+
- [Claude Code CLI](https://claude.ai/code) or any MCP-compatible client

## Installation

```bash
git clone https://github.com/BenWertoski/chimeraX-mcp.git
cd chimeraX-mcp
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

## Setup

Add the MCP server to Claude Code:

```bash
claude mcp add chimerax -- .venv/bin/python -m chimerax_mcp
```

That's it. ChimeraX will auto-launch with REST enabled when you first use a tool.

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `CHIMERAX_PORT` | `8080` | Default ChimeraX REST server port |
| `CHIMERAX_PATH` | auto-detect | Path to ChimeraX executable |
| `CHIMERAX_TIMEOUT` | `60` | Default command timeout (seconds) |
| `CHIMERAX_DEBUG` | `false` | Enable debug logging (`1`, `true`, or `yes`) |

## Available Tools (48)

### Core (2)

| Tool | Description |
|------|-------------|
| `run_command` | Execute any ChimeraX command directly |
| `get_atomspec_guide` | Reference guide for atom specification syntax |

### Structure Management (5)

| Tool | Description |
|------|-------------|
| `open_structure` | Open PDB/mmCIF files or fetch from PDB/EMDB databases |
| `close_models` | Remove models from session |
| `list_models` | List all loaded models with display status and atom counts |
| `get_model_info` | Detailed model information including chains, atoms, bonds |
| `get_chain_info` | Chain-level details with sequence and residue info |

### Visualization (5)

| Tool | Description |
|------|-------------|
| `show_hide_objects` | Control visibility of atoms, bonds, cartoons, surfaces, models |
| `color_models` | Color structures and selections by any ChimeraX color |
| `get_shown` | Query current visibility state of all models |
| `save_image` | Save publication-quality screenshots (configurable resolution, transparency) |
| `set_scene` | Configure background color, lighting, silhouettes, camera mode |

### Analysis (11)

| Tool | Description |
|------|-------------|
| `measure_distance` | Measure distance between two atoms |
| `measure_angle` | Measure angle between three atoms |
| `measure_torsion` | Measure torsion/dihedral angle between four atoms |
| `measure_sasa` | Calculate solvent-accessible surface area |
| `measure_center` | Calculate geometric center of a selection |
| `measure_buried_area` | Buried surface area between two groups of atoms |
| `find_hbonds` | Hydrogen bond detection and analysis |
| `find_clashes` | Steric clash detection with configurable overlap cutoff |
| `align_structures` | Structural alignment via matchmaker (reports RMSD) |
| `view_residue` | Center view and rotation on a specific residue |
| `predict_structure` | AlphaFold or ESMFold structure prediction from sequence |

### Selection (2)

| Tool | Description |
|------|-------------|
| `select_atoms` | Select atoms/residues/chains with set, add, subtract, or clear modes |
| `select_zone` | Select everything within a distance of a target (zone selection) |

### Labels & Annotations (2)

| Tool | Description |
|------|-------------|
| `label_atoms` | Add/remove 3D text labels on atoms or residues |
| `label_2d` | Add 2D text overlays on the viewport (titles, annotations) |

### Surfaces (3)

| Tool | Description |
|------|-------------|
| `create_surface` | Generate molecular surfaces (solid, mesh, or dot styles) |
| `color_surface` | Color surfaces by electrostatics (coulombic), hydrophobicity (mlp), or B-factor |
| `set_transparency` | Set transparency on surfaces, cartoons, or atoms |

### Sequence (2)

| Tool | Description |
|------|-------------|
| `get_sequence` | Get chain sequence in FASTA format |
| `blast_search` | Run BLAST sequence search against PDB or other databases |

### Structure Editing (3)

| Tool | Description |
|------|-------------|
| `swap_residue` | Mutate a residue to a different amino acid |
| `add_hydrogens` | Add hydrogen atoms to a structure |
| `minimize_structure` | Energy minimize a structure (configurable steps, 5-min timeout) |

### Volume & Maps (3)

| Tool | Description |
|------|-------------|
| `fit_in_map` | Fit an atomic model into an electron density map |
| `measure_surface_area` | Measure area of a molecular surface |
| `measure_map_stats` | Get density map statistics (mean, RMS, min, max) |

### Session Management (6)

| Tool | Description |
|------|-------------|
| `save_session` | Save current session to a .cxs file |
| `open_session` | Restore a previously saved session |
| `get_session_info` | Full session overview (models, visibility, status) |
| `list_chimerax_instances` | List all running ChimeraX instances |
| `start_new_chimerax_session` | Launch a new ChimeraX instance |
| `check_chimerax_status` | Health check on a specific session |
| `set_default_session` | Change which session receives commands by default |

### Undo (1)

| Tool | Description |
|------|-------------|
| `undo_redo` | Undo or redo recent actions (configurable step count) |

### Documentation (2)

| Tool | Description |
|------|-------------|
| `list_chimerax_commands` | Browse all available ChimeraX commands |
| `get_command_documentation` | Get detailed documentation for any ChimeraX command |

## Usage Examples

Once configured, just ask Claude naturally:

```
"Open PDB structure 1GCN and show it as ribbons colored by chain"

"Find all hydrogen bonds in chain A"

"Measure the distance between residue 100 CA and residue 200 CA"

"Create a surface for the protein and color it by electrostatic potential"

"Select everything within 5 Angstroms of the ligand"

"Add a label to the active site residues"

"Save a publication-quality image with white background at 4K resolution"

"Predict the structure of this sequence: MKTLLILAVL..."

"Save this session so I can come back to it later"
```

## Development

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run tests (119 tests)
.venv/bin/pytest tests/ -v

# Enable debug logging
CHIMERAX_DEBUG=true .venv/bin/python -m chimerax_mcp
```

## Architecture

| Module | Role |
|--------|------|
| `server.py` | FastMCP instance, all 48 tool definitions, entry point |
| `chimera_rest.py` | REST client, auto-launch, instance discovery, session management |
| `formatting.py` | Response formatting, error hints, input validation |
| `docs.py` | Atomspec guide, ChimeraX command documentation (HTML to markdown) |

## License

MIT
