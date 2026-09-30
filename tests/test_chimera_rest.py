import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from chimerax_mcp.chimera_rest import (
    cleanup,
    find_chimerax_executable,
    find_available_port,
    find_best_chimerax_instance,
    get_chimerax_url,
    is_chimerax_running,
    run_chimerax_command,
)


@pytest.fixture(autouse=True)
async def cleanup_rest_session():
    yield
    await cleanup()


class TestFindChimeraXExecutable:
    def test_returns_none_when_not_found(self):
        with patch("chimerax_mcp.chimera_rest.shutil.which", return_value=None):
            with patch("chimerax_mcp.chimera_rest._candidate_installation_directories", return_value=[]):
                with patch("chimerax_mcp.chimera_rest._find_chimerax_installation_directory", return_value=None):
                    assert find_chimerax_executable() is None

    def test_finds_executable_on_path(self):
        with patch("chimerax_mcp.chimera_rest.shutil.which", return_value="/usr/local/bin/ChimeraX"):
            assert find_chimerax_executable() == "/usr/local/bin/ChimeraX"

    def test_finds_macos_executable(self, tmp_path):
        exe = tmp_path / "Contents" / "MacOS" / "ChimeraX"
        exe.parent.mkdir(parents=True)
        exe.touch()
        with patch("chimerax_mcp.chimera_rest.shutil.which", return_value=None):
            with patch("chimerax_mcp.chimera_rest._candidate_installation_directories", return_value=[]):
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
        try:
            result = await is_chimerax_running(59999)
            assert result is False
        finally:
            await cleanup()


class TestRunChimeraXCommand:
    @pytest.mark.asyncio
    async def test_raises_on_connection_error_no_executable(self):
        with patch("chimerax_mcp.chimera_rest.find_chimerax_executable", return_value=None):
            with pytest.raises(Exception, match="Cannot connect"):
                await run_chimerax_command("open 1abc", port=59999)

    @pytest.mark.asyncio
    async def test_parses_successful_json_response(self):
        import chimerax_mcp.chimera_rest as rest_mod
        old_default = rest_mod._default_port

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

        try:
            with patch("chimerax_mcp.chimera_rest.get_session", return_value=mock_session):
                with patch("chimerax_mcp.chimera_rest.is_chimerax_running", return_value=True):
                    with patch("chimerax_mcp.chimera_rest.find_best_chimerax_instance", return_value=8080):
                        result = await run_chimerax_command("open 1abc")
                        assert result["logs"]["info"] == ["Opened 1abc"]
                        assert rest_mod._default_port == 8080
        finally:
            rest_mod._default_port = old_default

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


class TestFindBestChimeraXInstance:
    @pytest.mark.asyncio
    async def test_prefers_known_working_port(self):
        import chimerax_mcp.chimera_rest as rest_mod

        old_default = rest_mod._default_port
        old_instances = dict(rest_mod._instances)
        rest_mod._default_port = 8080
        rest_mod._instances.clear()
        rest_mod._instances[8082] = {"port": 8082, "session_name": "alt"}

        async def mock_running(port):
            return port == 8082

        try:
            with patch("chimerax_mcp.chimera_rest.is_chimerax_running", side_effect=mock_running):
                assert await find_best_chimerax_instance() == 8082
        finally:
            rest_mod._default_port = old_default
            rest_mod._instances.clear()
            rest_mod._instances.update(old_instances)


class TestParseInfoJson:
    def test_empty_json_values(self):
        from chimerax_mcp.chimera_rest import parse_info_json
        result = {"json_values": [], "return_values": [], "logs": {}}
        assert parse_info_json(result) == []

    def test_missing_json_values(self):
        from chimerax_mcp.chimera_rest import parse_info_json
        result = {"return_values": [], "logs": {}}
        assert parse_info_json(result) == []

    def test_parses_json_string(self):
        from chimerax_mcp.chimera_rest import parse_info_json
        import json
        data = [{"spec": "#1", "class": "AtomicStructure", "attribute": "name", "present": True, "value": "1abc"}]
        result = {"json_values": [json.dumps(data)], "return_values": [], "logs": {}}
        parsed = parse_info_json(result)
        assert len(parsed) == 1
        assert parsed[0]["spec"] == "#1"
        assert parsed[0]["value"] == "1abc"

    def test_already_parsed_list(self):
        from chimerax_mcp.chimera_rest import parse_info_json
        data = [{"spec": "#1", "value": "test"}]
        result = {"json_values": [data], "return_values": [], "logs": {}}
        parsed = parse_info_json(result)
        assert parsed == data

    def test_single_dict_wrapped(self):
        from chimerax_mcp.chimera_rest import parse_info_json
        data = {"spec": "#1", "value": "test"}
        result = {"json_values": [data], "return_values": [], "logs": {}}
        parsed = parse_info_json(result)
        assert parsed == [data]

    def test_none_in_json_values(self):
        from chimerax_mcp.chimera_rest import parse_info_json
        result = {"json_values": [None], "return_values": [], "logs": {}}
        assert parse_info_json(result) == []


# ---------------------------------------------------------------------------
# Transport behaviour: port selection, error reporting, launching
# ---------------------------------------------------------------------------

import asyncio
import json
import os
import subprocess

import aiohttp

import chimerax_mcp.chimera_rest as rest_mod


def _ok_response(payload=None):
    resp = AsyncMock()
    resp.status = 200
    resp.json = AsyncMock(return_value=payload or {
        "python values": [None],
        "json values": [None],
        "log messages": {"info": ["ok"]},
        "error": None,
    })
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _raising(exc):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(side_effect=exc)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _refused():
    return aiohttp.ClientConnectorError(MagicMock(), OSError(61, "Connection refused"))


def _session(*responses):
    session = MagicMock()
    session.get = MagicMock(side_effect=list(responses))
    return session


def _called_port(session, call_index=0):
    url = session.get.call_args_list[call_index][0][0]
    return int(url.split(":")[-1].split("/")[0])


@pytest.fixture
def rest_state():
    old_default = rest_mod._default_port
    old_instances = dict(rest_mod._instances)
    rest_mod._default_port = 8080
    rest_mod._instances.clear()
    yield rest_mod
    rest_mod._default_port = old_default
    rest_mod._instances.clear()
    rest_mod._instances.update(old_instances)


class TestPortSelection:
    @pytest.mark.asyncio
    async def test_default_port_used_without_probing(self, rest_state):
        session = _session(_ok_response())
        probe = AsyncMock(side_effect=AssertionError("must not probe on the happy path"))
        with patch("chimerax_mcp.chimera_rest.get_session", return_value=session), \
             patch("chimerax_mcp.chimera_rest._probe_running_ports", probe):
            result = await run_chimerax_command("version")
        assert result["logs"]["info"] == ["ok"]
        assert session.get.call_count == 1
        assert _called_port(session) == 8080

    @pytest.mark.asyncio
    async def test_explicit_port_does_not_change_default(self, rest_state):
        session = _session(_ok_response())
        with patch("chimerax_mcp.chimera_rest.get_session", return_value=session):
            await run_chimerax_command("version", port=8082)
        assert _called_port(session) == 8082
        assert rest_state._default_port == 8080
        assert 8082 in rest_state._instances

    @pytest.mark.asyncio
    async def test_falls_back_to_other_running_instance(self, rest_state):
        session = _session(_raising(_refused()), _ok_response())
        with patch("chimerax_mcp.chimera_rest.get_session", return_value=session), \
             patch("chimerax_mcp.chimera_rest._find_running_port", AsyncMock(return_value=8083)) as find, \
             patch("chimerax_mcp.chimera_rest.start_chimerax", AsyncMock(side_effect=AssertionError("no launch"))):
            await run_chimerax_command("version")
        find.assert_awaited_once_with(exclude=8080)
        assert _called_port(session, 1) == 8083
        assert rest_state._default_port == 8083

    @pytest.mark.asyncio
    async def test_auto_launches_when_nothing_running(self, rest_state):
        session = _session(_raising(_refused()), _ok_response())
        with patch("chimerax_mcp.chimera_rest.get_session", return_value=session), \
             patch("chimerax_mcp.chimera_rest._find_running_port", AsyncMock(return_value=None)), \
             patch("chimerax_mcp.chimera_rest.find_chimerax_executable", return_value="/x/ChimeraX"), \
             patch("chimerax_mcp.chimera_rest.start_chimerax", AsyncMock(return_value=(True, 8081))):
            await run_chimerax_command("version")
        assert _called_port(session, 1) == 8081
        assert rest_state._default_port == 8081


class TestErrorReporting:
    @pytest.mark.asyncio
    async def test_timeout_has_actionable_message(self, rest_state):
        session = _session(_raising(asyncio.TimeoutError()))
        with patch("chimerax_mcp.chimera_rest.get_session", return_value=session):
            with pytest.raises(Exception, match=r"did not respond within 5s") as info:
                await run_chimerax_command("minimize", port=8080, timeout=5)
        assert "CHIMERAX_TIMEOUT" in str(info.value)

    @pytest.mark.asyncio
    async def test_non_json_reply_explains_json_mode(self, rest_state):
        resp = _ok_response()
        resp.json = AsyncMock(side_effect=json.JSONDecodeError("x", "Opened 1abc", 0))
        session = _session(resp)
        with patch("chimerax_mcp.chimera_rest.get_session", return_value=session):
            with pytest.raises(Exception, match="json true"):
                await run_chimerax_command("open 1abc", port=8080)

    @pytest.mark.asyncio
    async def test_foreign_server_on_default_port_is_not_relaunched(self, rest_state):
        resp = _ok_response()
        resp.status = 404
        session = _session(resp)
        with patch("chimerax_mcp.chimera_rest.get_session", return_value=session), \
             patch("chimerax_mcp.chimera_rest._find_running_port", AsyncMock(return_value=None)), \
             patch("chimerax_mcp.chimera_rest.start_chimerax", AsyncMock(side_effect=AssertionError("no launch"))):
            with pytest.raises(Exception, match="HTTP 404"):
                await run_chimerax_command("version")


class TestLaunching:
    def test_daemon_is_detached_from_mcp_stdio(self):
        with patch("chimerax_mcp.chimera_rest.find_chimerax_executable", return_value="/x/ChimeraX"), \
             patch("chimerax_mcp.chimera_rest.subprocess.Popen") as popen, \
             patch("sys.platform", "linux"):
            assert rest_mod.start_chimerax_daemon(8085) is True
        args, kwargs = popen.call_args
        assert args[0] == ["/x/ChimeraX", "--cmd", "remotecontrol rest start port 8085 json true log true"]
        assert kwargs["stdout"] is subprocess.DEVNULL
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert kwargs["start_new_session"] is True

    def test_daemon_launch_failure_returns_false(self):
        with patch("chimerax_mcp.chimera_rest.find_chimerax_executable", return_value="/x/ChimeraX"), \
             patch("chimerax_mcp.chimera_rest.subprocess.Popen", side_effect=PermissionError("denied")):
            assert rest_mod.start_chimerax_daemon(8085) is False

    @pytest.mark.asyncio
    async def test_force_new_does_not_return_existing_instance(self, rest_state):
        async def running(port=None):
            return port in (8080, 8081) and (port == 8080 or daemon.called)

        daemon = MagicMock(return_value=True)
        with patch("chimerax_mcp.chimera_rest.is_chimerax_running", side_effect=running), \
             patch("chimerax_mcp.chimera_rest.find_chimerax_executable", return_value="/x/ChimeraX"), \
             patch("chimerax_mcp.chimera_rest.find_available_port", return_value=8081), \
             patch("chimerax_mcp.chimera_rest.start_chimerax_daemon", daemon):
            ok, port = await rest_mod.start_chimerax(force_new=True, session_name="second")
        assert (ok, port) == (True, 8081)
        daemon.assert_called_once_with(8081)
        assert rest_state._instances[8081]["session_name"] == "second"
