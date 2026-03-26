"""REST communication layer for ChimeraX MCP server.

Handles auto-discovery of running ChimeraX instances, optional auto-launch
as a background daemon, and the core run_chimerax_command() function.
"""

import os
import sys
import asyncio
import socket
import time
import subprocess
from typing import Optional

import aiohttp

from chimerax_mcp.docs import _find_chimerax_installation_directory
from chimerax_mcp.formatting import add_error_hints


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

CHIMERAX_HOST = 'localhost'
DEFAULT_CHIMERAX_PORT = 8080
DEBUG = False

_instances: dict = {}          # port -> instance info
_default_port: int = DEFAULT_CHIMERAX_PORT
_session: Optional[aiohttp.ClientSession] = None


# ---------------------------------------------------------------------------
# 1. find_chimerax_executable
# ---------------------------------------------------------------------------

def find_chimerax_executable() -> Optional[str]:
    """Return the path to the ChimeraX executable, or None if not found."""
    install_dir = _find_chimerax_installation_directory()
    if install_dir is None:
        return None

    if sys.platform == 'darwin':
        exe = os.path.join(install_dir, 'Contents', 'MacOS', 'ChimeraX')
    elif sys.platform == 'win32':
        exe = os.path.join(install_dir, 'bin', 'ChimeraX.exe')
    else:
        exe = os.path.join(install_dir, 'bin', 'ChimeraX')

    if os.path.exists(exe):
        return exe
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
    if _session is None or _session.closed:
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
        async with aiohttp.ClientSession() as session:
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

    # Check known instances
    for port, info in list(_instances.items()):
        if await is_chimerax_running(port):
            running[port] = info

    # Scan common ports 8080-8089
    for port in range(8080, 8090):
        if port not in running and await is_chimerax_running(port):
            running[port] = {'port': port, 'auto_discovered': True}

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
            _instances[existing_port] = {'port': existing_port, 'auto_discovered': True}
            return True, existing_port

    # Already running on requested port?
    if await is_chimerax_running(port):
        _instances[port] = {'port': port}
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
    _instances[actual_port] = {
        'port': actual_port,
        'session_name': session_name,
        'started_at': time.time(),
    }

    # Wait up to 30 seconds
    start_time = time.time()
    last_progress = start_time
    while time.time() - start_time < 30:
        if await is_chimerax_running(actual_port):
            return True, actual_port
        now = time.time()
        if now - last_progress >= 5:
            elapsed = int(now - start_time)
            if DEBUG:
                print(f"Waiting for ChimeraX on port {actual_port}... ({elapsed}s)")
            last_progress = now
        await asyncio.sleep(0.5)

    return False, actual_port


# ---------------------------------------------------------------------------
# 9. check_existing_rest_server
# ---------------------------------------------------------------------------

async def check_existing_rest_server() -> tuple[bool, int]:
    """Scan for an already-running ChimeraX REST server on common ports."""
    common_ports = [DEFAULT_CHIMERAX_PORT, 8081, 8082, 8083, 7955, 9000]
    for port in common_ports:
        if await is_chimerax_running(port):
            return True, port
    return False, DEFAULT_CHIMERAX_PORT


# ---------------------------------------------------------------------------
# 10. find_best_chimerax_instance
# ---------------------------------------------------------------------------

async def find_best_chimerax_instance() -> int:
    """Return the port of the best available ChimeraX instance.

    Checks the default port first, then common alternatives.
    Does NOT mutate _default_port.
    """
    # Check default port first
    if await is_chimerax_running(_default_port):
        return _default_port

    # Check common alternatives
    common_ports = [8081, 8082, 8083, 7955, 9000]
    for port in common_ports:
        if await is_chimerax_running(port):
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

async def run_chimerax_command(command: str, port: Optional[int] = None) -> dict:
    """Run a ChimeraX command via REST, auto-launching if needed.

    Returns a dict with keys: return_values, json_values, logs.
    """
    if port is None:
        port = await find_best_chimerax_instance()

    url = f"{get_chimerax_url(port)}/run"
    session = await get_session()

    try:
        return await _execute_command_request(session, url, command)
    except aiohttp.ClientConnectorError:
        # ChimeraX is not running; try to start it
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
        url = f"{get_chimerax_url(actual_port)}/run"
        return await _execute_command_request(session, url, command)


# ---------------------------------------------------------------------------
# 13. cleanup
# ---------------------------------------------------------------------------

async def cleanup() -> None:
    """Close the shared aiohttp session."""
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
        _session = None
