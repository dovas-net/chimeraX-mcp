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

    @pytest.mark.asyncio
    async def test_quotes_local_paths_with_spaces(self):
        from chimerax_mcp.server import open_structure
        mock_result = make_result(logs={"info": ["Opened file"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await open_structure("~/My Structures/test file.pdb")
            assert 'open "~/My Structures/test file.pdb"' == mock.call_args[0][0]


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
        deselect_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, side_effect=[select_result, show_result, model_result, deselect_result]) as mock:
            result = await show_hide_objects("show", "#1", "ab")
            assert "123 atoms" in result
            # The feedback selection must be cleared so renders don't show green highlights
            assert mock.call_args_list[-1][0][0] == "~select"

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

    @pytest.mark.asyncio
    async def test_escapes_quotes_in_label_text(self):
        from chimerax_mcp.server import label_atoms
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await label_atoms("#1/A:100", text='Active "Site"')
            assert 'text "Active \\"Site\\""' in mock.call_args[0][0]


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
            assert 'open "my_session.cxs"' == mock.call_args[0][0]


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
# Tier 1 — High Impact tools
# ===================================================================


class TestSetStyle:
    @pytest.mark.asyncio
    async def test_sets_stick_style(self):
        from chimerax_mcp.server import set_style
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await set_style("#1", "sphere")
            assert "style #1 sphere" == mock.call_args[0][0]

    @pytest.mark.asyncio
    async def test_invalid_style(self):
        from chimerax_mcp.server import set_style
        with pytest.raises(ValueError, match="stick.*ball.*sphere"):
            await set_style("#1", "wireframe")


class TestSetCartoon:
    @pytest.mark.asyncio
    async def test_default_cartoon(self):
        from chimerax_mcp.server import set_cartoon
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await set_cartoon("#1")
            cmd = mock.call_args[0][0]
            assert "cartoon #1" in cmd
            assert "suppressBackboneDisplay true" in cmd

    @pytest.mark.asyncio
    async def test_styled_cartoon(self):
        from chimerax_mcp.server import set_cartoon
        mock_result = make_result()
        calls = []
        async def mock_run(cmd, port=None, timeout=None):
            calls.append(cmd)
            return mock_result
        with patch("chimerax_mcp.server.run_chimerax_command", side_effect=mock_run):
            await set_cartoon("#1", xsection="barbell")
            assert any("cartoon style #1 xsection barbell" in c for c in calls)


class TestSetClipping:
    @pytest.mark.asyncio
    async def test_near_clip(self):
        from chimerax_mcp.server import set_clipping
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await set_clipping("near", 5.0)
            assert "clip near 5.0" == mock.call_args[0][0]

    @pytest.mark.asyncio
    async def test_disable_clip(self):
        from chimerax_mcp.server import set_clipping
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await set_clipping("near", enable=False)
            assert "clip off near" == mock.call_args[0][0]


class TestCalculateRmsd:
    @pytest.mark.asyncio
    async def test_computes_rmsd(self):
        from chimerax_mcp.server import calculate_rmsd
        mock_result = make_result(logs={"info": ["RMSD = 1.234 for 100 atom pairs"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result):
            result = await calculate_rmsd("#1/A", "#2/A")
            assert "1.234" in result


class TestSetVolumeDisplay:
    @pytest.mark.asyncio
    async def test_sets_contour_level(self):
        from chimerax_mcp.server import set_volume_display
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await set_volume_display("#2", level=3.5, style="mesh")
            cmd = mock.call_args[0][0]
            assert "volume #2" in cmd
            assert "level 3.5" in cmd
            assert "style mesh" in cmd


class TestAtomsToMap:
    @pytest.mark.asyncio
    async def test_generates_map(self):
        from chimerax_mcp.server import atoms_to_map
        mock_result = make_result(logs={"info": ["Created volume model"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            result = await atoms_to_map("#1", resolution=8.0)
            assert "molmap #1 8.0" == mock.call_args[0][0]


class TestShowContacts:
    @pytest.mark.asyncio
    async def test_finds_interfaces(self):
        from chimerax_mcp.server import show_contacts
        mock_result = make_result(logs={"info": ["Found 5 interfaces"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await show_contacts("#1")
            assert "interfaces #1" in mock.call_args[0][0]


class TestShowNucleotides:
    @pytest.mark.asyncio
    async def test_ladder_display(self):
        from chimerax_mcp.server import show_nucleotides
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await show_nucleotides("#1", "slab")
            assert "nucleotides #1 slab" == mock.call_args[0][0]

    @pytest.mark.asyncio
    async def test_invalid_style(self):
        from chimerax_mcp.server import show_nucleotides
        with pytest.raises(ValueError):
            await show_nucleotides("#1", "rainbow")


# ===================================================================
# Tier 2 — Publication & Animation tools
# ===================================================================


class TestRotateView:
    @pytest.mark.asyncio
    async def test_turn(self):
        from chimerax_mcp.server import rotate_view
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await rotate_view("y", 180)
            assert "turn y 180" in mock.call_args[0][0]

    @pytest.mark.asyncio
    async def test_rock(self):
        from chimerax_mcp.server import rotate_view
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await rotate_view("x", 30, rock=True)
            assert "rock x 30" in mock.call_args[0][0]


class TestZoomView:
    @pytest.mark.asyncio
    async def test_zoom_factor(self):
        from chimerax_mcp.server import zoom_view
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await zoom_view(2.0)
            assert "zoom 2.0" == mock.call_args[0][0]

    @pytest.mark.asyncio
    async def test_zoom_pixel_size(self):
        from chimerax_mcp.server import zoom_view
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await zoom_view(pixel_size=0.5)
            assert "zoom pixelSize 0.5" == mock.call_args[0][0]


class TestRecordMovie:
    @pytest.mark.asyncio
    async def test_record_start(self):
        from chimerax_mcp.server import record_movie
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await record_movie("record")
            assert "movie record" == mock.call_args[0][0]

    @pytest.mark.asyncio
    async def test_encode(self):
        from chimerax_mcp.server import record_movie
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await record_movie("encode", "out.mp4")
            cmd = mock.call_args[0][0]
            assert 'movie encode "out.mp4"' in cmd

    @pytest.mark.asyncio
    async def test_invalid_action(self):
        from chimerax_mcp.server import record_movie
        with pytest.raises(ValueError):
            await record_movie("pause")


class TestManageScenes:
    @pytest.mark.asyncio
    async def test_save_scene(self):
        from chimerax_mcp.server import manage_scenes
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await manage_scenes("save", "overview")
            assert 'scenes save "overview"' == mock.call_args[0][0]

    @pytest.mark.asyncio
    async def test_list_scenes(self):
        from chimerax_mcp.server import manage_scenes
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await manage_scenes("list")
            assert "scenes list" == mock.call_args[0][0]

    @pytest.mark.asyncio
    async def test_requires_name(self):
        from chimerax_mcp.server import manage_scenes
        with pytest.raises(ValueError, match="name required"):
            await manage_scenes("save")


class TestApplyPreset:
    @pytest.mark.asyncio
    async def test_applies_preset(self):
        from chimerax_mcp.server import apply_preset
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await apply_preset("publication")
            assert '"publication"' in mock.call_args[0][0]


class TestAddScalebar:
    @pytest.mark.asyncio
    async def test_adds_scalebar(self):
        from chimerax_mcp.server import add_scalebar
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await add_scalebar(length=10.0)
            cmd = mock.call_args[0][0]
            assert "scalebar" in cmd
            assert "length 10.0" in cmd

    @pytest.mark.asyncio
    async def test_removes_scalebar(self):
        from chimerax_mcp.server import add_scalebar
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await add_scalebar(show=False)
            assert "scalebar delete" == mock.call_args[0][0]


class TestAddMarker:
    @pytest.mark.asyncio
    async def test_places_marker(self):
        from chimerax_mcp.server import add_marker
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await add_marker(10.0, 20.0, 30.0, "red", 2.0)
            cmd = mock.call_args[0][0]
            assert "marker #200" in cmd
            assert "10.0,20.0,30.0" in cmd
            assert "color red" in cmd


class TestAddShape:
    @pytest.mark.asyncio
    async def test_adds_sphere(self):
        from chimerax_mcp.server import add_shape
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await add_shape("sphere", "1,2,3", 5.0, "blue")
            cmd = mock.call_args[0][0]
            assert "shape sphere" in cmd

    @pytest.mark.asyncio
    async def test_invalid_shape(self):
        from chimerax_mcp.server import add_shape
        with pytest.raises(ValueError):
            await add_shape("cube")


# ===================================================================
# Tier 3 — Specialized Workflow tools
# ===================================================================


class TestPrepForDocking:
    @pytest.mark.asyncio
    async def test_preps(self):
        from chimerax_mcp.server import prep_for_docking
        mock_result = make_result(logs={"info": ["Dock prep done"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await prep_for_docking("#1")
            assert "dockprep #1" == mock.call_args[0][0]


class TestAssignSecondaryStructure:
    @pytest.mark.asyncio
    async def test_assigns(self):
        from chimerax_mcp.server import assign_secondary_structure
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await assign_secondary_structure("#1")
            assert "dssp #1" == mock.call_args[0][0]


class TestFindCavities:
    @pytest.mark.asyncio
    async def test_finds(self):
        from chimerax_mcp.server import find_cavities
        mock_result = make_result(logs={"info": ["Found 3 cavities"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await find_cavities("#1")
            assert "kvfinder #1" == mock.call_args[0][0]


class TestMorphStructures:
    @pytest.mark.asyncio
    async def test_morphs(self):
        from chimerax_mcp.server import morph_structures
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await morph_structures("#1-3", frames=30)
            assert "morph #1-3 frames 30" == mock.call_args[0][0]


class TestSplitModel:
    @pytest.mark.asyncio
    async def test_splits_by_chain(self):
        from chimerax_mcp.server import split_model
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await split_model("#1")
            assert "split #1" == mock.call_args[0][0]


class TestCombineModels:
    @pytest.mark.asyncio
    async def test_combines(self):
        from chimerax_mcp.server import combine_models
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await combine_models("#1,2", name="merged", close_originals=True)
            cmd = mock.call_args[0][0]
            assert "combine #1,2" in cmd
            assert 'name "merged"' in cmd
            assert "close true" in cmd


class TestSetAttribute:
    @pytest.mark.asyncio
    async def test_sets_attr(self):
        from chimerax_mcp.server import set_attribute
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await set_attribute("#1/A:100-200", "score", "0.95", "residues")
            cmd = mock.call_args[0][0]
            assert "setattr #1/A:100-200 residues score 0.95 create true" == cmd


class TestShowCrosslinks:
    @pytest.mark.asyncio
    async def test_loads(self):
        from chimerax_mcp.server import show_crosslinks
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await show_crosslinks("xl_data.csv")
            assert 'crosslinks "xl_data.csv"' in mock.call_args[0][0]


class TestShowCrystalContacts:
    @pytest.mark.asyncio
    async def test_shows(self):
        from chimerax_mcp.server import show_crystal_contacts
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await show_crystal_contacts("#1", distance=4.0)
            assert "crystalcontacts #1 distance 4.0" == mock.call_args[0][0]


class TestBuildStructure:
    @pytest.mark.asyncio
    async def test_builds_peptide(self):
        from chimerax_mcp.server import build_structure
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await build_structure("peptide", "ACGT")
            assert "build start peptide ACGT" == mock.call_args[0][0]

    @pytest.mark.asyncio
    async def test_invalid_type(self):
        from chimerax_mcp.server import build_structure
        with pytest.raises(ValueError):
            await build_structure("protein", "ACGT")


class TestShowSymmetry:
    @pytest.mark.asyncio
    async def test_assembly(self):
        from chimerax_mcp.server import show_symmetry
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await show_symmetry("#1", "assembly", "1")
            assert "sym #1 assembly 1" == mock.call_args[0][0]


class TestAddCharges:
    @pytest.mark.asyncio
    async def test_adds(self):
        from chimerax_mcp.server import add_charges
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await add_charges("#1")
            assert "addcharge #1 method am1-bcc" == mock.call_args[0][0]


class TestRenameModel:
    @pytest.mark.asyncio
    async def test_renames(self):
        from chimerax_mcp.server import rename_model
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await rename_model("#1", "My Protein")
            assert 'rename #1 "My Protein"' == mock.call_args[0][0]


class TestChangeChainIds:
    @pytest.mark.asyncio
    async def test_changes(self):
        from chimerax_mcp.server import change_chain_ids
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await change_chain_ids("#1/A", "B")
            assert "changechains #1/A B" == mock.call_args[0][0]


class TestRenumberResidues:
    @pytest.mark.asyncio
    async def test_renumbers(self):
        from chimerax_mcp.server import renumber_residues
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await renumber_residues("#1/A", start=100)
            assert "renumber #1/A start 100" == mock.call_args[0][0]


class TestDeleteAtoms:
    @pytest.mark.asyncio
    async def test_deletes(self):
        from chimerax_mcp.server import delete_atoms
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await delete_atoms("solvent")
            assert "delete solvent" == mock.call_args[0][0]


class TestManageBonds:
    @pytest.mark.asyncio
    async def test_add_bond(self):
        from chimerax_mcp.server import manage_bonds
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await manage_bonds("add", "#1/A:100@CA #1/A:200@CA")
            assert "bond" in mock.call_args[0][0]

    @pytest.mark.asyncio
    async def test_invalid_action(self):
        from chimerax_mcp.server import manage_bonds
        with pytest.raises(ValueError):
            await manage_bonds("toggle", "#1")


class TestDefineAxisPlane:
    @pytest.mark.asyncio
    async def test_defines_axis(self):
        from chimerax_mcp.server import define_axis_plane
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await define_axis_plane("plane", "#1/A")
            assert "define plane #1/A" == mock.call_args[0][0]


class TestSetLighting:
    @pytest.mark.asyncio
    async def test_sets_soft(self):
        from chimerax_mcp.server import set_lighting
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await set_lighting("soft", shadows=True)
            cmd = mock.call_args[0][0]
            assert "lighting soft" in cmd
            assert "shadows true" in cmd


class TestSetCamera:
    @pytest.mark.asyncio
    async def test_ortho(self):
        from chimerax_mcp.server import set_camera
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await set_camera("ortho")
            assert "camera ortho" == mock.call_args[0][0]


class TestSetWindowSize:
    @pytest.mark.asyncio
    async def test_resizes(self):
        from chimerax_mcp.server import set_window_size
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await set_window_size(1920, 1080)
            assert "windowsize 1920 1080" == mock.call_args[0][0]


class TestTileModels:
    @pytest.mark.asyncio
    async def test_tiles(self):
        from chimerax_mcp.server import tile_models
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await tile_models("#1-4", columns=2)
            cmd = mock.call_args[0][0]
            assert "tile #1-4" in cmd
            assert "columns 2" in cmd


class TestCopyModel:
    @pytest.mark.asyncio
    async def test_copies(self):
        from chimerax_mcp.server import copy_model
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await copy_model("#1")
            assert "combine #1" == mock.call_args[0][0]


class TestSetSize:
    @pytest.mark.asyncio
    async def test_sets_radius(self):
        from chimerax_mcp.server import set_size
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await set_size("#1", atom_radius=2.0)
            cmd = mock.call_args[0][0]
            assert "size #1" in cmd
            assert "atomRadius 2.0" in cmd


class TestMoveModel:
    @pytest.mark.asyncio
    async def test_moves(self):
        from chimerax_mcp.server import move_model
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await move_model("z", 15.0, models="#1")
            cmd = mock.call_args[0][0]
            assert "move z 15.0" in cmd
            assert "models #1" in cmd


class TestColorKey:
    @pytest.mark.asyncio
    async def test_adds_key(self):
        from chimerax_mcp.server import color_key
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await color_key("red-white-blue")
            assert "key red-white-blue" in mock.call_args[0][0]

    @pytest.mark.asyncio
    async def test_removes_key(self):
        from chimerax_mcp.server import color_key
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await color_key(show=False)
            assert "key delete" == mock.call_args[0][0]


class TestFoldseekSearch:
    @pytest.mark.asyncio
    async def test_searches(self):
        from chimerax_mcp.server import foldseek_search
        mock_result = make_result(logs={"info": ["Found 10 hits"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await foldseek_search("#1", "afdb50")
            cmd = mock.call_args[0][0]
            assert "foldseek #1" in cmd
            assert "database afdb50" in cmd


class TestAltlocs:
    @pytest.mark.asyncio
    async def test_list_altlocs(self):
        from chimerax_mcp.server import altlocs
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await altlocs("#1/A:100")
            assert "altlocs list #1/A:100" == mock.call_args[0][0]

    @pytest.mark.asyncio
    async def test_change_altloc(self):
        from chimerax_mcp.server import altlocs
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await altlocs("#1/A:100", "B")
            assert "altlocs change #1/A:100 B" == mock.call_args[0][0]


class TestCoordset:
    @pytest.mark.asyncio
    async def test_goto_frame(self):
        from chimerax_mcp.server import coordset
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await coordset("#1", frame=5)
            assert "coordset #1 5" == mock.call_args[0][0]

    @pytest.mark.asyncio
    async def test_play_all(self):
        from chimerax_mcp.server import coordset
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await coordset("#1", play=True)
            assert "coordset #1" == mock.call_args[0][0]


class TestSwapNucleicAcid:
    @pytest.mark.asyncio
    async def test_swaps(self):
        from chimerax_mcp.server import swap_nucleic_acid
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await swap_nucleic_acid("#1/A:10", "G")
            assert "swapna #1/A:10 G" == mock.call_args[0][0]


class TestSetMaterial:
    @pytest.mark.asyncio
    async def test_sets_material(self):
        from chimerax_mcp.server import set_material
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await set_material(reflectivity=0.8, specular_exponent=30)
            cmd = mock.call_args[0][0]
            assert "reflectivity 0.8" in cmd
            assert "specularExponent 30" in cmd

    @pytest.mark.asyncio
    async def test_no_params(self):
        from chimerax_mcp.server import set_material
        result = await set_material()
        assert "No material" in result


class TestNameSelection:
    @pytest.mark.asyncio
    async def test_names_atomspec(self):
        from chimerax_mcp.server import name_selection
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await name_selection("active_site", "#1/A:100-120")
            assert "name active_site #1/A:100-120" == mock.call_args[0][0]

    @pytest.mark.asyncio
    async def test_names_current_selection(self):
        from chimerax_mcp.server import name_selection
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await name_selection("my_sel")
            assert "name my_sel sel" == mock.call_args[0][0]


class TestSimilarStructures:
    @pytest.mark.asyncio
    async def test_searches(self):
        from chimerax_mcp.server import similar_structures
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await similar_structures("#1/A")
            assert "similarstructures #1/A" == mock.call_args[0][0]


class TestStruts:
    @pytest.mark.asyncio
    async def test_adds_struts(self):
        from chimerax_mcp.server import struts
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await struts("#1", length=5.0)
            assert "struts #1 length 5.0" == mock.call_args[0][0]

    @pytest.mark.asyncio
    async def test_removes_struts(self):
        from chimerax_mcp.server import struts
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await struts("#1", show=False)
            assert "~struts #1" == mock.call_args[0][0]


# ===================================================================
# Remaining commands — full coverage
# ===================================================================


class TestCreateAlias:
    @pytest.mark.asyncio
    async def test_creates(self):
        from chimerax_mcp.server import create_alias
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await create_alias("showsite", "select #1/A:100-120; show sel target ab")
            assert "alias showsite" in mock.call_args[0][0]

    @pytest.mark.asyncio
    async def test_deletes(self):
        from chimerax_mcp.server import create_alias
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await create_alias("showsite", delete=True)
            assert "alias delete showsite" == mock.call_args[0][0]


class TestShowAniso:
    @pytest.mark.asyncio
    async def test_shows(self):
        from chimerax_mcp.server import show_aniso
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await show_aniso("#1", scale=1.5)
            assert "aniso #1 scale 1.5" == mock.call_args[0][0]

    @pytest.mark.asyncio
    async def test_hides(self):
        from chimerax_mcp.server import show_aniso
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await show_aniso("#1", show=False)
            assert "~aniso #1" == mock.call_args[0][0]


class TestPredictBoltz:
    @pytest.mark.asyncio
    async def test_predicts(self):
        from chimerax_mcp.server import predict_boltz
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await predict_boltz("MKTLLILAVL")
            assert "boltz predict MKTLLILAVL" == mock.call_args[0][0]


class TestShowBumps:
    @pytest.mark.asyncio
    async def test_shows(self):
        from chimerax_mcp.server import show_bumps
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await show_bumps("#1")
            assert "bumps #1" == mock.call_args[0][0]

    @pytest.mark.asyncio
    async def test_hides(self):
        from chimerax_mcp.server import show_bumps
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await show_bumps("#1", show=False)
            assert "~bumps #1" == mock.call_args[0][0]


class TestCheckChirality:
    @pytest.mark.asyncio
    async def test_checks(self):
        from chimerax_mcp.server import check_chirality
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await check_chirality("#1")
            assert "chirality #1" == mock.call_args[0][0]


class TestCrossfade:
    @pytest.mark.asyncio
    async def test_crossfades(self):
        from chimerax_mcp.server import crossfade
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await crossfade(60)
            assert "crossfade 60" == mock.call_args[0][0]


class TestLoadAttributes:
    @pytest.mark.asyncio
    async def test_loads(self):
        from chimerax_mcp.server import load_attributes
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await load_attributes("bfactors.defattr")
            assert 'defattr "bfactors.defattr"' == mock.call_args[0][0]


class TestFlyCamera:
    @pytest.mark.asyncio
    async def test_fly_between_views(self):
        from chimerax_mcp.server import fly_camera
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await fly_camera("start pos1 pos2", frames=30)
            assert "fly 30 start pos1 pos2" == mock.call_args[0][0]


class TestGetCoordinates:
    @pytest.mark.asyncio
    async def test_gets(self):
        from chimerax_mcp.server import get_coordinates
        mock_result = make_result(logs={"info": ["10.5 20.3 30.1"]})
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            result = await get_coordinates("#1/A:100@CA")
            assert "define centroid #1/A:100@CA" == mock.call_args[0][0]


class TestSetGraphics:
    @pytest.mark.asyncio
    async def test_sets_quality(self):
        from chimerax_mcp.server import set_graphics
        mock_result = make_result()
        calls = []
        async def mock_run(cmd, port=None, timeout=None):
            calls.append(cmd)
            return mock_result
        with patch("chimerax_mcp.server.run_chimerax_command", side_effect=mock_run):
            await set_graphics(quality=2.0, silhouettes=True)
            assert any("graphics quality 2.0" in c for c in calls)
            assert any("graphics silhouettes true" in c for c in calls)


class TestShowHkcage:
    @pytest.mark.asyncio
    async def test_t1(self):
        from chimerax_mcp.server import show_hkcage
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await show_hkcage(1, 0, radius=150.0)
            assert "hkcage 1 0 radius 150.0" == mock.call_args[0][0]


class TestManageLog:
    @pytest.mark.asyncio
    async def test_clears(self):
        from chimerax_mcp.server import manage_log
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await manage_log("clear")
            assert "log clear" == mock.call_args[0][0]

    @pytest.mark.asyncio
    async def test_saves(self):
        from chimerax_mcp.server import manage_log
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await manage_log("save", "output.log")
            assert 'log save "output.log"' == mock.call_args[0][0]


class TestRunModeller:
    @pytest.mark.asyncio
    async def test_comparative(self):
        from chimerax_mcp.server import run_modeller
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await run_modeller("#1/A", "comparative")
            assert "modeller comparative #1/A" == mock.call_args[0][0]

    @pytest.mark.asyncio
    async def test_invalid_action(self):
        from chimerax_mcp.server import run_modeller
        with pytest.raises(ValueError):
            await run_modeller("#1", "refine")


class TestPlayMapSeries:
    @pytest.mark.asyncio
    async def test_plays(self):
        from chimerax_mcp.server import play_map_series
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await play_map_series("#2", "play")
            assert "mseries #2 play" == mock.call_args[0][0]


class TestShowMutationScores:
    @pytest.mark.asyncio
    async def test_shows(self):
        from chimerax_mcp.server import show_mutation_scores
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await show_mutation_scores("#1")
            assert "mutationscores #1" == mock.call_args[0][0]


class TestManagePseudobonds:
    @pytest.mark.asyncio
    async def test_styles(self):
        from chimerax_mcp.server import manage_pseudobonds
        mock_result = make_result()
        calls = []
        async def mock_run(cmd, port=None, timeout=None):
            calls.append(cmd)
            return mock_result
        with patch("chimerax_mcp.server.run_chimerax_command", side_effect=mock_run):
            await manage_pseudobonds("#1.3", color="cyan", radius=0.3)
            assert any("color #1.3 cyan" in c for c in calls)
            assert any("size #1.3 stickRadius 0.3" in c for c in calls)

    @pytest.mark.asyncio
    async def test_hides(self):
        from chimerax_mcp.server import manage_pseudobonds
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await manage_pseudobonds("#1.3", show=False)
            assert "hide #1.3 target pb" == mock.call_args[0][0]


class TestResidueFitDensity:
    @pytest.mark.asyncio
    async def test_fits(self):
        from chimerax_mcp.server import residue_fit_density
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await residue_fit_density("#1", "#2")
            assert "resfit #1 inMap #2" == mock.call_args[0][0]


class TestBuildRna:
    @pytest.mark.asyncio
    async def test_builds_path(self):
        from chimerax_mcp.server import build_rna
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await build_rna("1,50,10", length=60)
            cmd = mock.call_args[0][0]
            assert "rna path 1,50,10" in cmd
            assert "length 60" in cmd


class TestRollView:
    @pytest.mark.asyncio
    async def test_rolls(self):
        from chimerax_mcp.server import roll_view
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await roll_view("y", 2.0, 180)
            assert "roll y 2.0 180" == mock.call_args[0][0]


class TestShowTopography:
    @pytest.mark.asyncio
    async def test_shows(self):
        from chimerax_mcp.server import show_topography
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await show_topography("#2")
            assert "topography #2" == mock.call_args[0][0]


class TestWobbleView:
    @pytest.mark.asyncio
    async def test_wobbles(self):
        from chimerax_mcp.server import wobble_view
        mock_result = make_result()
        with patch("chimerax_mcp.server.run_chimerax_command", new_callable=AsyncMock, return_value=mock_result) as mock:
            await wobble_view("y", 5.0, frames=100)
            assert "wobble y 5.0 100" == mock.call_args[0][0]


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
            # 'orthographic' must be mapped to ChimeraX's native 'ortho' camera mode
            assert "camera ortho" in calls
            assert "camera orthographic" not in calls


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
