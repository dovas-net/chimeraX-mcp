# ChimeraX MCP Server

Standalone MCP server connecting Claude Code CLI to UCSF ChimeraX for molecular visualization and structural analysis. 38 tools covering structure management, visualization, analysis, measurement, sequence, editing, and volume/surface operations.

## Architecture

```
Claude Code CLI → MCP (stdio) → chimerax-mcp (Python) → HTTP REST → ChimeraX
```

- `src/chimerax_mcp/server.py` — FastMCP instance, all 38 tool definitions, `main()` entry point
- `src/chimerax_mcp/chimera_rest.py` — REST client, auto-launch, instance discovery, `run_chimerax_command()`, `parse_info_json()`
- `src/chimerax_mcp/formatting.py` — response formatting, error hints (`add_error_hints`, `format_chimerax_response`)
- `src/chimerax_mcp/docs.py` — atomspec guide, command doc lookup (HTML→markdown), ChimeraX installation discovery

## Development

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
- Tools call `run_chimerax_command(command, session_id)` and format with `format_chimerax_response(result, context)`
- ChimeraX REST returns `json_values[0]` as a **JSON string** — always use `parse_info_json()` to parse
- The `info models` command returns `{spec, class, attribute, present, value}` rows — one attribute per query
- Error hints in `formatting.py` pattern-match ChimeraX errors and suggest the right tool to fix them

## ChimeraX REST API

- Endpoint: `http://localhost:<port>/run?command=<url-encoded-command>`
- JSON mode: `remotecontrol rest start port <N> json true log true`
- Response: `{"json values": [...], "python values": [...], "log messages": {...}, "error": null}`
- ChimeraX is auto-launched as a daemon if not running (double-fork on Unix)

## Testing

Tests mock `run_chimerax_command` with realistic ChimeraX JSON string responses. Use `make_result()` helper in `tests/test_tools.py`. Run with `.venv/bin/pytest` (the venv has all deps).

ChimeraX 1.11.1 is installed at `/Applications/ChimeraX-1.11.1.app/`.
