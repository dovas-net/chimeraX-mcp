from chimerax_mcp.formatting import (
    add_error_hints,
    format_chimerax_response,
    format_single_model_info,
    quote_chimerax_arg,
)


class TestFormatChimeraXResponse:
    def test_logs_priority(self):
        result = {
            "return_values": ["some_value"],
            "json_values": [{"key": "val"}],
            "logs": {"info": ["Structure opened successfully"]},
        }
        output = format_chimerax_response(result)
        assert "INFO: Structure opened successfully" in output

    def test_json_fallback_when_no_logs(self):
        result = {
            "return_values": [],
            "json_values": [{"atoms": 100}],
            "logs": {},
        }
        output = format_chimerax_response(result)
        assert "JSON Output" in output
        assert '"atoms": 100' in output

    def test_python_values_fallback(self):
        result = {
            "return_values": [42],
            "json_values": [],
            "logs": {},
        }
        output = format_chimerax_response(result)
        assert "Output" in output
        assert "42" in output

    def test_success_when_empty(self):
        result = {"return_values": [], "json_values": [], "logs": {}}
        output = format_chimerax_response(result)
        assert "Command completed successfully" in output

    def test_context_prepended(self):
        result = {"return_values": [], "json_values": [], "logs": {"info": ["done"]}}
        output = format_chimerax_response(result, context="Opened 1abc")
        assert output.startswith("Opened 1abc")

    def test_filters_markdown_link_echoes(self):
        result = {
            "return_values": [],
            "json_values": [],
            "logs": {"info": ["[open](cmd:open) [1abc](cmd:1abc) more links", "Real info"]},
        }
        output = format_chimerax_response(result)
        assert "Real info" in output
        assert "cmd:open" not in output

    def test_none_values_filtered(self):
        result = {
            "return_values": [None, 42, None],
            "json_values": [],
            "logs": {},
        }
        output = format_chimerax_response(result)
        assert "42" in output

    def test_multiple_log_levels(self):
        result = {
            "return_values": [],
            "json_values": [],
            "logs": {
                "warning": ["Low resolution"],
                "info": ["Model loaded"],
            },
        }
        output = format_chimerax_response(result)
        warn_pos = output.index("WARNING")
        info_pos = output.index("INFO")
        assert warn_pos < info_pos


class TestAddErrorHints:
    def test_atomspec_error(self):
        msg = add_error_hints("UserError", "Expected an objects specifier", "color foo red")
        assert "get_atomspec_guide()" in msg
        assert "#1" in msg

    def test_no_models_error(self):
        msg = add_error_hints("UserError", "No models specified by #5", "color #5 red")
        assert "list_models()" in msg

    def test_unknown_command_error(self):
        msg = add_error_hints("UserError", "Unknown command: foobar", "foobar #1")
        assert "list_chimerax_commands()" in msg
        assert "foobar" in msg

    def test_argument_error(self):
        msg = add_error_hints("UserError", "Missing or invalid width argument", "save img.png width")
        assert "get_command_documentation()" in msg

    def test_file_error(self):
        msg = add_error_hints("UserError", "File not found: bad.pdb", "open bad.pdb")
        assert "absolute paths" in msg

    def test_generic_error(self):
        msg = add_error_hints("InternalError", "something weird happened", "weird")
        assert "HINT" in msg

    def test_no_atoms_matched(self):
        msg = add_error_hints("UserError", "no atoms matched specification", "select #1/Z")
        assert "list_models()" in msg
        assert "chain IDs" in msg


class TestQuoteChimeraXArg:
    def test_wraps_with_quotes(self):
        assert quote_chimerax_arg("My File.cxs") == '"My File.cxs"'

    def test_escapes_quotes_and_backslashes(self):
        value = 'C:\\Users\\docas\\"quoted".pdb'
        assert quote_chimerax_arg(value) == '"C:\\\\Users\\\\docas\\\\\\"quoted\\".pdb"'


class TestFormatSingleModelInfo:
    def test_atomic_structure(self):
        model = {
            "spec": "#1",
            "name": "1abc",
            "class": "AtomicStructure",
            "display": True,
            "num_atoms": 5000,
        }
        lines = format_single_model_info(model)
        assert "#1, 1abc (AtomicStructure), shown" in lines[0]
        assert "5000 atoms" in lines[1]

    def test_volume_model(self):
        model = {
            "spec": "#2",
            "name": "map",
            "class": "Volume",
            "display": True,
        }
        lines = format_single_model_info(model)
        assert "#2, map (Volume), shown" in lines[0]

    def test_hidden_model(self):
        model = {"spec": "#3", "name": "test", "display": False}
        lines = format_single_model_info(model)
        assert "hidden" in lines[0]
