# ChimeraX MCP Server v0.2.0 — Bug Fixes, Infrastructure, and New Tools

## Overview

Harden the existing 38-tool MCP server with bug fixes, add infrastructure (logging, timeouts, input validation), complete test coverage, and add high-impact new tools for the most common structural biology workflows.

## Phase 1: Bug Fixes

### 1.1 Fix `superpose_residue` — source params unused

**Problem**: Takes `source_model/chain/residue` params but only runs commands against `target_*`. The `source_spec` is built then discarded. Tool name implies structural superposition but only recenters the camera.

**Fix**: Rename to `view_residue` with params `model`, `chain`, `residue`. Remove the unused source params entirely. Update docstring to accurately describe what it does (centers view + sets center of rotation).

### 1.2 Fix `set_scene` — discards ChimeraX results

**Problem**: Return values from `run_chimerax_command` are thrown away. Warnings and info messages are silently lost.

**Fix**: Collect results from each command and format with `format_chimerax_response`. Aggregate all log messages and present them.

### 1.3 Fix `is_chimerax_running` — creates new session per call

**Problem**: Creates a fresh `aiohttp.ClientSession` on every call. Called ~60 times during startup poll (30s × 2/s) and ~10 times during port scanning.

**Fix**: Use the shared session from `get_session()`. Fall back to a fresh session only if the shared session is unavailable (e.g., during early init before any command has run).

### 1.4 Fix `get_session_info` — duplicates `list_models` without atom counts

**Problem**: Copy-pastes model query logic but skips the `num_atoms` enrichment query. `format_single_model_info` shows "N/A" for atom counts.

**Fix**: Have `get_session_info` call `list_models()` directly for the model portion instead of reimplementing it.

### 1.5 Fix `show_hide_objects` — fragile count extraction

**Problem**: Hardcodes `note_logs[1]` for selection count. ChimeraX note ordering is version-dependent.

**Fix**: Search all note messages for a count pattern (e.g., regex matching `\d+ (atoms?|bonds?|residues?|models?)`). Fall back to "some" if no pattern matches.

### 1.6 Fix `cleanup()` atexit — asyncio.run() inside atexit

**Problem**: If the event loop is still running during shutdown, `asyncio.run()` raises `RuntimeError`.

**Fix**: Use synchronous close pattern. `aiohttp.ClientSession` tracks its connector — calling `connector.close()` synchronously is safe during atexit. Alternatively, try `asyncio.run()` and catch `RuntimeError` as a fallback.

### 1.7 Fix `blast_search` — always appends ellipsis

**Problem**: `query[:50]...` adds `"..."` even for short queries.

**Fix**: Only append `"..."` when `len(query) > 50`.

### 1.8 Remove unused `aioresponses` dev dependency

## Phase 2: Infrastructure

### 2.1 Logging

Add Python `logging` module throughout:
- `chimera_rest.py`: Log connection attempts, auto-launch, port discovery, command execution (DEBUG), errors (ERROR)
- `server.py`: Log tool invocations at DEBUG level
- `formatting.py`: Log when error hints are added

Use logger name `chimerax_mcp` with sub-loggers (`chimerax_mcp.rest`, `chimerax_mcp.tools`). No handler configuration — callers (Claude Code) provide that. Default to `NullHandler`.

### 2.2 Timeouts

Add `timeout` parameter to `run_chimerax_command()`:
- Default: 60 seconds for normal commands
- `predict_structure`: 300 seconds (5 min)
- `minimize_structure`: 300 seconds (5 min)
- `blast_search`: 120 seconds (2 min)

Pass `aiohttp.ClientTimeout(total=N)` to `_execute_command_request`.

### 2.3 Input Validation

Add `validate_atomspec(spec: str) -> str` utility in `formatting.py`:
- Strip whitespace
- Reject empty strings
- Reject obvious shell injection patterns (`;`, `&&`, `||`, `` ` ``, `$(`, `import os`)
- Note: ChimeraX commands are NOT shell commands, so the injection surface is limited to ChimeraX's own command parser. The main risk is `open` executing Python scripts. We log a warning for suspicious patterns but don't block — users may have legitimate use cases.

Apply to all tools that take `atomspec`, `target`, `model_id`, `chain_id` params.

For `run_command` specifically: Log a warning for commands containing `runscript` or `open` with `.py` extension, but do not block — the user controls what commands to run.

### 2.4 Configuration via Environment Variables

| Env Var | Default | Description |
|---------|---------|-------------|
| `CHIMERAX_PORT` | `8080` | Default REST port |
| `CHIMERAX_PATH` | auto-detect | Path to ChimeraX executable |
| `CHIMERAX_TIMEOUT` | `60` | Default command timeout (seconds) |
| `CHIMERAX_DEBUG` | `false` | Enable debug logging |

Read at module import time in `chimera_rest.py`. Override existing hardcoded values.

## Phase 3: Complete Test Coverage

Add tests for the 17 untested tools. Group by category:

**Session/instance tools** (mock `is_chimerax_running`, `list_running_instances`, `start_chimerax`):
- `list_chimerax_instances` — mock returns 2 instances
- `start_new_chimerax_session` — test success + no-executable case
- `check_chimerax_status` — running + not running
- `set_default_session` — success + not-running

**Documentation tools** (mock `list_available_commands`, `get_command_doc`):
- `list_chimerax_commands` — commands found + empty
- `get_command_documentation` — returns doc string

**Structure management** (mock `run_chimerax_command`):
- `list_models` — multi-model response with display + atoms enrichment
- `get_model_info` — full info with chains
- `get_chain_info` — chain data with sequence
- `open_structure` — basic + with emdb map
- `save_image` — default filename + custom filename

**Visualization**:
- `color_models` — basic color
- `show_hide_objects` — show + hide + invalid action
- `superpose_residue` → `view_residue` (post-rename)

**Error path tests** (in `test_formatting.py`):
- Test `format_chimerax_response` when logs exist alongside json_values (logs win)
- Test each error hint pattern fires correctly

**Infrastructure tests** (new file `tests/test_infrastructure.py`):
- Test `validate_atomspec` rejects empty, passes valid
- Test environment variable configuration loading
- Test timeout propagation

## Phase 4: New High-Impact Tools (10 new tools → 48 total)

### 4.1 Selection Tools

**`select_atoms`** — Select atoms/residues/chains with feedback
```python
async def select_atoms(atomspec: str, mode: str = "set", session_id=None) -> str:
    # mode: "set" (replace), "add", "subtract"
    # Commands: select (set), select add (add), ~select (clear) + select (for subtract)
```

**`select_zone`** — Select everything within a distance of a target
```python
async def select_zone(origin: str, distance: float, target_type: str = "residues", session_id=None) -> str:
    # Command: select zone {origin} {distance} {target_type} true
```

### 4.2 Label Tools

**`label_atoms`** — Add text labels to atoms/residues
```python
async def label_atoms(atomspec: str, text: str = "", attribute: str = "", height: float = 1.0, color: str = "", session_id=None) -> str:
    # Command: label {atomspec} [text "{text}"] [attribute {attr}] height {h} [color {c}]
```

**`label_2d`** — Add 2D text overlay to the viewport
```python
async def label_2d(text: str, x: float = 0.5, y: float = 0.95, size: int = 24, color: str = "white", session_id=None) -> str:
    # Command: 2dlabels text "{text}" xpos {x} ypos {y} size {size} color {color}
```

### 4.3 Session Persistence

**`save_session`** — Save ChimeraX session to file
```python
async def save_session(filename: str, session_id=None) -> str:
    # Command: save {filename}
    # Auto-append .cxs if no extension
```

**`open_session`** — Restore a saved session
```python
async def open_session(filename: str, session_id=None) -> str:
    # Command: open {filename}
```

### 4.4 Surface Tools

**`create_surface`** — Generate molecular surface
```python
async def create_surface(target: str = "all", style: str = "solid", resolution: float = 0.0, session_id=None) -> str:
    # Command: surface {target} [resolution {r}]
    # style: "solid", "mesh", "dot"
    # If style != solid: follow with "surface style {target} {style}"
```

**`color_surface`** — Color surface by electrostatics or hydrophobicity
```python
async def color_surface(target: str, method: str = "coulombic", palette: str = "", session_id=None) -> str:
    # method: "coulombic" (electrostatics), "mlp" (hydrophobicity), "bfactor"
    # Command: {method} {target} [palette {palette}]
```

**`set_transparency`** — Set transparency on surfaces or cartoons
```python
async def set_transparency(target: str, percent: int, what: str = "s", session_id=None) -> str:
    # what: "s" (surfaces), "c" (cartoons), "a" (atoms)
    # Command: transparency {target} {percent} target {what}
```

### 4.5 Undo/Redo

**`undo_redo`** — Undo or redo the last action
```python
async def undo_redo(action: str = "undo", count: int = 1, session_id=None) -> str:
    # Command: undo {count} or redo {count}
```

## Architecture Changes

### File Structure (no new files)

All changes stay in existing files:
- `server.py` — bug fixes + 10 new tool functions
- `chimera_rest.py` — logging, timeouts, session reuse, env vars
- `formatting.py` — `validate_atomspec()`, logging
- `tests/test_tools.py` — tests for 17 previously untested + 10 new tools
- `tests/test_infrastructure.py` — new file for validation/config tests
- `pyproject.toml` — remove `aioresponses`, bump version to 0.2.0

### Tool Count: 38 → 47

Remove 1 (superpose_residue → view_residue rename), add 10 new = 47 total tools.

Wait — the rename is in-place so it's still 38 existing + 10 new = 48 total, but `superpose_residue` becomes `view_residue` so the count is 38 - 1 + 1 + 10 = 48.

## Implementation Order

1. Bug fixes (Phase 1) — independent, can be done in one pass
2. Infrastructure (Phase 2) — logging and timeouts first, then validation, then config
3. New tools (Phase 4) — all 10 tools, straightforward pattern following
4. Tests (Phase 3) — cover everything at the end

## Success Criteria

- All existing 68 tests still pass
- New tests bring total to ~110+ passing tests
- No regressions in tool behavior
- Logging visible when `CHIMERAX_DEBUG=true`
- Timeouts fire correctly for long-running operations
- All new tools follow existing patterns (format_chimerax_response, session_id, etc.)
