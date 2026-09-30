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


class TestFindInstallationDirectory:
    def test_ignores_non_chimerax_bin_directories(self, tmp_path):
        """A python in <prefix>/bin must not make <prefix> look like ChimeraX (was: '/usr')."""
        from chimerax_mcp import docs

        fake_python = tmp_path / "bin" / "python3"
        fake_python.parent.mkdir()
        fake_python.touch()
        with patch.dict(os.environ, {}, clear=False), \
             patch("chimerax_mcp.docs.sys.executable", str(fake_python)), \
             patch("chimerax_mcp.docs.shutil.which", return_value=None), \
             patch("chimerax_mcp.docs._candidate_installation_directories", return_value=[]), \
             patch("sys.platform", "linux"):
            os.environ.pop("CHIMERAX_PATH", None)
            assert docs._find_chimerax_installation_directory() is None

    def test_uses_chimerax_path_override(self, tmp_path):
        from chimerax_mcp import docs

        exe = tmp_path / "chimerax-1.11" / "bin" / "ChimeraX"
        exe.parent.mkdir(parents=True)
        exe.touch()
        with patch.dict(os.environ, {"CHIMERAX_PATH": str(exe)}), \
             patch("chimerax_mcp.docs.shutil.which", return_value=None), \
             patch("sys.platform", "linux"):
            assert docs._find_chimerax_installation_directory() == str(tmp_path / "chimerax-1.11")

    def test_accepts_candidate_with_docs(self, tmp_path):
        from chimerax_mcp import docs

        (tmp_path / "share" / "docs" / "user" / "commands").mkdir(parents=True)
        with patch.dict(os.environ, {}, clear=False), \
             patch("chimerax_mcp.docs.shutil.which", return_value=None), \
             patch("chimerax_mcp.docs.sys.executable", "/nonexistent/python"), \
             patch("chimerax_mcp.docs._candidate_installation_directories", return_value=[str(tmp_path)]), \
             patch("sys.platform", "linux"):
            os.environ.pop("CHIMERAX_PATH", None)
            assert docs._find_chimerax_installation_directory() == str(tmp_path)


class TestCommandDocNames:
    def _docs_with(self, tmpdir, *names):
        cmd_dir = os.path.join(tmpdir, "user", "commands")
        os.makedirs(cmd_dir)
        for name in names:
            with open(os.path.join(cmd_dir, f"{name}.html"), "w") as f:
                f.write(f"<html><body><h1>{name} docs</h1></body></html>")

    def test_subcommand_uses_parent_page(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._docs_with(tmpdir, "surface")
            with patch("chimerax_mcp.docs.get_docs_path", return_value=tmpdir):
                result = get_command_doc("surface dust")
                assert "# ChimeraX Command: surface" in result
                assert "surface docs" in result

    def test_negated_and_capitalized_forms(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._docs_with(tmpdir, "select")
            with patch("chimerax_mcp.docs.get_docs_path", return_value=tmpdir):
                assert "select docs" in get_command_doc("~select")
                assert "select docs" in get_command_doc("Select")

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._docs_with(tmpdir, "open")
            with open(os.path.join(tmpdir, "secret.html"), "w") as f:
                f.write("<html><body>secret</body></html>")
            with patch("chimerax_mcp.docs.get_docs_path", return_value=tmpdir):
                result = get_command_doc("../../secret")
                assert "not found" in result.lower()
                assert "secret</" not in result
