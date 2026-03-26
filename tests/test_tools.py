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
