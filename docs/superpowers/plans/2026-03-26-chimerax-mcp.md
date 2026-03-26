# ChimeraX MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone MCP server that connects Claude Code CLI to UCSF ChimeraX for molecular visualization and analysis, based on the RBVI official bridge.

**Architecture:** Standalone Python process communicating with ChimeraX via its REST API. Auto-launches ChimeraX with REST enabled. 25 MCP tools: 14 retained from RBVI, 3 re-enabled, 8 new.

**Tech Stack:** Python 3.11+, FastMCP (mcp SDK), aiohttp, beautifulsoup4, html2text, pytest + pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-03-26-chimerax-mcp-design.md`

**RBVI source reference:** The full RBVI bridge source is cached at `.claude/projects/-Users-docas-Desktop-chimeraX-mcp/6dc734a1-f89e-4a27-8877-d2c46d39bc61/tool-results/toolu_0145JxysLgSunmnkGqTbtUHb.txt` — consult this for exact RBVI implementations when porting tools.

---

## File Map

| File | Responsibility | Status |
|------|---------------|--------|
| `pyproject.toml` | Package metadata, deps, entry points | Create |
| `src/chimerax_mcp/__init__.py` | Version string | Create |
| `src/chimerax_mcp/__main__.py` | `python -m chimerax_mcp` support | Create |
| `src/chimerax_mcp/formatting.py` | Response formatting, error hints, model info formatting | Create |
| `src/chimerax_mcp/docs.py` | Atomspec guide, command doc lookup (HTML->markdown) | Create |
| `src/chimerax_mcp/chimera_rest.py` | REST client, auto-launch, discovery, daemon mode | Create |
| `src/chimerax_mcp/server.py` | FastMCP instance, all 25 tool definitions, main() | Create |
| `tests/test_formatting.py` | Unit tests for formatting module | Create |
| `tests/test_docs.py` | Unit tests for docs module | Create |
| `tests/test_chimera_rest.py` | Unit tests for REST client (mocked HTTP) | Create |
| `tests/test_tools.py` | Unit tests for new tool functions (mocked REST) | Create |

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/chimerax_mcp/__init__.py`
- Create: `src/chimerax_mcp/__main__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p src/chimerax_mcp tests
```

- [ ] **Step 2: Create pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "chimerax-mcp"
version = "0.1.0"
description = "MCP server for UCSF ChimeraX molecular visualization"
readme = "README.md"
license = "MIT"
requires-python = ">=3.11"
authors = [
    {name = "ChimeraX MCP Contributors"}
]
dependencies = [
    "mcp[cli]>=1.0.0",
    "aiohttp>=3.9.0",
    "beautifulsoup4>=4.12.0",
    "html2text>=2024.2.26",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "aioresponses>=0.7",
]

[project.scripts]
chimerax-mcp = "chimerax_mcp.server:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 3: Create `src/chimerax_mcp/__init__.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 4: Create `src/chimerax_mcp/__main__.py`**

```python
from chimerax_mcp.server import main

main()
```

- [ ] **Step 5: Create `tests/__init__.py`**

Empty file.

- [ ] **Step 6: Install in dev mode and verify**

```bash
pip install -e ".[dev]"
```

Expected: installs successfully with all dependencies.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/ tests/__init__.py
git commit -m "feat: project scaffolding with pyproject.toml and package structure"
```

---

## Task 2: Formatting Module

**Files:**
- Create: `src/chimerax_mcp/formatting.py`
- Create: `tests/test_formatting.py`

- [ ] **Step 1: Write tests for `format_chimerax_response`**

```python
# tests/test_formatting.py
from chimerax_mcp.formatting import format_chimerax_response, add_error_hints, format_single_model_info


class TestFormatChimeraXResponse:
    def test_logs_priority(self):
        """Logs are shown first when present."""
        result = {
            "return_values": ["some_value"],
            "json_values": [{"key": "val"}],
            "logs": {"info": ["Structure opened successfully"]},
        }
        output = format_chimerax_response(result)
        assert "INFO: Structure opened successfully" in output

    def test_json_fallback_when_no_logs(self):
        """JSON values shown when logs are empty."""
        result = {
            "return_values": [],
            "json_values": [{"atoms": 100}],
            "logs": {},
        }
        output = format_chimerax_response(result)
        assert "JSON Output" in output
        assert '"atoms": 100' in output

    def test_python_values_fallback(self):
        """Python values shown when no logs and no JSON."""
        result = {
            "return_values": [42],
            "json_values": [],
            "logs": {},
        }
        output = format_chimerax_response(result)
        assert "Output" in output
        assert "42" in output

    def test_success_when_empty(self):
        """Returns success message when all outputs are empty."""
        result = {"return_values": [], "json_values": [], "logs": {}}
        output = format_chimerax_response(result)
        assert "Command completed successfully" in output

    def test_context_prepended(self):
        """Context string appears at start of output."""
        result = {"return_values": [], "json_values": [], "logs": {"info": ["done"]}}
        output = format_chimerax_response(result, context="Opened 1abc")
        assert output.startswith("Opened 1abc")

    def test_filters_markdown_link_echoes(self):
        """Command echo lines with markdown links are filtered out."""
        result = {
            "return_values": [],
            "json_values": [],
            "logs": {"info": ["[open](cmd:open) [1abc](cmd:1abc) more links", "Real info"]},
        }
        output = format_chimerax_response(result)
        assert "Real info" in output
        assert "cmd:open" not in output

    def test_none_values_filtered(self):
        """None values in json_values and return_values are excluded."""
        result = {
            "return_values": [None, 42, None],
            "json_values": [],
            "logs": {},
        }
        output = format_chimerax_response(result)
        assert "42" in output

    def test_multiple_log_levels(self):
        """Multiple log levels shown in severity order."""
        result = {
            "return_values": [],
            "json_values": [],
            "logs": {
                "warning": ["Low resolution"],
                "info": ["Model loaded"],
            },
        }
        output = format_chimerax_response(result)
        warn_pos = output.index("WARNING")
        info_pos = output.index("INFO")
        assert warn_pos < info_pos


class TestAddErrorHints:
    def test_atomspec_error(self):
        """Atomspec errors suggest get_atomspec_guide()."""
        msg = add_error_hints("UserError", "Expected an objects specifier", "color foo red")
        assert "get_atomspec_guide()" in msg
        assert "#1" in msg

    def test_no_models_error(self):
        """Model errors suggest list_models()."""
        msg = add_error_hints("UserError", "No models specified by #5", "color #5 red")
        assert "list_models()" in msg

    def test_unknown_command_error(self):
        """Unknown command errors suggest list_chimerax_commands()."""
        msg = add_error_hints("UserError", "Unknown command: foobar", "foobar #1")
        assert "list_chimerax_commands()" in msg
        assert "foobar" in msg

    def test_argument_error(self):
        """Argument errors suggest get_command_documentation()."""
        msg = add_error_hints("UserError", "Missing or invalid width argument", "save img.png width")
        assert "get_command_documentation()" in msg

    def test_file_error(self):
        """File errors suggest absolute paths."""
        msg = add_error_hints("UserError", "File not found: bad.pdb", "open bad.pdb")
        assert "absolute paths" in msg

    def test_generic_error(self):
        """Unrecognized errors get generic hints."""
        msg = add_error_hints("InternalError", "something weird happened", "weird")
        assert "HINT" in msg

    def test_no_atoms_matched(self):
        """No atoms matched suggests checking chain IDs."""
        msg = add_error_hints("UserError", "no atoms matched specification", "select #1/Z")
        assert "list_models()" in msg
        assert "chain IDs" in msg


class TestFormatSingleModelInfo:
    def test_atomic_structure(self):
        """Formats atomic structure with atoms, bonds, residues, chains."""
        model = {
            "spec": "1",
            "name": "1abc",
            "shown": True,
            "num atoms": 5000,
            "num bonds": 5100,
            "num residues": 300,
            "chains": ["A", "B"],
        }
        lines = format_single_model_info(model)
        assert "#1, 1abc, shown" in lines[0]
        assert "5000 atoms" in lines[1]
        assert "2 chains (A,B)" in lines[1]

    def test_volume_model(self):
        """Formats volume model with size and level info."""
        model = {
            "spec": "2",
            "name": "map",
            "shown": True,
            "size": [400, 400, 400],
            "step": 1,
            "voxel size": 1.06,
            "surface levels": [5.0],
            "minimum value": -3.0,
            "maximum value": 12.0,
            "value type": "float32",
            "num symmetry operators": 0,
        }
        lines = format_single_model_info(model)
        combined = " ".join(lines)
        assert "size 400,400,400" in combined
        assert "level 5.0" in combined

    def test_hidden_model(self):
        """Hidden models show 'hidden' status."""
        model = {"spec": "3", "name": "test", "shown": False}
        lines = format_single_model_info(model)
        assert "hidden" in lines[0]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_formatting.py -v
```

Expected: ImportError — `chimerax_mcp.formatting` does not exist yet.

- [ ] **Step 3: Implement `formatting.py`**

Create `src/chimerax_mcp/formatting.py` with the following functions ported from the RBVI bridge (`chimerax_mcp_bridge.py`):

- `format_chimerax_response(result: dict, context: str = "") -> str` — cascading fallback: logs -> JSON values -> Python values -> "success". Filters markdown link echoes and None values. Formats log levels in severity order.
- `add_error_hints(error_type: str, error_msg: str, command: str) -> str` — pattern-matches error messages and appends contextual hints suggesting the right tool. Categories: atomspec errors, no-atoms-matched, model errors, command errors, argument errors, file errors, generic fallback.
- `format_single_model_info(model: dict) -> list[str]` — formats a single model dict from ChimeraX `info` command into display lines. Handles AtomicStructure (atoms/bonds/residues/chains/pseudobond groups), Volume (size/step/voxel/levels/range), Surface (triangles), and generic models.

Port these three functions exactly from the RBVI bridge source. The RBVI source is cached at `.claude/projects/-Users-docas-Desktop-chimeraX-mcp/6dc734a1-f89e-4a27-8877-d2c46d39bc61/tool-results/toolu_0145JxysLgSunmnkGqTbtUHb.txt`. The functions to port are:
- `format_chimerax_response` (line 570-650 in cached file)
- `add_error_hints` (line 652-795)
- `_format_single_model_info` (line 1065-1161) — rename to `format_single_model_info` (public)

No modifications needed to logic — just move into this module with proper imports.

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_formatting.py -v
```

Expected: All 14 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/chimerax_mcp/formatting.py tests/test_formatting.py
git commit -m "feat: add formatting module with response formatting and error hints"
```

---

## Task 3: Documentation Module

**Files:**
- Create: `src/chimerax_mcp/docs.py`
- Create: `tests/test_docs.py`

- [ ] **Step 1: Write tests for docs module**

```python
# tests/test_docs.py
import os
import tempfile
from unittest.mock import patch
from chimerax_mcp.docs import get_atomspec_guide, get_docs_path, list_available_commands, get_command_doc


class TestAtomspecGuide:
    def test_returns_string(self):
        guide = get_atomspec_guide()
        assert isinstance(guide, str)
        assert len(guide) > 1000

    def test_contains_key_sections(self):
        guide = get_atomspec_guide()
        assert "Hierarchical Specifiers" in guide
        assert "Built-in Classifications" in guide
        assert "Zones" in guide
        assert "Attributes" in guide
        assert "Combinations" in guide
        assert "Quick Reference" in guide

    def test_contains_examples(self):
        guide = get_atomspec_guide()
        assert "#1/A:100" in guide
        assert "@ca" in guide
        assert "protein" in guide
        assert "ligand" in guide


class TestGetDocsPath:
    def test_returns_none_when_no_chimerax(self):
        with patch("chimerax_mcp.docs._find_chimerax_installation_directory", return_value=None):
            assert get_docs_path() is None

    def test_returns_path_when_chimerax_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_path = os.path.join(tmpdir, "Contents", "share", "docs")
            os.makedirs(docs_path)
            with patch("chimerax_mcp.docs._find_chimerax_installation_directory", return_value=tmpdir):
                with patch("sys.platform", "darwin"):
                    result = get_docs_path()
                    assert result == docs_path


class TestListAvailableCommands:
    def test_empty_when_no_docs(self):
        with patch("chimerax_mcp.docs.get_docs_path", return_value=None):
            assert list_available_commands() == []

    def test_finds_html_commands(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_dir = os.path.join(tmpdir, "user", "commands")
            os.makedirs(cmd_dir)
            for name in ["open.html", "color.html", "save.html"]:
                open(os.path.join(cmd_dir, name), "w").close()
            with patch("chimerax_mcp.docs.get_docs_path", return_value=tmpdir):
                commands = list_available_commands()
                assert "open" in commands
                assert "color" in commands
                assert "save" in commands
                assert commands == sorted(commands)


class TestGetCommandDoc:
    def test_returns_error_when_no_docs(self):
        with patch("chimerax_mcp.docs.get_docs_path", return_value=None):
            result = get_command_doc("open")
            assert "not found" in result.lower()

    def test_converts_html_to_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_dir = os.path.join(tmpdir, "user", "commands")
            os.makedirs(cmd_dir)
            with open(os.path.join(cmd_dir, "open.html"), "w") as f:
                f.write("<html><body><h1>Open Command</h1><p>Opens a file.</p></body></html>")
            with patch("chimerax_mcp.docs.get_docs_path", return_value=tmpdir):
                result = get_command_doc("open")
                assert "Open Command" in result
                assert "Opens a file" in result
                assert "# ChimeraX Command: open" in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_docs.py -v
```

Expected: ImportError — module does not exist.

- [ ] **Step 3: Implement `docs.py`**

Create `src/chimerax_mcp/docs.py` with the following:

- `ATOMSPEC_GUIDE: str` — the complete atomspec guide text (port the string returned by `get_atomspec_guide()` in the RBVI bridge, lines 812-984 of the cached source)
- `get_atomspec_guide() -> str` — returns `ATOMSPEC_GUIDE`
- `_find_chimerax_installation_directory() -> Optional[str]` — port from RBVI (lines 99-118). Walks up from `sys.executable` and `__file__` looking for platform-specific parent dirs. **Enhancement:** also try globbing `/Applications/ChimeraX*.app` on macOS as a standalone fallback.
- `_find_parent_directory(path: str, dir_name: str) -> Optional[str]` — port from RBVI (lines 120-128)
- `get_docs_path() -> Optional[str]` — port from RBVI (lines 332-349). Locates ChimeraX docs directory.
- `list_available_commands() -> list[str]` — port from RBVI (lines 351-367). Lists HTML files in commands dir.
- `get_command_doc(command_name: str) -> str` — port from RBVI (lines 369-428). Converts HTML docs to markdown using BeautifulSoup + html2text. Pre-processes `<br>` in table cells, strips copyright header and footer.

The `_find_chimerax_installation_directory` function needs this enhancement for standalone mode:

```python
def _find_chimerax_installation_directory() -> Optional[str]:
    """Find ChimeraX installation directory.

    Tries multiple strategies:
    1. Walk up from sys.executable (works when running inside ChimeraX's Python)
    2. Walk up from this file's location
    3. Glob /Applications/ChimeraX*.app on macOS (standalone fallback)
    """
    import sys
    from sys import platform as sys_platform

    for base_path in [os.path.realpath(sys.executable), os.path.abspath(__file__)]:
        if sys_platform == 'darwin':
            cdir = _find_parent_directory(base_path, 'Contents')
        elif sys_platform == 'win32':
            cdir = _find_parent_directory(base_path, 'bin')
        else:
            cdir = _find_parent_directory(base_path, 'lib')
        if cdir:
            return os.path.dirname(cdir)

    # Standalone fallback: glob for ChimeraX app on macOS
    if sys_platform == 'darwin':
        import glob
        matches = sorted(glob.glob('/Applications/ChimeraX*.app'), reverse=True)
        if matches:
            return matches[0]  # Most recent version

    return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_docs.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/chimerax_mcp/docs.py tests/test_docs.py
git commit -m "feat: add docs module with atomspec guide and command documentation"
```

---

## Task 4: REST Client Module

**Files:**
- Create: `src/chimerax_mcp/chimera_rest.py`
- Create: `tests/test_chimera_rest.py`

- [ ] **Step 1: Write tests for REST client**

```python
# tests/test_chimera_rest.py
import asyncio
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from chimerax_mcp.chimera_rest import (
    find_chimerax_executable,
    find_available_port,
    get_chimerax_url,
    is_chimerax_running,
    run_chimerax_command,
)


class TestFindChimeraXExecutable:
    def test_returns_none_when_not_found(self):
        with patch("chimerax_mcp.chimera_rest._find_chimerax_installation_directory", return_value=None):
            assert find_chimerax_executable() is None

    def test_finds_macos_executable(self, tmp_path):
        exe = tmp_path / "Contents" / "MacOS" / "ChimeraX"
        exe.parent.mkdir(parents=True)
        exe.touch()
        with patch("chimerax_mcp.chimera_rest._find_chimerax_installation_directory", return_value=str(tmp_path)):
            with patch("sys.platform", "darwin"):
                result = find_chimerax_executable()
                assert result == str(exe)


class TestFindAvailablePort:
    def test_finds_open_port(self):
        port = find_available_port(49152)
        assert 49152 <= port < 49252

    def test_skips_bound_ports(self):
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("localhost", 49200))
        try:
            port = find_available_port(49200)
            assert port != 49200
        finally:
            sock.close()


class TestGetChimeraXUrl:
    def test_default_port(self):
        url = get_chimerax_url(8080)
        assert url == "http://localhost:8080"

    def test_custom_port(self):
        url = get_chimerax_url(9000)
        assert url == "http://localhost:9000"


class TestIsChimeraXRunning:
    @pytest.mark.asyncio
    async def test_returns_false_when_not_running(self):
        result = await is_chimerax_running(59999)
        assert result is False


class TestRunChimeraXCommand:
    @pytest.mark.asyncio
    async def test_raises_on_connection_error_no_executable(self):
        with patch("chimerax_mcp.chimera_rest.find_chimerax_executable", return_value=None):
            with pytest.raises(Exception, match="Cannot connect"):
                await run_chimerax_command("open 1abc", port=59999)

    @pytest.mark.asyncio
    async def test_parses_successful_json_response(self):
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "python values": [None],
            "json values": [None],
            "log messages": {"info": ["Opened 1abc"]},
            "error": None,
        })
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        with patch("chimerax_mcp.chimera_rest.get_session", return_value=mock_session):
            with patch("chimerax_mcp.chimera_rest.is_chimerax_running", return_value=True):
                with patch("chimerax_mcp.chimera_rest.find_best_chimerax_instance", return_value=8080):
                    result = await run_chimerax_command("open 1abc")
                    assert result["logs"]["info"] == ["Opened 1abc"]

    @pytest.mark.asyncio
    async def test_raises_on_chimerax_error(self):
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "python values": [],
            "json values": [],
            "log messages": {},
            "error": {"type": "UserError", "message": "Unknown command: foobar"},
        })
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)

        with patch("chimerax_mcp.chimera_rest.get_session", return_value=mock_session):
            with patch("chimerax_mcp.chimera_rest.is_chimerax_running", return_value=True):
                with patch("chimerax_mcp.chimera_rest.find_best_chimerax_instance", return_value=8080):
                    with pytest.raises(Exception, match="Unknown command"):
                        await run_chimerax_command("foobar")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_chimera_rest.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `chimera_rest.py`**

Create `src/chimerax_mcp/chimera_rest.py`. Port the following functions from the RBVI bridge:

**Constants:**
```python
CHIMERAX_HOST = 'localhost'
DEFAULT_CHIMERAX_PORT = 8080
DEBUG = False

_instances: dict = {}
_default_port: int = DEFAULT_CHIMERAX_PORT
_session = None  # aiohttp.ClientSession
```

**Functions to port (reference lines in cached RBVI source):**

- `find_chimerax_executable() -> Optional[str]` (lines 80-97) — uses `_find_chimerax_installation_directory` from `docs.py` module. Platform-specific exe path construction.
- `find_available_port(start_port: int = 8080) -> int` (lines 130-140) — scans for available port.
- `is_chimerax_running(port: Optional[int] = None) -> bool` (lines 142-154) — async GET to `/cmdline.html` with 1s timeout.
- `get_chimerax_url(port: Optional[int] = None) -> str` (lines 156-160)
- `get_session() -> aiohttp.ClientSession` (lines 433-438) — lazy singleton.
- `list_running_instances() -> dict` (lines 162-176) — checks known + scans 8080-8089.
- `start_chimerax_daemon(port: int) -> bool` (lines 178-215) — Unix double-fork.
- `check_existing_rest_server() -> tuple[bool, int]` (lines 217-247) — scans for existing REST servers.
- `start_chimerax(port, session_name, force_new) -> tuple[bool, int]` (lines 249-326) — auto-start with 30s wait. **Enhancement:** add stderr progress messages during wait.
- `find_best_chimerax_instance() -> int` (lines 440-468) — prefer default port, scan alternatives.
- `_execute_command_request(session, url, command, timeout=None) -> dict` (lines 470-525) — HTTP GET, JSON parse, error handling with `add_error_hints`. The optional `timeout` param accepts an `aiohttp.ClientTimeout` to override default (used by `predict_structure` for 5-min timeout).
- `run_chimerax_command(command, port) -> dict` (lines 528-568) — main entry point, auto-discovery, auto-start fallback on `ClientConnectorError`.
- `ensure_json_mode(port) -> None` — **New function.** If a REST response is not valid JSON, auto-run `remotecontrol rest start json true log true` to reconfigure. Called as a fallback inside `_execute_command_request` when `response.json()` raises `ContentTypeError`.
- `cleanup()` (lines 1886-1891) — close aiohttp session.

**Key import from formatting module:**
```python
from chimerax_mcp.formatting import add_error_hints
```

**Key import from docs module:**
```python
from chimerax_mcp.docs import _find_chimerax_installation_directory
```

**Enhancement for `start_chimerax`:** Add progress messages during the 30-second wait loop:

```python
for i in range(30):
    await asyncio.sleep(1)
    if await is_chimerax_running(port):
        print(f"ChimeraX started successfully on port {port}!", file=sys.stderr)
        _instances[port]["status"] = "running"
        return True, port
    if i % 5 == 4:
        print(f"Still waiting for ChimeraX to start... ({i+1}s)", file=sys.stderr)
```

**Enhancement for `find_chimerax_executable`:** Use `_find_chimerax_installation_directory` from `docs.py` which already has the macOS glob fallback.

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_chimera_rest.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/chimerax_mcp/chimera_rest.py tests/test_chimera_rest.py
git commit -m "feat: add REST client module with auto-launch and discovery"
```

---

## Task 5: Server Entry Point + Retained Tools

**Files:**
- Create: `src/chimerax_mcp/server.py`

This is the largest task. It creates the FastMCP server with all 14 retained tools + the enhanced `run_command` docstring.

- [ ] **Step 1: Create server.py with FastMCP instance, imports, and main()**

```python
# src/chimerax_mcp/server.py
import asyncio
import atexit
import json
import sys
from typing import Optional

from mcp.server.fastmcp import FastMCP

from chimerax_mcp.chimera_rest import (
    run_chimerax_command,
    is_chimerax_running,
    start_chimerax,
    find_chimerax_executable,
    find_available_port,
    list_running_instances,
    cleanup,
    _instances,
    _default_port,
)
from chimerax_mcp.formatting import format_chimerax_response, format_single_model_info
from chimerax_mcp.docs import get_atomspec_guide as _get_atomspec_guide, list_available_commands, get_command_doc

mcp = FastMCP("ChimeraX Bridge")


def main():
    atexit.register(lambda: asyncio.run(cleanup()))
    mcp.run()
```

- [ ] **Step 2: Add `run_command` with enhanced docstring**

Add to `server.py`:

```python
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
```

- [ ] **Step 3: Add `get_atomspec_guide` tool**

```python
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
```

- [ ] **Step 4: Add model info tools (list_models, get_shown, get_model_info, get_chain_info)**

Port these 4 tools from the RBVI bridge. They use `run_chimerax_command` and `format_chimerax_response` from our modules. Key functions:

- `list_models(session_id)` — runs `info`, parses JSON, formats with `format_single_model_info`
- `get_shown(session_id)` — runs `info shown`, returns JSON
- `get_model_info(model_id, session_id)` — runs `info`, finds model, calls `_get_chain_info_helper` per chain
- `get_chain_info(model_id, chain_id, session_id)` — calls `_get_chain_info_helper`
- `_get_chain_info_helper(model_id, chain_id, session_id) -> tuple[str, dict]` — private helper, queries chain attributes via `info chains` for chain_id, polymer_type, description, num_residues, num_existing_residues. Port from RBVI lines 1395-1493.
- `_get_chain_info_helper(model_id, chain_id, session_id)` — queries chain attributes via `info chains`

Port these exactly from the RBVI bridge (lines 1163-1515 of cached source). All `@mcp.tool()` decorators should be present.

- [ ] **Step 5: Add visualization tools (color_models, superpose_residue)**

Port from RBVI bridge (lines 1518-1625 of cached source):

- `color_models(color, target, session_id)` — runs `color {target} {color}`
- `superpose_residue(source_model, source_chain, source_residue, target_model, target_chain, target_residue, session_id)` — two-step: `view` + `move cofr`

- [ ] **Step 6: Add documentation tools (list_chimerax_commands, get_command_documentation)**

Port from RBVI bridge (lines 1853-1884):

- `list_chimerax_commands()` — calls `list_available_commands()` from docs module
- `get_command_documentation(command_name)` — calls `get_command_doc()` from docs module

- [ ] **Step 7: Add session management tools**

Port from RBVI bridge (lines 1747-1851):

- `list_chimerax_instances()` — calls `list_running_instances()`
- `start_new_chimerax_session(session_name, port)` — calls `start_chimerax(force_new=True)`
- `check_chimerax_status(session_id)` — calls `is_chimerax_running()`
- `set_default_session(session_id)` — mutates `_default_port` global

For `set_default_session`, import and modify the module-level variable:

```python
@mcp.tool()
async def set_default_session(session_id: int) -> str:
    """Set the default ChimeraX session for commands without explicit session_id

    Args:
        session_id: ChimeraX session port to use as default
    """
    import chimerax_mcp.chimera_rest as rest

    if not await is_chimerax_running(session_id):
        return f"No ChimeraX instance running on port {session_id}"

    old_default = rest._default_port
    rest._default_port = session_id

    session_name = "unknown session"
    if session_id in rest._instances:
        session_name = rest._instances[session_id].get("session_name", f"session_{session_id}")

    return f"Default session changed from port {old_default} to port {session_id} ({session_name})"
```

- [ ] **Step 8: Verify server starts**

```bash
python -c "from chimerax_mcp.server import mcp; print(f'Server created: {mcp.name}')"
```

Expected: `Server created: ChimeraX Bridge`

- [ ] **Step 9: Commit**

```bash
git add src/chimerax_mcp/server.py
git commit -m "feat: add server with 14 retained tools and enhanced run_command"
```

---

## Task 6: Re-enabled Tools

**Files:**
- Modify: `src/chimerax_mcp/server.py`

- [ ] **Step 1: Add `open_structure` tool**

Port from RBVI bridge (lines 1025-1063). Add `@mcp.tool()` decorator (was commented out in RBVI):

```python
@mcp.tool()
async def open_structure(identifier: str, format: str = "auto-detect", fetch_emdb_map: bool = False, session_id: Optional[int] = None) -> str:
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
```

- [ ] **Step 2: Add `save_image` tool**

Port from RBVI bridge (lines 1541-1559), add `transparent_background` param and auto-filename:

```python
@mcp.tool()
async def save_image(filename: str = "", width: int = 1920, height: int = 1080, supersample: int = 3, transparent_background: bool = False, session_id: Optional[int] = None) -> str:
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
```

- [ ] **Step 3: Add `show_hide_objects` tool**

Port from RBVI bridge (lines 1627-1743). Add `@mcp.tool()` decorator. This is the largest tool — it validates action/target, runs `select` first for feedback, then `show`/`hide`, and auto-shows parent model on `show`:

```python
@mcp.tool()
async def show_hide_objects(
    action: str,
    atomspec: str,
    target: str,
    session_id: Optional[int] = None
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
    counts_string = select_result.get("logs", {}).get("note", ["", ""])[1] if len(select_result.get("logs", {}).get("note", [])) > 1 else "unknown count"
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
```

- [ ] **Step 4: Verify all 17 tools are registered**

```bash
python -c "
from chimerax_mcp.server import mcp
tools = mcp.list_tools()
print(f'Registered tools: {len(tools) if hasattr(tools, \"__len__\") else \"check manually\"}')
"
```

- [ ] **Step 5: Commit**

```bash
git add src/chimerax_mcp/server.py
git commit -m "feat: re-enable open_structure, save_image, show_hide_objects tools"
```

---

## Task 7: New Analysis Tools

**Files:**
- Modify: `src/chimerax_mcp/server.py`
- Create: `tests/test_tools.py`

- [ ] **Step 1: Write tests for analysis tools**

```python
# tests/test_tools.py
import pytest
from unittest.mock import patch, AsyncMock


def make_result(logs=None, json_values=None, return_values=None):
    return {
        "logs": logs or {},
        "json_values": json_values or [],
        "return_values": return_values or [],
    }


class TestMeasureDistance:
    @pytest.mark.asyncio
    async def test_returns_formatted_distance(self):
        from chimerax_mcp.server import measure_distance
        mock_result = make_result(logs={"info": ["Distance between #1/A:100@CA and #1/A:200@CA = 12.34"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result):
            result = await measure_distance("#1/A:100@CA", "#1/A:200@CA")
            assert "12.34" in result
            assert "distance" in result.lower()


class TestFindHbonds:
    @pytest.mark.asyncio
    async def test_returns_hbond_info(self):
        from chimerax_mcp.server import find_hbonds
        mock_result = make_result(logs={"info": ["Found 42 hydrogen bonds"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result):
            result = await find_hbonds("#1")
            assert "42" in result


class TestFindClashes:
    @pytest.mark.asyncio
    async def test_returns_clash_info(self):
        from chimerax_mcp.server import find_clashes
        mock_result = make_result(logs={"info": ["12 clashes found"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result):
            result = await find_clashes("#1")
            assert "12" in result


class TestAlignStructures:
    @pytest.mark.asyncio
    async def test_returns_rmsd(self):
        from chimerax_mcp.server import align_structures
        mock_result = make_result(logs={"info": ["RMSD between 245 pruned atom pairs is 1.23 angstroms"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result):
            result = await align_structures("#2", "#1")
            assert "1.23" in result


class TestPredictStructure:
    @pytest.mark.asyncio
    async def test_validates_invalid_sequence(self):
        from chimerax_mcp.server import predict_structure
        with pytest.raises(ValueError, match="Invalid"):
            await predict_structure("NOTAVALIDSEQUENCE123!!!")

    @pytest.mark.asyncio
    async def test_validates_invalid_method(self):
        from chimerax_mcp.server import predict_structure
        with pytest.raises(ValueError, match="Method"):
            await predict_structure("MKTLLILAVL", method="deepfold")

    @pytest.mark.asyncio
    async def test_accepts_valid_sequence(self):
        from chimerax_mcp.server import predict_structure
        mock_result = make_result(logs={"info": ["AlphaFold prediction complete"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result):
            result = await predict_structure("MKTLLILAVL")
            assert "prediction" in result.lower() or "AlphaFold" in result


class TestSetScene:
    @pytest.mark.asyncio
    async def test_sets_background_only(self):
        from chimerax_mcp.server import set_scene
        calls = []
        async def mock_run(cmd, port=None):
            calls.append(cmd)
            return make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", side_effect=mock_run):
            await set_scene(background="white")
            assert any("bgColor" in c for c in calls)
            assert not any("lighting" in c for c in calls)

    @pytest.mark.asyncio
    async def test_sets_all_params(self):
        from chimerax_mcp.server import set_scene
        calls = []
        async def mock_run(cmd, port=None):
            calls.append(cmd)
            return make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", side_effect=mock_run):
            await set_scene(background="black", lighting="soft", silhouettes=True, camera="orthographic")
            assert len(calls) == 4


class TestCloseModels:
    @pytest.mark.asyncio
    async def test_close_all(self):
        from chimerax_mcp.server import close_models
        mock_result = make_result(logs={"info": ["All models closed"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result):
            result = await close_models("all")
            assert "close" in result.lower() or "closed" in result.lower() or "Command" in result


class TestGetSessionInfo:
    @pytest.mark.asyncio
    async def test_returns_combined_info(self):
        from chimerax_mcp.server import get_session_info
        info_result = make_result(json_values=[[{"spec": "1", "name": "test", "shown": True}]])
        shown_result = make_result(json_values=[[]])
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, side_effect=[info_result, shown_result]):
            with patch("chimerax_mcp.server.is_chimerax_running", new_callable=AsyncMock, return_value=True):
                result = await get_session_info()
                assert "test" in result or "model" in result.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_tools.py -v
```

Expected: ImportError or AttributeError — tools not defined yet.

- [ ] **Step 3: Implement `measure_distance`**

Add to `server.py`:

```python
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
```

- [ ] **Step 4: Implement `find_hbonds`**

```python
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
```

- [ ] **Step 5: Implement `find_clashes`**

```python
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
```

- [ ] **Step 6: Implement `align_structures`**

```python
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
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
pytest tests/test_tools.py::TestMeasureDistance tests/test_tools.py::TestFindHbonds tests/test_tools.py::TestFindClashes tests/test_tools.py::TestAlignStructures -v
```

Expected: All 4 tests PASS.

- [ ] **Step 8: Commit**

```bash
git add src/chimerax_mcp/server.py tests/test_tools.py
git commit -m "feat: add analysis tools (measure_distance, find_hbonds, find_clashes, align_structures)"
```

---

## Task 8: New Utility Tools

**Files:**
- Modify: `src/chimerax_mcp/server.py`

- [ ] **Step 1: Implement `predict_structure`**

```python
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

    # Use extended timeout for predictions
    import aiohttp
    from chimerax_mcp.chimera_rest import get_session, get_chimerax_url, find_best_chimerax_instance, _execute_command_request

    port = session_id if session_id is not None else await find_best_chimerax_instance()
    session = await get_session()
    url = f"{get_chimerax_url(port)}/run"

    # Override timeout for this request (5 minutes)
    original_timeout = session.timeout
    try:
        result = await _execute_command_request(session, url, command, timeout=aiohttp.ClientTimeout(total=300))
    except Exception:
        # Fallback to normal run_chimerax_command if custom timeout fails
        result = await run_chimerax_command(command, session_id)

    context = f"Structure prediction ({method}) for sequence ({len(seq_upper)} residues)"
    return format_chimerax_response(result, context)
```

Note: This requires adding an optional `timeout` parameter to `_execute_command_request` in `chimera_rest.py`:

```python
async def _execute_command_request(session, url: str, command: str, timeout=None) -> dict:
    params = {'command': command}
    kwargs = {}
    if timeout is not None:
        kwargs['timeout'] = timeout
    async with session.get(url, params=params, **kwargs) as response:
        # ... rest unchanged
```

- [ ] **Step 2: Implement `set_scene`**

```python
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
        result = await run_chimerax_command(cmd, session_id)
        results.append(cmd)

    return f"Scene updated:\n" + "\n".join(f"  - {cmd}" for cmd in results)
```

- [ ] **Step 3: Implement `close_models`**

```python
@mcp.tool()
async def close_models(target: str = "all", session_id: Optional[int] = None) -> str:
    """Close (remove) models from the ChimeraX session.

    Args:
        target: Atomspec of models to close (e.g., '#1', '#2,3', 'all')
        session_id: ChimeraX session port (defaults to primary session)
    """
    if target != "all":
        # Verify models exist first
        check_result = await run_chimerax_command("info", session_id)
        json_values = check_result.get("json_values", [])
        if json_values:
            model_data = json_values[0] if isinstance(json_values[0], list) else json.loads(json_values[0])
            if not model_data:
                return "No models are currently loaded."

    command = f"close {target}"
    result = await run_chimerax_command(command, session_id)
    context = f"Closed models: {target}"
    return format_chimerax_response(result, context)
```

- [ ] **Step 4: Implement `get_session_info`**

```python
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
        info_result = await run_chimerax_command("info", session_id)
        json_values = info_result.get("json_values", [])
        if json_values and json_values[0]:
            model_data = json_values[0] if isinstance(json_values[0], list) else json.loads(json_values[0])
            output.append(f"\nModels ({len(model_data)} loaded):")
            for model in model_data:
                lines = format_single_model_info(model)
                for line in lines:
                    output.append(f"  {line}")
        else:
            output.append("\nNo models loaded.")
    except Exception as e:
        output.append(f"\nCould not retrieve model info: {e}")

    # Visibility state
    try:
        shown_result = await run_chimerax_command("info shown", session_id)
        shown_json = shown_result.get("json_values", [])
        if shown_json and shown_json[0]:
            display_data = shown_json[0] if isinstance(shown_json[0], list) else json.loads(shown_json[0])
            if display_data:
                output.append(f"\nVisible objects: {len(display_data)} model(s) have visible elements")
            else:
                output.append("\nNo objects currently visible.")
        else:
            output.append("\nNo visibility data available.")
    except Exception as e:
        output.append(f"\nCould not retrieve visibility info: {e}")

    return "\n".join(output)
```

- [ ] **Step 5: Run all tool tests**

```bash
pytest tests/test_tools.py -v
```

Expected: All tests PASS.

- [ ] **Step 6: Run full test suite**

```bash
pytest -v
```

Expected: All tests PASS across all test files.

- [ ] **Step 7: Commit**

```bash
git add src/chimerax_mcp/server.py tests/test_tools.py
git commit -m "feat: add utility tools (predict_structure, set_scene, close_models, get_session_info)"
```

---

## Task 9: README & Integration Validation

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create README.md**

```markdown
# ChimeraX MCP Server

A standalone [MCP](https://modelcontextprotocol.io) server that connects Claude Code CLI to [UCSF ChimeraX](https://www.cgl.ucsf.edu/chimerax/) for molecular visualization and structural analysis.

Based on the [RBVI official ChimeraX MCP bridge](https://github.com/RBVI/ChimeraX/tree/develop/src/bundles/mcp_server).

## Prerequisites

- [UCSF ChimeraX](https://www.cgl.ucsf.edu/chimerax/download.html) installed
- Python 3.11+
- [Claude Code CLI](https://claude.ai/code)

## Installation

pip install chimerax-mcp

Or from source:

git clone <repo-url>
cd chimerax-mcp
pip install -e .

## Setup

Add the MCP server to Claude Code:

claude mcp add chimerax -- python -m chimerax_mcp

That's it. ChimeraX will auto-launch with REST enabled when you first use a tool.

## Available Tools (25)

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

### Prediction
- **predict_structure** - AlphaFold/ESMFold structure prediction

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
```

- [ ] **Step 2: Verify the server starts correctly**

```bash
python -c "
from chimerax_mcp.server import mcp, main
print('Server name:', mcp.name)
print('Import OK')
"
```

Expected: `Server name: ChimeraX Bridge` and `Import OK`

- [ ] **Step 3: Run full test suite**

```bash
pytest -v --tb=short
```

Expected: All tests PASS.

- [ ] **Step 4: Verify Claude Code integration command works**

```bash
python -m chimerax_mcp --help 2>&1 || echo "Server runs via mcp.run() - no --help flag expected"
```

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: add README with installation, setup, and usage instructions"
```

- [ ] **Step 6: Final commit with all files**

```bash
git status
git log --oneline
```

Verify 7 commits total:
1. Design spec
2. Project scaffolding
3. Formatting module
4. Docs module
5. REST client module
6. Server with retained tools
7. Re-enabled tools
8. Analysis tools
9. Utility tools
10. README
