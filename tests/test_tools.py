import json

import pytest
from unittest.mock import patch, AsyncMock


def make_result(logs=None, json_values=None, return_values=None):
    return {
        "logs": logs or {},
        "json_values": json_values or [],
        "return_values": return_values or [],
    }


# ===================================================================
# Previously untested tools
# ===================================================================


class TestRunCommand:
    @pytest.mark.asyncio
    async def test_executes_arbitrary_command(self):
        from chimerax_mcp.server import run_command
        mock_result = make_result(logs={"info": ["Opened 1abc"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result):
            result = await run_command("open 1abc")
            assert "1abc" in result


class TestListModels:
    @pytest.mark.asyncio
    async def test_returns_model_list(self):
        from chimerax_mcp.server import list_models
        info_data = json.dumps([
            {"spec": "#1", "class": "AtomicStructure", "attribute": "name", "present": True, "value": "1abc"},
            {"spec": "#2", "class": "Volume", "attribute": "name", "present": True, "value": "emd_1234"},
        ])
        display_data = json.dumps([
            {"spec": "#1", "attribute": "display", "present": True, "value": True},
            {"spec": "#2", "attribute": "display", "present": True, "value": False},
        ])
        atoms_data = json.dumps([
            {"spec": "#1", "attribute": "num_atoms", "present": True, "value": 5000},
        ])
        results = [
            make_result(json_values=[info_data]),
            make_result(json_values=[display_data]),
            make_result(json_values=[atoms_data]),
        ]
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, side_effect=results):
            result = await list_models()
            assert "1abc" in result
            assert "emd_1234" in result
            assert "5000" in result

    @pytest.mark.asyncio
    async def test_no_models(self):
        from chimerax_mcp.server import list_models
        mock_result = make_result(json_values=[json.dumps([])])
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result):
            result = await list_models()
            assert "No models" in result


class TestGetModelInfo:
    @pytest.mark.asyncio
    async def test_returns_model_details(self):
        from chimerax_mcp.server import get_model_info
        info_data = json.dumps([{"spec": "#1", "class": "AtomicStructure", "value": "1abc"}])
        atoms_data = json.dumps([{"spec": "#1", "value": 5000}])
        residues_data = json.dumps([{"spec": "#1", "value": 300}])
        bonds_data = json.dumps([{"spec": "#1", "value": 5100}])
        display_data = json.dumps([{"spec": "#1", "value": True}])
        chain_data = json.dumps([{"value": "A", "polymer type": "protein", "sequence": "MVQD", "residues": ["/A:1","/A:2","/A:3","/A:4"]}])
        results = [
            make_result(json_values=[info_data]),
            make_result(json_values=[atoms_data]),
            make_result(json_values=[residues_data]),
            make_result(json_values=[bonds_data]),
            make_result(json_values=[display_data]),
            make_result(json_values=[chain_data]),
        ]
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, side_effect=results):
            result = await get_model_info("1")
            assert "1abc" in result
            assert "5000" in result
            assert "Chain A" in result


class TestGetChainInfo:
    @pytest.mark.asyncio
    async def test_returns_chain_details(self):
        from chimerax_mcp.server import get_chain_info
        chain_data = json.dumps([{"value": "A", "polymer type": "protein", "sequence": "MVQDTGK", "residues": ["/A:1","/A:2","/A:3","/A:4","/A:5","/A:6","/A:7"]}])
        mock_result = make_result(json_values=[chain_data])
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result):
            result = await get_chain_info("1", "A")
            assert "protein" in result
            assert "7" in result


class TestOpenStructure:
    @pytest.mark.asyncio
    async def test_opens_pdb(self):
        from chimerax_mcp.server import open_structure
        mock_result = make_result(logs={"info": ["Opened 1gcn"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            result = await open_structure("1gcn")
            mock.assert_called_once()
            assert "1gcn" in mock.call_args[0][0]
            assert "1gcn" in result

    @pytest.mark.asyncio
    async def test_opens_with_emdb(self):
        from chimerax_mcp.server import open_structure
        mock_result = make_result(logs={"info": ["Opened with map"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            result = await open_structure("7bv2", fetch_emdb_map=True)
            assert "fetchEmdbMap" in mock.call_args[0][0]
            assert "EMDB" in result


class TestSaveImage:
    @pytest.mark.asyncio
    async def test_auto_generates_filename(self):
        from chimerax_mcp.server import save_image
        mock_result = make_result(logs={"info": ["Image saved"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            result = await save_image()
            cmd = mock.call_args[0][0]
            assert "/tmp/chimerax_" in cmd
            assert ".png" in cmd

    @pytest.mark.asyncio
    async def test_custom_filename(self):
        from chimerax_mcp.server import save_image
        mock_result = make_result(logs={"info": ["Image saved"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            result = await save_image("output.png", width=800, height=600)
            cmd = mock.call_args[0][0]
            assert "output.png" in cmd
            assert "800" in cmd


class TestColorModels:
    @pytest.mark.asyncio
    async def test_colors_target(self):
        from chimerax_mcp.server import color_models
        mock_result = make_result(logs={"info": ["Colored 5000 atoms"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            result = await color_models("red", "#1/A")
            assert "color #1/A red" == mock.call_args[0][0]


class TestShowHideObjects:
    @pytest.mark.asyncio
    async def test_show_atoms(self):
        from chimerax_mcp.server import show_hide_objects
        select_result = make_result(logs={"note": ["Selected items:", "123 atoms, 120 bonds selected"]})
        show_result = make_result()
        model_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, side_effect=[select_result, show_result, model_result]):
            result = await show_hide_objects("show", "#1", "ab")
            assert "123 atoms" in result

    @pytest.mark.asyncio
    async def test_invalid_action(self):
        from chimerax_mcp.server import show_hide_objects
        with pytest.raises(ValueError, match="show.*hide"):
            await show_hide_objects("toggle", "#1", "a")

    @pytest.mark.asyncio
    async def test_nothing_selected(self):
        from chimerax_mcp.server import show_hide_objects
        select_result = make_result(logs={"note": ["Nothing selected"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=select_result):
            with pytest.raises(ValueError, match="No objects"):
                await show_hide_objects("show", "#99", "a")


class TestViewResidue:
    @pytest.mark.asyncio
    async def test_centers_on_residue(self):
        from chimerax_mcp.server import view_residue
        calls = []
        async def mock_run(cmd, port=None, timeout=None):
            calls.append(cmd)
            return make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", side_effect=mock_run):
            result = await view_residue("1", "A", "100")
            assert any("view #1/A:100" in c for c in calls)
            assert any("cofr #1/A:100" in c for c in calls)


class TestListChimeraXInstances:
    @pytest.mark.asyncio
    async def test_lists_instances(self):
        from chimerax_mcp.server import list_chimerax_instances
        instances = {8080: {"session_name": "main"}, 8081: {"session_name": "alt", "auto_discovered": True}}
        with patch("chimerax_mcp.server.list_running_instances", new_callable=AsyncMock, return_value=instances):
            result = await list_chimerax_instances()
            assert "8080" in result
            assert "main" in result

    @pytest.mark.asyncio
    async def test_no_instances(self):
        from chimerax_mcp.server import list_chimerax_instances
        with patch("chimerax_mcp.server.list_running_instances", new_callable=AsyncMock, return_value={}):
            result = await list_chimerax_instances()
            assert "No running" in result


class TestStartNewSession:
    @pytest.mark.asyncio
    async def test_starts_successfully(self):
        from chimerax_mcp.server import start_new_chimerax_session
        with patch("chimerax_mcp.server.find_chimerax_executable", return_value="/usr/bin/chimerax"):
            with patch("chimerax_mcp.server.start_chimerax", new_callable=AsyncMock, return_value=(True, 8081)):
                result = await start_new_chimerax_session("test_session", 8081)
                assert "8081" in result
                assert "successfully" in result

    @pytest.mark.asyncio
    async def test_no_executable(self):
        from chimerax_mcp.server import start_new_chimerax_session
        with patch("chimerax_mcp.server.find_chimerax_executable", return_value=None):
            result = await start_new_chimerax_session()
            assert "not found" in result


class TestCheckStatus:
    @pytest.mark.asyncio
    async def test_running(self):
        from chimerax_mcp.server import check_chimerax_status
        with patch("chimerax_mcp.server.is_chimerax_running", new_callable=AsyncMock, return_value=True):
            result = await check_chimerax_status(8080)
            assert "running" in result.lower()

    @pytest.mark.asyncio
    async def test_not_running(self):
        from chimerax_mcp.server import check_chimerax_status
        with patch("chimerax_mcp.server.is_chimerax_running", new_callable=AsyncMock, return_value=False):
            result = await check_chimerax_status(9999)
            assert "NOT running" in result


class TestSetDefaultSession:
    @pytest.mark.asyncio
    async def test_sets_default(self):
        from chimerax_mcp.server import set_default_session
        import chimerax_mcp.chimera_rest as rest_mod
        old_port = rest_mod._default_port
        with patch("chimerax_mcp.server.is_chimerax_running", new_callable=AsyncMock, return_value=True):
            result = await set_default_session(8081)
            assert "8081" in result
        rest_mod._default_port = old_port  # restore

    @pytest.mark.asyncio
    async def test_rejects_nonrunning(self):
        from chimerax_mcp.server import set_default_session
        with patch("chimerax_mcp.server.is_chimerax_running", new_callable=AsyncMock, return_value=False):
            result = await set_default_session(9999)
            assert "No ChimeraX" in result


class TestListCommands:
    @pytest.mark.asyncio
    async def test_lists_commands(self):
        from chimerax_mcp.server import list_chimerax_commands
        with patch("chimerax_mcp.server.list_available_commands", return_value=["open", "close", "color"]):
            result = await list_chimerax_commands()
            assert "open" in result
            assert "3" in result  # count

    @pytest.mark.asyncio
    async def test_no_docs(self):
        from chimerax_mcp.server import list_chimerax_commands
        with patch("chimerax_mcp.server.list_available_commands", return_value=[]):
            result = await list_chimerax_commands()
            assert "not found" in result.lower() or "Could not" in result


class TestGetCommandDocumentation:
    @pytest.mark.asyncio
    async def test_returns_doc(self):
        from chimerax_mcp.server import get_command_documentation
        with patch("chimerax_mcp.server.get_command_doc", return_value="# ChimeraX Command: open\n\nOpen files"):
            result = await get_command_documentation("open")
            assert "open" in result.lower()


# ===================================================================
# New tools (Phase 4)
# ===================================================================


class TestSelectAtoms:
    @pytest.mark.asyncio
    async def test_set_selection(self):
        from chimerax_mcp.server import select_atoms
        mock_result = make_result(logs={"note": ["123 atoms selected"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            result = await select_atoms("#1/A")
            assert "select #1/A" == mock.call_args[0][0]

    @pytest.mark.asyncio
    async def test_add_selection(self):
        from chimerax_mcp.server import select_atoms
        mock_result = make_result(logs={"note": ["Added to selection"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await select_atoms("#1/B", mode="add")
            assert "select add #1/B" == mock.call_args[0][0]

    @pytest.mark.asyncio
    async def test_clear_selection(self):
        from chimerax_mcp.server import select_atoms
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            result = await select_atoms("", mode="clear")
            assert "~select" == mock.call_args[0][0]
            assert "cleared" in result.lower()

    @pytest.mark.asyncio
    async def test_invalid_mode(self):
        from chimerax_mcp.server import select_atoms
        with pytest.raises(ValueError, match="Mode"):
            await select_atoms("#1", mode="toggle")


class TestSelectZone:
    @pytest.mark.asyncio
    async def test_selects_zone(self):
        from chimerax_mcp.server import select_zone
        mock_result = make_result(logs={"note": ["50 residues selected"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            result = await select_zone("#1:ATP", 5.0)
            assert "zone" in mock.call_args[0][0]
            assert "5.0" in mock.call_args[0][0]

    @pytest.mark.asyncio
    async def test_invalid_target_type(self):
        from chimerax_mcp.server import select_zone
        with pytest.raises(ValueError, match="target_type"):
            await select_zone("#1", 5.0, target_type="chains")


class TestLabelAtoms:
    @pytest.mark.asyncio
    async def test_adds_label(self):
        from chimerax_mcp.server import label_atoms
        mock_result = make_result(logs={"info": ["Labeled 1 residue"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            result = await label_atoms("#1/A:100", text="Active Site")
            cmd = mock.call_args[0][0]
            assert 'text "Active Site"' in cmd

    @pytest.mark.asyncio
    async def test_deletes_labels(self):
        from chimerax_mcp.server import label_atoms
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            result = await label_atoms("#1", delete=True)
            assert "label delete" in mock.call_args[0][0]
            assert "Removed" in result


class TestLabel2D:
    @pytest.mark.asyncio
    async def test_adds_2d_label(self):
        from chimerax_mcp.server import label_2d
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            result = await label_2d("My Title", x=0.5, y=0.9, size=32)
            cmd = mock.call_args[0][0]
            assert '2dlabels' in cmd
            assert '"My Title"' in cmd
            assert "32" in cmd


class TestSaveSession:
    @pytest.mark.asyncio
    async def test_saves_with_extension(self):
        from chimerax_mcp.server import save_session
        mock_result = make_result(logs={"info": ["Session saved"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            result = await save_session("my_session")
            assert "my_session.cxs" in mock.call_args[0][0]

    @pytest.mark.asyncio
    async def test_preserves_extension(self):
        from chimerax_mcp.server import save_session
        mock_result = make_result(logs={"info": ["Session saved"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await save_session("my_session.cxs")
            assert mock.call_args[0][0].count(".cxs") == 1


class TestOpenSession:
    @pytest.mark.asyncio
    async def test_opens_session(self):
        from chimerax_mcp.server import open_session
        mock_result = make_result(logs={"info": ["Session restored"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            result = await open_session("my_session.cxs")
            assert "open my_session.cxs" == mock.call_args[0][0]


class TestCreateSurface:
    @pytest.mark.asyncio
    async def test_creates_solid_surface(self):
        from chimerax_mcp.server import create_surface
        mock_result = make_result(logs={"info": ["Created surface"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            result = await create_surface("#1")
            assert mock.call_count == 1  # solid = no style command

    @pytest.mark.asyncio
    async def test_creates_mesh_surface(self):
        from chimerax_mcp.server import create_surface
        mock_result = make_result(logs={"info": ["Created surface"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await create_surface("#1", style="mesh")
            assert mock.call_count == 2  # surface + style

    @pytest.mark.asyncio
    async def test_invalid_style(self):
        from chimerax_mcp.server import create_surface
        with pytest.raises(ValueError, match="Style"):
            await create_surface("#1", style="wireframe")


class TestColorSurface:
    @pytest.mark.asyncio
    async def test_coulombic(self):
        from chimerax_mcp.server import color_surface
        mock_result = make_result(logs={"info": ["Colored by electrostatics"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            result = await color_surface("#1", method="coulombic")
            assert "coulombic #1" == mock.call_args[0][0]

    @pytest.mark.asyncio
    async def test_invalid_method(self):
        from chimerax_mcp.server import color_surface
        with pytest.raises(ValueError, match="Method"):
            await color_surface("#1", method="rainbow")


class TestSetTransparency:
    @pytest.mark.asyncio
    async def test_sets_transparency(self):
        from chimerax_mcp.server import set_transparency
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            result = await set_transparency("#1", 50, "s")
            assert "transparency #1 50 target s" == mock.call_args[0][0]

    @pytest.mark.asyncio
    async def test_rejects_invalid_percent(self):
        from chimerax_mcp.server import set_transparency
        with pytest.raises(ValueError, match="0-100"):
            await set_transparency("#1", 150)


class TestUndoRedo:
    @pytest.mark.asyncio
    async def test_undo(self):
        from chimerax_mcp.server import undo_redo
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            result = await undo_redo("undo")
            assert mock.call_args[0][0] == "undo"
            assert "Undo" in result

    @pytest.mark.asyncio
    async def test_redo_multiple(self):
        from chimerax_mcp.server import undo_redo
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            result = await undo_redo("redo", count=3)
            assert "redo 3" == mock.call_args[0][0]
            assert "3 steps" in result

    @pytest.mark.asyncio
    async def test_invalid_action(self):
        from chimerax_mcp.server import undo_redo
        with pytest.raises(ValueError, match="undo.*redo"):
            await undo_redo("reset")


# ===================================================================
# Infrastructure tests
# ===================================================================


class TestValidateAtomspec:
    def test_strips_whitespace(self):
        from chimerax_mcp.formatting import validate_atomspec
        assert validate_atomspec("  #1/A  ") == "#1/A"

    def test_rejects_empty(self):
        from chimerax_mcp.formatting import validate_atomspec
        with pytest.raises(ValueError, match="empty"):
            validate_atomspec("")

    def test_rejects_none(self):
        from chimerax_mcp.formatting import validate_atomspec
        with pytest.raises(ValueError, match="None"):
            validate_atomspec(None)

    def test_passes_valid(self):
        from chimerax_mcp.formatting import validate_atomspec
        assert validate_atomspec("#1/A:100@CA") == "#1/A:100@CA"


# ===================================================================
# Existing tool tests below
# ===================================================================


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
