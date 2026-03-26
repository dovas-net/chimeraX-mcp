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
