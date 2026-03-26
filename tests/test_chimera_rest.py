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
