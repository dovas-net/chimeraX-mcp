# ChimeraX MCP Server

Standalone MCP server connecting Claude Code CLI to UCSF ChimeraX for molecular visualization and structural analysis. 119 tools covering structure management, visualization, analysis, measurement, sequence, editing, volume/surface, selection, labels, surfaces, and session management.

## Architecture

```
Claude Code CLI → MCP (stdio) → chimerax-mcp (Python) → HTTP REST → ChimeraX
```

- `src/chimerax_mcp/server.py` — FastMCP instance, all 119 tool definitions, `main()` entry point
- `src/chimerax_mcp/chimera_rest.py` — REST client, auto-launch, instance discovery, `run_chimerax_command()`, `parse_info_json()`, env var config
- `src/chimerax_mcp/formatting.py` — response formatting, error hints, `validate_atomspec()`, logging
- `src/chimerax_mcp/docs.py` — atomspec guide, command doc lookup (HTML→markdown), ChimeraX installation discovery

## Development

`mcp` is pinned `<2`: mcp 2.x removed `mcp.server.fastmcp`.

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
.venv/bin/pytest tests/ -v

# Test against running ChimeraX (must have REST enabled on port 8080)
.venv/bin/python -c "
import asyncio
from chimerax_mcp.chimera_rest import run_chimerax_command, parse_info_json
async def test():
    r = await run_chimerax_command('info models', port=8080)
    print(parse_info_json(r))
asyncio.run(test())
"

# Add to Claude Code
claude mcp add chimerax -- .venv/bin/python -m chimerax_mcp
```

## Key Patterns

- All tools are `async def` decorated with `@mcp.tool()` in `server.py`
- Tools call `run_chimerax_command(command, session_id, timeout=N)` and format with `format_chimerax_response(result, context)`
- Use `validate_atomspec(spec)` on user-provided atomspec params before passing to commands
- Use `_model_spec(model_id)` for bare model-ID params (accepts `1` or `#1`; never build `f"#{model_id}"`)
- Validate all arguments before the first `run_chimerax_command` call so a bad argument has no side effects
- ChimeraX REST returns `json_values[0]` as a **JSON string** — always use `parse_info_json()` to parse
- The `info models` command returns `{spec, class, attribute, present, value}` rows — one attribute per query
- Error hints in `formatting.py` pattern-match ChimeraX errors and suggest the right tool to fix them
- Long-running tools use explicit timeouts: `predict_structure` (300s), `minimize_structure` (300s), `blast_search` (120s)

## Environment Variables

- `CHIMERAX_PORT` — default REST port (default: 8080)
- `CHIMERAX_PATH` — override ChimeraX executable path (default: auto-detect)
- `CHIMERAX_TIMEOUT` — default command timeout in seconds (default: 60)
- `CHIMERAX_DEBUG` — enable debug logging (set to `1`, `true`, or `yes`)

## ChimeraX REST API

- Endpoint: `http://localhost:<port>/run?command=<url-encoded-command>`
- JSON mode: `remotecontrol rest start port <N> json true log true`
- Response: `{"json values": [...], "python values": [...], "log messages": {...}, "error": null}`
- The REST server is a single-threaded `HTTPServer`: requests (including health probes) queue behind any running command
- `run_chimerax_command(port=None)` sends straight to the last known-good default port and only probes other ports if that fails; an explicit port never changes the default
- Non-JSON / non-200 replies raise an error explaining `json true`; timeouts raise an error naming `CHIMERAX_TIMEOUT`
- ChimeraX is auto-launched as a detached `subprocess.Popen` (new session, stdio → devnull, since our stdout is the MCP channel) if not running

## Testing

Tests mock `run_chimerax_command` with realistic ChimeraX JSON string responses. Use `make_result()` helper in `tests/test_tools.py`. Run with `.venv/bin/pytest` (the venv has all deps).

ChimeraX 1.11.1 is installed at `/Applications/ChimeraX-1.11.1.app/`.
