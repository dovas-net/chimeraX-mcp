import os
import tempfile
from unittest.mock import patch
from chimerax_mcp.docs import get_atomspec_guide, get_docs_path, list_available_commands, get_command_doc


class TestAtomspecGuide:
    def test_returns_string(self):
        guide = get_atomspec_guide()
        assert isinstance(guide, str)
        assert len(guide) > 1000

    def test_contains_key_sections(self):
        guide = get_atomspec_guide()
        assert "Hierarchical Specifiers" in guide
        assert "Built-in Classifications" in guide
        assert "Zones" in guide
        assert "Attributes" in guide
        assert "Combinations" in guide
        assert "Quick Reference" in guide

    def test_contains_examples(self):
        guide = get_atomspec_guide()
        assert "#1/A:100" in guide
        assert "@ca" in guide
        assert "protein" in guide
        assert "ligand" in guide


class TestGetDocsPath:
    def test_returns_none_when_no_chimerax(self):
        with patch("chimerax_mcp.docs._find_chimerax_installation_directory", return_value=None):
            assert get_docs_path() is None

    def test_returns_path_when_chimerax_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_path = os.path.join(tmpdir, "Contents", "share", "docs")
            os.makedirs(docs_path)
            with patch("chimerax_mcp.docs._find_chimerax_installation_directory", return_value=tmpdir):
                with patch("sys.platform", "darwin"):
                    result = get_docs_path()
                    assert result == docs_path


class TestListAvailableCommands:
    def test_empty_when_no_docs(self):
        with patch("chimerax_mcp.docs.get_docs_path", return_value=None):
            assert list_available_commands() == []

    def test_finds_html_commands(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_dir = os.path.join(tmpdir, "user", "commands")
            os.makedirs(cmd_dir)
            for name in ["open.html", "color.html", "save.html"]:
                open(os.path.join(cmd_dir, name), "w").close()
            with patch("chimerax_mcp.docs.get_docs_path", return_value=tmpdir):
                commands = list_available_commands()
                assert "open" in commands
                assert "color" in commands
                assert "save" in commands
                assert commands == sorted(commands)


class TestGetCommandDoc:
    def test_returns_error_when_no_docs(self):
        with patch("chimerax_mcp.docs.get_docs_path", return_value=None):
            result = get_command_doc("open")
            assert "not found" in result.lower()

    def test_converts_html_to_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cmd_dir = os.path.join(tmpdir, "user", "commands")
            os.makedirs(cmd_dir)
            with open(os.path.join(cmd_dir, "open.html"), "w") as f:
                f.write("<html><body><h1>Open Command</h1><p>Opens a file.</p></body></html>")
            with patch("chimerax_mcp.docs.get_docs_path", return_value=tmpdir):
                result = get_command_doc("open")
                assert "Open Command" in result
                assert "Opens a file" in result
                assert "# ChimeraX Command: open" in result
