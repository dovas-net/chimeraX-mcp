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


class TestMeasureAngle:
    @pytest.mark.asyncio
    async def test_returns_angle(self):
        from chimerax_mcp.server import measure_angle
        mock_result = make_result(logs={"info": ["Angle: 109.5 degrees"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result):
            result = await measure_angle("#1/A:100@CA", "#1/A:100@CB", "#1/A:100@CG")
            assert "109.5" in result


class TestMeasureTorsion:
    @pytest.mark.asyncio
    async def test_returns_torsion(self):
        from chimerax_mcp.server import measure_torsion
        mock_result = make_result(logs={"info": ["Torsion: -60.3 degrees"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result):
            result = await measure_torsion("#1/A:100@N", "#1/A:100@CA", "#1/A:100@CB", "#1/A:100@CG")
            assert "-60.3" in result


class TestMeasureSasa:
    @pytest.mark.asyncio
    async def test_returns_sasa(self):
        from chimerax_mcp.server import measure_sasa
        mock_result = make_result(logs={"info": ["SASA = 12345.6 A^2"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result):
            result = await measure_sasa("#1")
            assert "12345.6" in result


class TestMeasureCenter:
    @pytest.mark.asyncio
    async def test_returns_center(self):
        from chimerax_mcp.server import measure_center
        mock_result = make_result(logs={"info": ["Center of mass: 10.5, 20.3, 30.1"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result):
            result = await measure_center("#1/A")
            assert "10.5" in result


class TestMeasureBuriedArea:
    @pytest.mark.asyncio
    async def test_returns_buried_area(self):
        from chimerax_mcp.server import measure_buried_area
        mock_result = make_result(logs={"info": ["Buried area: 890.5 A^2"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result):
            result = await measure_buried_area("#1/A", "#1/B")
            assert "890.5" in result


class TestGetSequence:
    @pytest.mark.asyncio
    async def test_returns_fasta_sequence(self):
        from chimerax_mcp.server import get_sequence
        import json
        chain_data = json.dumps([{"spec": "/A", "attribute": "chain_id", "sequence": "MVQDTGK", "residues": ["/A:1","/A:2","/A:3","/A:4","/A:5","/A:6","/A:7"], "polymer type": "protein", "present": True, "value": "A"}])
        mock_result = make_result(json_values=[chain_data])
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result):
            result = await get_sequence("1", "A")
            assert "MVQDTGK" in result
            assert "protein" in result
            assert "7 residues" in result

    @pytest.mark.asyncio
    async def test_no_chain_data(self):
        from chimerax_mcp.server import get_sequence
        mock_result = make_result(json_values=[])
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result):
            result = await get_sequence("1", "Z")
            assert "No sequence" in result


class TestBlastSearch:
    @pytest.mark.asyncio
    async def test_runs_blast(self):
        from chimerax_mcp.server import blast_search
        mock_result = make_result(logs={"info": ["5 BLAST hits found"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result):
            result = await blast_search("#1/A")
            assert "5" in result


class TestSwapResidue:
    @pytest.mark.asyncio
    async def test_swaps(self):
        from chimerax_mcp.server import swap_residue
        mock_result = make_result(logs={"info": ["Swapped residue"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result):
            result = await swap_residue("#1/A:100", "ALA")
            assert "ALA" in result


class TestAddHydrogens:
    @pytest.mark.asyncio
    async def test_adds_h(self):
        from chimerax_mcp.server import add_hydrogens
        mock_result = make_result(logs={"info": ["Added 2500 hydrogens"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result):
            result = await add_hydrogens("#1")
            assert "2500" in result


class TestMinimizeStructure:
    @pytest.mark.asyncio
    async def test_minimizes(self):
        from chimerax_mcp.server import minimize_structure
        mock_result = make_result(logs={"info": ["Minimization complete"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result):
            result = await minimize_structure("#1", steps=200)
            assert "200 steps" in result


class TestFitInMap:
    @pytest.mark.asyncio
    async def test_fits(self):
        from chimerax_mcp.server import fit_in_map
        mock_result = make_result(logs={"info": ["Correlation = 0.85"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result):
            result = await fit_in_map("#1", "#2")
            assert "0.85" in result


class TestMeasureSurfaceArea:
    @pytest.mark.asyncio
    async def test_measures_area(self):
        from chimerax_mcp.server import measure_surface_area
        mock_result = make_result(logs={"info": ["Area = 45678.9 A^2"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result):
            result = await measure_surface_area("#1")
            assert "45678.9" in result


class TestMeasureMapStats:
    @pytest.mark.asyncio
    async def test_returns_stats(self):
        from chimerax_mcp.server import measure_map_stats
        mock_result = make_result(logs={"info": ["Mean = 0.0, RMS = 1.5, Min = -3.0, Max = 12.0"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result):
            result = await measure_map_stats("#2")
            assert "1.5" in result
