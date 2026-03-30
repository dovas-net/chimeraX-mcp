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
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
            sock.bind(('localhost', port))
            sock.close()
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
    """Launch ChimeraX as a Unix double-fork daemon with REST enabled."""
    chimerax_path = find_chimerax_executable()
    if chimerax_path is None:
        return False

    cmd_args = [
        chimerax_path,
        "--cmd",
        f"remotecontrol rest start port {port} json true log true",
    ]

    try:
        # First fork
        pid = os.fork()
        if pid > 0:
            # Parent: wait for first child to exit
            os.waitpid(pid, 0)
            return True

        # First child
        os.setsid()

        # Second fork
        pid2 = os.fork()
        if pid2 > 0:
            os._exit(0)

        # Daemon (second child): redirect stdio to /dev/null
        devnull_fd = os.open(os.devnull, os.O_RDWR)
        os.dup2(devnull_fd, 0)
        os.dup2(devnull_fd, 1)
        os.dup2(devnull_fd, 2)
        os.close(devnull_fd)

        os.execv(chimerax_path, cmd_args)
        # execv replaces the process; this line is never reached
        os._exit(1)

    except Exception:
        return False


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
    global _default_port

    if port is None:
        port = _default_port

    # If not forcing a new instance and port is the default, check for existing
    if not force_new and port == _default_port:
        found, existing_port = await check_existing_rest_server()
        if found:
            _remember_instance(existing_port, auto_discovered=True)
            return True, existing_port

    # Already running on requested port?
    if await is_chimerax_running(port):
        _remember_instance(port)
        return True, port

    chimerax_path = find_chimerax_executable()
    if chimerax_path is None:
        return False, port

    # Choose an available port if the requested one is in use
    try:
        actual_port = find_available_port(port)
    except RuntimeError:
        actual_port = port

    if sys.platform == 'win32':
        # Windows: use subprocess with DETACHED_PROCESS
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        subprocess.Popen(
            [
                chimerax_path,
                "--cmd",
                f"remotecontrol rest start port {actual_port} json true log true",
            ],
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
    else:
        # Unix: double-fork daemon
        success = start_chimerax_daemon(actual_port)
        if not success:
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

async def check_existing_rest_server() -> tuple[bool, int]:
    """Scan for an already-running ChimeraX REST server on common ports."""
    common_ports = _unique_ports([
        _default_port,
        DEFAULT_CHIMERAX_PORT,
        *list(_instances.keys()),
        8081,
        8082,
        8083,
        7955,
        9000,
    ])
    statuses = await _probe_running_ports(common_ports)
    for port in common_ports:
        if statuses.get(port):
            return True, port
    return False, _default_port


# ---------------------------------------------------------------------------
# 10. find_best_chimerax_instance
# ---------------------------------------------------------------------------

async def find_best_chimerax_instance() -> int:
    """Return the port of the best available ChimeraX instance.

    Checks the default port first, then known and common alternatives.
    """
    candidate_ports = _unique_ports([
        _default_port,
        *list(_instances.keys()),
        DEFAULT_CHIMERAX_PORT,
        8081,
        8082,
        8083,
        7955,
        9000,
    ])
    statuses = await _probe_running_ports(candidate_ports)
    for port in candidate_ports:
        if statuses.get(port):
            return port

    # Fall back to default
    return _default_port


# ---------------------------------------------------------------------------
# 11. _execute_command_request
# ---------------------------------------------------------------------------

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
        data = await resp.json()

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
    """
    if port is None:
        port = await find_best_chimerax_instance()

    if timeout is None:
        timeout = DEFAULT_TIMEOUT

    url = f"{get_chimerax_url(port)}/run"
    session = await get_session()
    aio_timeout = aiohttp.ClientTimeout(total=timeout)

    logger.debug("Running command on port %d: %s (timeout=%ds)", port, command, timeout)

    try:
        result = await _execute_command_request(session, url, command, aio_timeout)
        _remember_instance(port, promote=True)
        logger.debug("Command completed: %s", command[:80])
        return result
    except aiohttp.ClientConnectorError:
        logger.info("Cannot connect to port %d, attempting auto-launch", port)
        chimerax_path = find_chimerax_executable()
        if chimerax_path is None:
            raise Exception(
                f"Cannot connect to ChimeraX on port {port} and no ChimeraX "
                "executable was found. Please start ChimeraX manually."
            )
        success, actual_port = await start_chimerax(port=port)
        if not success:
            raise Exception(
                f"Cannot connect to ChimeraX on port {port} and failed to start "
                "a new instance automatically."
            )
        logger.info("Auto-launched ChimeraX on port %d", actual_port)
        _remember_instance(actual_port, promote=True)
        url = f"{get_chimerax_url(actual_port)}/run"
        return await _execute_command_request(session, url, command, aio_timeout)


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
