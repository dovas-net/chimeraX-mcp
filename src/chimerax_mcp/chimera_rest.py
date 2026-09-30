"""REST communication layer for ChimeraX MCP server.

Handles auto-discovery of running ChimeraX instances, optional auto-launch
as a background daemon, and the core run_chimerax_command() function.
"""

import logging
import os
import sys
import asyncio
import socket
import time
import subprocess
import shutil
from typing import Optional

import aiohttp

from chimerax_mcp.docs import (
    _candidate_installation_directories,
    _find_chimerax_installation_directory,
)
from chimerax_mcp.formatting import add_error_hints

logger = logging.getLogger("chimerax_mcp.rest")


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

CHIMERAX_HOST = 'localhost'
DEFAULT_CHIMERAX_PORT = int(os.environ.get("CHIMERAX_PORT", "8080"))
DEFAULT_TIMEOUT = int(os.environ.get("CHIMERAX_TIMEOUT", "60"))
CHIMERAX_PATH_OVERRIDE = os.environ.get("CHIMERAX_PATH")
DEBUG = os.environ.get("CHIMERAX_DEBUG", "").lower() in ("1", "true", "yes")

if DEBUG:
    logging.basicConfig(level=logging.DEBUG)
    logger.setLevel(logging.DEBUG)

_instances: dict[int, dict] = {}          # port -> instance info
_default_port: int = DEFAULT_CHIMERAX_PORT
_session: Optional[aiohttp.ClientSession] = None


def _unique_ports(ports: list[int]) -> list[int]:
    """Return ports in their original order with duplicates removed."""
    return list(dict.fromkeys(ports))


def _remember_instance(port: int, *, promote: bool = False, **info) -> None:
    """Merge instance metadata and optionally promote the port as default."""
    global _default_port

    instance = _instances.get(port, {"port": port})
    for key, value in info.items():
        if value is not None:
            instance[key] = value
    _instances[port] = instance

    if promote:
        _default_port = port


async def _probe_running_ports(ports: list[int]) -> dict[int, bool]:
    """Probe candidate ports concurrently and return their reachability."""
    unique_ports = _unique_ports(ports)
    results = await asyncio.gather(
        *(is_chimerax_running(port) for port in unique_ports),
        return_exceptions=True,
    )

    statuses: dict[int, bool] = {}
    for port, result in zip(unique_ports, results):
        statuses[port] = bool(result) if not isinstance(result, Exception) else False
    return statuses


# ---------------------------------------------------------------------------
# 1. find_chimerax_executable
# ---------------------------------------------------------------------------

def find_chimerax_executable() -> Optional[str]:
    """Return the path to the ChimeraX executable, or None if not found."""
    if CHIMERAX_PATH_OVERRIDE:
        if os.path.exists(CHIMERAX_PATH_OVERRIDE):
            logger.debug("Using CHIMERAX_PATH override: %s", CHIMERAX_PATH_OVERRIDE)
            return CHIMERAX_PATH_OVERRIDE
        logger.warning("CHIMERAX_PATH=%s does not exist", CHIMERAX_PATH_OVERRIDE)

    for exe_name in ("ChimeraX", "chimerax", "ChimeraX.exe"):
        resolved = shutil.which(exe_name)
        if resolved:
            logger.debug("Found ChimeraX executable on PATH: %s", resolved)
            return resolved

    install_dir = _find_chimerax_installation_directory()
    install_dirs: list[str] = []
    if install_dir is not None:
        install_dirs.append(install_dir)
    install_dirs.extend(
        candidate for candidate in _candidate_installation_directories()
        if candidate not in install_dirs
    )

    for install_dir in install_dirs:
        if sys.platform == 'darwin':
            candidates = [os.path.join(install_dir, 'Contents', 'MacOS', 'ChimeraX')]
        elif sys.platform == 'win32':
            candidates = [
                os.path.join(install_dir, 'bin', 'ChimeraX.exe'),
                os.path.join(install_dir, 'ChimeraX.exe'),
            ]
        else:
            candidates = [
                os.path.join(install_dir, 'bin', 'ChimeraX'),
                os.path.join(install_dir, 'bin', 'chimerax'),
                os.path.join(install_dir, 'ChimeraX'),
            ]

        for exe in candidates:
            if os.path.exists(exe):
                logger.debug("Found ChimeraX executable: %s", exe)
                return exe

    logger.debug("No ChimeraX executable found via override, PATH, or common install locations")
    return None


# ---------------------------------------------------------------------------
# 2. find_available_port
# ---------------------------------------------------------------------------

def find_available_port(start_port: int = 8080) -> int:
    """Find the first available TCP port starting at start_port (up to +100)."""
    for port in range(start_port, start_port + 100):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
                sock.bind(('localhost', port))
            return port
        except OSError:
            continue
    raise RuntimeError(f"No available port found in range {start_port}-{start_port + 99}")


# ---------------------------------------------------------------------------
# 3. get_chimerax_url
# ---------------------------------------------------------------------------

def get_chimerax_url(port: Optional[int] = None) -> str:
    """Return the base URL for the ChimeraX REST server."""
    if port is None:
        port = _default_port
    return f"http://{CHIMERAX_HOST}:{port}"


# ---------------------------------------------------------------------------
# 4. get_session
# ---------------------------------------------------------------------------

async def get_session() -> aiohttp.ClientSession:
    """Return the shared aiohttp ClientSession, creating it if necessary."""
    global _session
    if _session is not None and not _session.closed:
        # Verify the session belongs to the current event loop
        try:
            current_loop = asyncio.get_running_loop()
            connector = _session.connector
            if connector is not None and hasattr(connector, '_loop') and connector._loop is not current_loop:
                # Stale session from a different event loop — discard without closing
                # (closing would fail on the wrong loop)
                _session = None
            else:
                return _session
        except RuntimeError:
            _session = None
    elif _session is not None and _session.closed:
        _session = None
    _session = aiohttp.ClientSession()
    return _session


# ---------------------------------------------------------------------------
# 5. is_chimerax_running
# ---------------------------------------------------------------------------

async def is_chimerax_running(port: Optional[int] = None) -> bool:
    """Return True if a ChimeraX REST server is reachable on the given port."""
    if port is None:
        port = _default_port
    url = f"http://{CHIMERAX_HOST}:{port}/cmdline.html"
    try:
        timeout = aiohttp.ClientTimeout(total=1)
        session = await get_session()
        async with session.get(url, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 6. list_running_instances
# ---------------------------------------------------------------------------

async def list_running_instances() -> dict:
    """Return a dict of all detected running ChimeraX REST instances."""
    running: dict = {}

    known_ports = list(_instances.keys())
    scanned_ports = list(range(8080, 8090))
    statuses = await _probe_running_ports(known_ports + scanned_ports)

    for port in known_ports:
        if statuses.get(port):
            running[port] = _instances[port]

    for port in scanned_ports:
        if port not in running and statuses.get(port):
            _remember_instance(port, auto_discovered=True)
            running[port] = _instances[port]

    return running


# ---------------------------------------------------------------------------
# 7. start_chimerax_daemon
# ---------------------------------------------------------------------------

def start_chimerax_daemon(port: int) -> bool:
    """Launch ChimeraX detached from this process with REST enabled.

    The child gets its own session/process group and /dev/null for stdio:
    our stdout is the MCP JSON-RPC channel, so ChimeraX must never inherit it.
    subprocess is used rather than a hand-rolled double fork because forking
    the running asyncio process is unsafe, and a failed exec in a forked child
    would otherwise return into a duplicate copy of this server.
    """
    chimerax_path = find_chimerax_executable()
    if chimerax_path is None:
        return False

    cmd_args = [
        chimerax_path,
        "--cmd",
        f"remotecontrol rest start port {port} json true log true",
    ]
    popen_kwargs: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform == 'win32':
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        popen_kwargs["creationflags"] = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    try:
        subprocess.Popen(cmd_args, **popen_kwargs)
    except OSError as exc:
        logger.error("Failed to launch ChimeraX (%s): %s", chimerax_path, exc)
        return False
    return True


# ---------------------------------------------------------------------------
# 8. start_chimerax
# ---------------------------------------------------------------------------

async def start_chimerax(
    port: Optional[int] = None,
    session_name: Optional[str] = None,
    force_new: bool = False,
) -> tuple[bool, int]:
    """Start a ChimeraX instance with REST enabled.

    Returns (success, actual_port).
    """
    if port is None:
        port = _default_port

    # Reuse an existing instance unless the caller explicitly wants a new one.
    # (With force_new, find_available_port below skips ports already bound by
    # a running ChimeraX, so a genuinely new instance is launched.)
    if not force_new:
        if port == _default_port:
            found, existing_port = await check_existing_rest_server()
            if found:
                _remember_instance(existing_port, auto_discovered=True)
                return True, existing_port

        if await is_chimerax_running(port):
            _remember_instance(port)
            return True, port

    if find_chimerax_executable() is None:
        return False, port

    # Choose an available port if the requested one is in use
    try:
        actual_port = find_available_port(port)
    except RuntimeError:
        actual_port = port

    if not start_chimerax_daemon(actual_port):
        return False, actual_port

    # Register in instances
    _remember_instance(
        actual_port,
        session_name=session_name,
        started_at=time.time(),
    )

    # Wait up to 30 seconds
    logger.info("Waiting for ChimeraX to start on port %d...", actual_port)
    start_time = time.time()
    last_progress = start_time
    while time.time() - start_time < 30:
        if await is_chimerax_running(actual_port):
            logger.info("ChimeraX ready on port %d (%.1fs)", actual_port, time.time() - start_time)
            return True, actual_port
        now = time.time()
        if now - last_progress >= 5:
            elapsed = int(now - start_time)
            logger.debug("Still waiting for ChimeraX on port %d... (%ds)", actual_port, elapsed)
            last_progress = now
        await asyncio.sleep(0.5)

    logger.error("ChimeraX failed to start on port %d within 30s", actual_port)
    return False, actual_port


# ---------------------------------------------------------------------------
# 9. check_existing_rest_server
# ---------------------------------------------------------------------------

_COMMON_PORTS = (8081, 8082, 8083, 7955, 9000)


def _candidate_ports() -> list[int]:
    """Ports worth probing, most preferred first: default, known, common."""
    return _unique_ports([
        _default_port,
        *list(_instances.keys()),
        DEFAULT_CHIMERAX_PORT,
        *_COMMON_PORTS,
    ])


async def _find_running_port(exclude: Optional[int] = None) -> Optional[int]:
    """Return the most preferred reachable ChimeraX port, or None."""
    candidates = [port for port in _candidate_ports() if port != exclude]
    statuses = await _probe_running_ports(candidates)
    for port in candidates:
        if statuses.get(port):
            return port
    return None


async def check_existing_rest_server() -> tuple[bool, int]:
    """Scan for an already-running ChimeraX REST server on common ports."""
    port = await _find_running_port()
    if port is None:
        return False, _default_port
    return True, port


# ---------------------------------------------------------------------------
# 10. find_best_chimerax_instance
# ---------------------------------------------------------------------------

async def find_best_chimerax_instance() -> int:
    """Return the port of the best available ChimeraX instance.

    Checks the default port first, then known and common alternatives.
    Falls back to the default port when nothing is reachable.
    """
    port = await _find_running_port()
    return _default_port if port is None else port


# ---------------------------------------------------------------------------
# 11. _execute_command_request
# ---------------------------------------------------------------------------

class _UnexpectedResponse(Exception):
    """The port answered, but not like a ChimeraX REST server in JSON mode."""


def _unexpected_response_message(port: int, detail: str) -> str:
    return (
        f"Port {port} answered, but not as a ChimeraX REST server in JSON mode "
        f"({detail}).\n"
        "→ If this is ChimeraX, restart its REST server in JSON mode by running in "
        f"ChimeraX: remotecontrol rest stop; remotecontrol rest start port {port} json true\n"
        "→ If another program owns this port, start ChimeraX on a different port "
        "(start_new_chimerax_session) or set CHIMERAX_PORT"
    )


async def _execute_command_request(
    session: aiohttp.ClientSession,
    url: str,
    command: str,
    timeout: Optional[aiohttp.ClientTimeout] = None,
) -> dict:
    """Send a command to ChimeraX via GET and return a parsed result dict."""
    kwargs = {}
    if timeout is not None:
        kwargs['timeout'] = timeout

    async with session.get(url, params={'command': command}, **kwargs) as resp:
        if resp.status != 200:
            raise _UnexpectedResponse(f"HTTP {resp.status}")
        try:
            # content_type=None: parse by content, not header, so a text/plain
            # reply (REST started without `json true`) is reported clearly below.
            data = await resp.json(content_type=None)
        except ValueError:
            data = None
    if not isinstance(data, dict):
        raise _UnexpectedResponse("response was not a JSON object")

    # Handle ChimeraX error response
    error = data.get('error')
    if error:
        error_type = error.get('type', 'Error') if isinstance(error, dict) else 'Error'
        error_msg = error.get('message', str(error)) if isinstance(error, dict) else str(error)
        hint_message = add_error_hints(error_type, error_msg, command)
        raise Exception(hint_message)

    return {
        'return_values': data.get('python values', []),
        'json_values': data.get('json values', []),
        'logs': data.get('log messages', {}),
    }


# ---------------------------------------------------------------------------
# 12. run_chimerax_command
# ---------------------------------------------------------------------------

async def run_chimerax_command(
    command: str,
    port: Optional[int] = None,
    timeout: Optional[int] = None,
) -> dict:
    """Run a ChimeraX command via REST, auto-launching if needed.

    Args:
        command: ChimeraX command string.
        port: REST server port (auto-discovers if None).
        timeout: Command timeout in seconds (uses DEFAULT_TIMEOUT if None).

    Returns a dict with keys: return_values, json_values, logs.

    When ``port`` is None the last known-good default port is tried directly;
    other ports are only probed if that fails. (ChimeraX's REST server handles
    one request at a time, so probing before every command would double the
    request count and queue probes behind in-flight commands.) An explicit
    ``port`` is used as-is and does not change the default.
    """
    explicit_port = port is not None
    if port is None:
        port = _default_port

    if timeout is None:
        timeout = DEFAULT_TIMEOUT

    session = await get_session()
    aio_timeout = aiohttp.ClientTimeout(total=timeout)

    async def run_on(target_port: int, promote: bool) -> dict:
        url = f"{get_chimerax_url(target_port)}/run"
        logger.debug(
            "Running command on port %d: %s (timeout=%ds)", target_port, command, timeout
        )
        try:
            result = await _execute_command_request(session, url, command, aio_timeout)
        except asyncio.TimeoutError:
            raise Exception(
                f"ChimeraX on port {target_port} did not respond within {timeout}s "
                f"to: {command[:200]}\n"
                "→ The command may still be running inside ChimeraX; check its log "
                "before retrying\n"
                "→ Raise CHIMERAX_TIMEOUT for long-running commands"
            ) from None
        _remember_instance(target_port, promote=promote)
        logger.debug("Command completed: %s", command[:80])
        return result

    try:
        return await run_on(port, promote=not explicit_port)
    except aiohttp.ClientConnectorError:
        failure: Optional[_UnexpectedResponse] = None
    except _UnexpectedResponse as exc:
        if explicit_port:
            raise Exception(_unexpected_response_message(port, str(exc))) from None
        failure = exc

    if not explicit_port:
        # The default port is gone (or isn't ChimeraX); look for another instance.
        alternative = await _find_running_port(exclude=port)
        if alternative is not None:
            logger.info("Port %d unavailable, using ChimeraX on port %d", port, alternative)
            try:
                return await run_on(alternative, promote=True)
            except _UnexpectedResponse as exc:
                raise Exception(_unexpected_response_message(alternative, str(exc))) from None

    if failure is not None:
        raise Exception(_unexpected_response_message(port, str(failure)))

    logger.info("Cannot connect to port %d, attempting auto-launch", port)
    if find_chimerax_executable() is None:
        raise Exception(
            f"Cannot connect to ChimeraX on port {port} and no ChimeraX "
            "executable was found. Please start ChimeraX manually, or set "
            "CHIMERAX_PATH to the ChimeraX executable."
        )
    success, actual_port = await start_chimerax(port=port)
    if not success:
        raise Exception(
            f"Cannot connect to ChimeraX on port {port} and failed to start "
            "a new instance automatically."
        )
    logger.info("Auto-launched ChimeraX on port %d", actual_port)
    try:
        return await run_on(actual_port, promote=not explicit_port)
    except _UnexpectedResponse as exc:
        raise Exception(_unexpected_response_message(actual_port, str(exc))) from None


# ---------------------------------------------------------------------------
# 13. parse_info_json
# ---------------------------------------------------------------------------

def parse_info_json(result: dict) -> list[dict]:
    """Extract and parse JSON data from a ChimeraX info command response.

    ChimeraX 1.11.1 returns json_values[0] as a JSON-encoded string.
    This handles both string and already-parsed formats for robustness.

    Returns a list of dicts (one per model/chain/attribute row).
    """
    import json as _json

    json_values = result.get("json_values", [])
    if not json_values:
        return []

    raw = json_values[0]
    if raw is None:
        return []

    # If it's a JSON string, parse it
    if isinstance(raw, str):
        try:
            parsed = _json.loads(raw)
        except _json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return parsed
        elif isinstance(parsed, dict):
            return [parsed]
        return []

    # Already parsed
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return [raw]

    return []


# ---------------------------------------------------------------------------
# 14. cleanup
# ---------------------------------------------------------------------------

async def cleanup() -> None:
    """Close the shared aiohttp session."""
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
        _session = None
