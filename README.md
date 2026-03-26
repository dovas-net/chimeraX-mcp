# ChimeraX MCP Server

A standalone [MCP](https://modelcontextprotocol.io) server that connects Claude Code CLI to [UCSF ChimeraX](https://www.cgl.ucsf.edu/chimerax/) for molecular visualization and structural analysis.

Based on the [RBVI official ChimeraX MCP bridge](https://github.com/RBVI/ChimeraX/tree/develop/src/bundles/mcp_server).

## Prerequisites

- [UCSF ChimeraX](https://www.cgl.ucsf.edu/chimerax/download.html) installed
- Python 3.11+
- [Claude Code CLI](https://claude.ai/code)

## Installation

```bash
pip install chimerax-mcp
```

Or from source:

```bash
git clone <repo-url>
cd chimerax-mcp
pip install -e .
```

## Setup

Add the MCP server to Claude Code:

```bash
claude mcp add chimerax -- python -m chimerax_mcp
```

That's it. ChimeraX will auto-launch with REST enabled when you first use a tool.

## Available Tools (38)

### Core
- **run_command** - Execute any ChimeraX command directly
- **get_atomspec_guide** - Reference guide for atom specification syntax

### Structure Management
- **open_structure** - Open PDB files or fetch from database
- **close_models** - Remove models from session
- **list_models** - List all loaded models
- **get_model_info** - Detailed model information
- **get_chain_info** - Chain-level details

### Visualization
- **show_hide_objects** - Control visibility of representations
- **color_models** - Color structures and selections
- **get_shown** - Current visibility state
- **save_image** - Save screenshots
- **set_scene** - Configure lighting, background, camera

### Analysis
- **measure_distance** - Measure atomic distances
- **find_hbonds** - Hydrogen bond analysis
- **find_clashes** - Steric clash detection
- **align_structures** - Structural alignment (matchmaker)
- **superpose_residue** - Ligand superposition
- **measure_angle** - Measure the angle between three atoms
- **measure_torsion** - Measure the torsion angle between four atoms
- **measure_sasa** - Solvent-accessible surface area calculation
- **measure_center** - Calculate center of mass for a selection
- **measure_buried_area** - Buried surface area between two chains

### Sequence
- **get_sequence** - Get the sequence of a chain in FASTA format
- **blast_search** - Run BLAST sequence search against PDB

### Structure Editing
- **swap_residue** - Mutate a residue to a different amino acid
- **add_hydrogens** - Add hydrogen atoms to a structure
- **minimize_structure** - Energy minimize a structure

### Prediction
- **predict_structure** - AlphaFold/ESMFold structure prediction

### Volume & Maps
- **fit_in_map** - Fit atomic model into an electron density map
- **measure_surface_area** - Measure surface area of a molecular surface
- **measure_map_stats** - Get density map statistics (mean, RMS, min, max)

### Session Management
- **get_session_info** - Full session overview
- **list_chimerax_instances** - List running instances
- **start_new_chimerax_session** - Launch new instance
- **check_chimerax_status** - Health check
- **set_default_session** - Change default target

### Documentation
- **list_chimerax_commands** - Browse available commands
- **get_command_documentation** - Detailed command docs

## Usage Examples

Once configured, just ask Claude naturally:

- "Open PDB structure 1GCN and show it as ribbons colored by chain"
- "Find all hydrogen bonds in chain A"
- "Measure the distance between residue 100 CA and residue 200 CA in chain A"
- "Save a publication-quality image with white background"
- "Predict the structure of this sequence: MKTLLILAVL..."

## License

MIT
