"""Formatting utilities for ChimeraX MCP responses."""

import json
import logging
import re

logger = logging.getLogger("chimerax_mcp.formatting")

# Patterns that suggest suspicious input (not shell injection — ChimeraX command abuse)
_SUSPICIOUS_PATTERNS = [
    "runscript",
    "open.*\\.py",
    "import os",
    "import sys",
    "exec(",
    "eval(",
]


def validate_atomspec(spec: str) -> str:
    """Validate and clean an atomspec string.

    Strips whitespace, rejects empty strings, and warns on suspicious patterns.
    Returns the cleaned spec.
    """
    if spec is None:
        raise ValueError("Atomspec cannot be None")
    spec = str(spec).strip()
    if not spec:
        raise ValueError("Atomspec cannot be empty")
    return spec


def quote_chimerax_arg(value: str) -> str:
    """Quote a free-form ChimeraX command argument.

    This is intended for filenames, labels, preset names, and other text values
    that may contain spaces or quotes. The value is always wrapped in double
    quotes and escaped for ChimeraX's command parser.
    """
    if value is None:
        raise ValueError("Command argument cannot be None")

    text = str(value)
    escaped = (
        text
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def format_chimerax_response(result: dict, context: str = "") -> str:
    """Format a ChimeraX REST API result into a human-readable string.

    Uses a cascading fallback strategy:
    1. Log messages (by severity)
    2. JSON values
    3. Return values
    4. "Command completed successfully" if nothing else
    """
    lines = []

    if context:
        lines.append(context)

    # Priority 1: Log messages
    log_lines = []
    log_level_order = ["error", "warning", "info", "note", "debug"]
    logs = result.get("logs", {})

    for level in log_level_order:
        messages = logs.get(level, [])
        if not messages:
            continue
        filtered = []
        for msg in messages:
            if not msg:
                continue
            # Filter out command echo lines: start with "[" and contain 2+ markdown links
            if msg.startswith("[") and len(re.findall(r"\]\(", msg)) >= 2:
                continue
            filtered.append(msg)
        if filtered:
            combined = "; ".join(filtered)
            log_lines.append(f"{level.upper()}: {combined}")

    if log_lines:
        lines.extend(log_lines)
        return "\n".join(lines)

    # Priority 2: JSON values
    json_values = [v for v in result.get("json_values", []) if v is not None]
    if json_values:
        lines.append("JSON Output:")
        for val in json_values:
            lines.append(json.dumps(val, indent=2))
        return "\n".join(lines)

    # Priority 3: Return values
    return_values = [v for v in result.get("return_values", []) if v is not None]
    if return_values:
        lines.append("Output:")
        for val in return_values:
            lines.append(str(val))
        return "\n".join(lines)

    # Nothing generated beyond context
    if lines:
        lines.append("Command completed successfully")
        return "\n".join(lines)

    return "Command completed successfully"


# Commands that take atomspecs as their primary argument
_ATOMSPEC_COMMANDS = {
    "select", "color", "show", "hide", "style", "cartoon",
    "display", "label", "size", "view", "zone", "surface",
}


def add_error_hints(error_type: str, error_msg: str, command: str) -> str:
    """Add contextual hints to error messages based on pattern matching."""
    logger.debug("Adding hints for %s: %s (command: %s)", error_type, error_msg[:100], command[:60])
    msg_lower = error_msg.lower()
    cmd_lower = command.lower().strip()
    cmd_name = cmd_lower.split()[0] if cmd_lower.split() else ""

    hint = None

    # Atomspec errors
    atomspec_patterns = [
        "expected an objects specifier",
        "invalid an atom specifier",
        "not an atom specifier",
        "empty atom specifier",
        "is not a selector name",
        "only initial part",
    ]
    is_atomspec_error = any(p in msg_lower for p in atomspec_patterns)

    # "expected a keyword" when used with an atomspec command
    if not is_atomspec_error and "expected a keyword" in msg_lower and cmd_name in _ATOMSPEC_COMMANDS:
        is_atomspec_error = True

    if is_atomspec_error:
        hint = (
            "Atom specification syntax error.\n"
            "→ Use get_atomspec_guide() for full syntax reference\n"
            "→ Common patterns: #1 (model), #1/A (chain), #1/A:100 (residue), @ca (atom name), protein (selector)\n"
            "→ Model IDs require the # prefix (e.g., #1 not 1)"
        )
        return f"{error_type}: {error_msg}\n\n🔍 HINT: {hint}"

    # No atoms matched
    no_atoms_patterns = ["no atoms matched", "nothing specified"]
    if any(p in msg_lower for p in no_atoms_patterns):
        hint = (
            "No atoms matched the specification.\n"
            "→ Use list_models() to see available models and their IDs\n"
            "→ Check chain IDs and verify residues exist in the structure\n"
            "→ Confirm model is loaded and the spec is correct"
        )
        return f"{error_type}: {error_msg}\n\n🔍 HINT: {hint}"

    # Model errors
    model_patterns = [
        "no models",
        "no atomic structures",
        "must specify 1 model",
        "must specify 1 atomic structure",
        "must specify exactly one",
    ]
    if any(p in msg_lower for p in model_patterns):
        hint = (
            "No matching model found.\n"
            "→ Use list_models() to see all open models\n"
            "→ Use open_structure() to open a structure if none are loaded"
        )
        return f"{error_type}: {error_msg}\n\n🔍 HINT: {hint}"

    # Command errors
    command_patterns = ["unknown command", "no command"]
    if any(p in msg_lower for p in command_patterns):
        # Try to extract the unknown command name from the error message
        unknown_cmd = cmd_name
        match = re.search(r"unknown command[:\s]+(\S+)", error_msg, re.IGNORECASE)
        if match:
            unknown_cmd = match.group(1)
        hint = (
            f"Command '{unknown_cmd}' is not recognized.\n"
            "→ Use list_chimerax_commands() to browse available commands\n"
            f"→ Use get_command_documentation('{unknown_cmd}') to check if it exists under a different name"
        )
        return f"{error_type}: {error_msg}\n\n🔍 HINT: {hint}"

    # Argument errors
    argument_patterns = ["missing or invalid", "missing required", "expected", "should be", "require"]
    if any(p in msg_lower for p in argument_patterns):
        hint = (
            f"Invalid or missing argument for command '{cmd_name}'.\n"
            f"→ Use get_command_documentation() with '{cmd_name}' to see correct syntax and required arguments"
        )
        return f"{error_type}: {error_msg}\n\n🔍 HINT: {hint}"

    # File errors
    file_patterns = ["cannot open", "file not found", "no such file", "cannot read", "does not exist"]
    if any(p in msg_lower for p in file_patterns):
        hint = (
            "File not found or inaccessible.\n"
            "→ Verify the file path is correct\n"
            "→ Use absolute paths to avoid working directory issues"
        )
        return f"{error_type}: {error_msg}\n\n🔍 HINT: {hint}"

    # Generic fallback
    hint = (
        "An unexpected error occurred.\n"
        "→ Use list_models() to check what is currently open\n"
        "→ Use get_atomspec_guide() for atom selection syntax\n"
        "→ Use get_command_documentation() for command usage"
    )
    return f"{error_type}: {error_msg}\n\n🔍 HINT: {hint}"


def format_single_model_info(model: dict) -> list[str]:
    """Format a single model dict into a list of display lines.

    Accepts the aggregated format from ChimeraX 1.11.1 REST API:
        {"spec": "#1", "name": "1abc", "class": "AtomicStructure",
         "display": True, "num_atoms": 6087}
    """
    spec = model.get("spec", "?")
    # spec already has '#' prefix from the new format; don't double-prefix
    if not str(spec).startswith("#"):
        spec = f"#{spec}"

    name = model.get("name", "unknown")
    model_class = model.get("class", "")

    # Accept both old "shown" and new "display" keys
    display = model.get("display", model.get("shown", False))
    visibility = "shown" if display else "hidden"

    # Build the main line
    class_part = f" ({model_class})" if model_class else ""
    line1 = f"{spec}, {name}{class_part}, {visibility}"

    lines = [line1]

    # Atom count — accept both "num_atoms" and legacy "num atoms"
    num_atoms = model.get("num_atoms", model.get("num atoms"))
    if num_atoms is not None:
        lines.append(f"  {num_atoms} atoms")

    return lines
