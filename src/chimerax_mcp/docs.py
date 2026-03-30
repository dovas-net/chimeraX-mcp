"""Documentation module for ChimeraX MCP server.

Provides the atomspec reference guide and functions to look up ChimeraX command
documentation from the installed HTML docs.
"""

import os
import shutil
import sys
from typing import Optional


ATOMSPEC_GUIDE = """# ChimeraX Object Specification Guide

ChimeraX uses a hierarchical atom specification (atomspec) syntax to select models,
chains, residues, and atoms. This guide covers all specifier types with examples.

---

## Hierarchical Specifiers

Atomspecs are built from four levels of the molecular hierarchy:

| Symbol | Level   | Example       | Meaning                          |
|--------|---------|---------------|----------------------------------|
| `#`    | Model   | `#1`          | Model 1                          |
| `/`    | Chain   | `/A`          | Chain A (all models)             |
| `:`    | Residue | `:100`        | Residue 100 (all models/chains)  |
| `@`    | Atom    | `@ca`         | All alpha-carbon atoms           |

Levels can be combined by concatenation:

    #1/A:100        — model 1, chain A, residue 100
    #1/A:100@ca     — alpha-carbon of residue 100 in chain A of model 1
    #2/B:50-75      — residues 50 through 75 in chain B of model 2
    /A:100-200@ca   — CA atoms of residues 100-200 in chain A (any model)

---

## Lists and Ranges

Multiple specifiers at the same level can be combined:

    :100,105,110        — residues 100, 105, and 110
    :100-110            — residues 100 through 110 (inclusive)
    :100-110,150-160    — two residue ranges
    #1,3                — models 1 and 3
    /A,B                — chains A and B
    @ca,cb,cg           — atoms named CA, CB, CG

Wildcards use `*`:

    @c*                 — all atoms starting with 'c' (CA, CB, CG, etc.)
    /A*                 — all chains starting with 'A'
    :A*                 — all residues with names starting with 'A' (e.g., ALA)

---

## Built-in Classifications

ChimeraX provides named sets for common molecular entities:

**Residue-level:**

| Name       | Meaning                                      |
|------------|----------------------------------------------|
| `protein`  | All protein residues (amino acids)           |
| `nucleic`  | All nucleic acid residues (DNA and RNA)      |
| `solvent`  | Solvent molecules (water, ions in some defs) |
| `ligand`   | Small molecule ligands (non-polymer)         |
| `ions`     | Ion atoms                                    |

**Secondary structure (protein only):**

| Name     | Meaning             |
|----------|---------------------|
| `helix`  | Alpha-helix residues |
| `strand` | Beta-strand residues |
| `coil`   | Coil/loop residues  |

**Atom-level:**

| Name        | Meaning                              |
|-------------|--------------------------------------|
| `backbone`  | Backbone atoms (N, CA, C, O for protein; P, C5', etc. for nucleic) |
| `sidechain` | Side-chain atoms                     |
| `aromatic`  | Atoms in aromatic rings              |

**Element symbols** can be used directly (case-insensitive):

    @/element=C         — all carbon atoms
    @/element=N         — all nitrogen atoms
    @/element=FE        — all iron atoms

---

## Zones

Zone specifiers select atoms within a distance of another selection:

    @nz @< 3.8          — atoms within 3.8 Å of atom named NZ
    :< 10.5             — residues with any atom within 10.5 Å of the current selection
    #1 @< 5.0           — atoms of model 1 within 5.0 Å
    ligand @< 4.0       — atoms within 4.0 Å of any ligand atom
    protein @< 5.0 & helix   — helical residues within 5.0 Å of protein

Zone operator variants:

| Operator | Meaning                                      |
|----------|----------------------------------------------|
| `@<`     | Within distance (atom-level zones)           |
| `:<`     | Within distance (residue-level zones)        |
| `@>`     | Beyond distance (atom-level)                 |
| `:>`     | Beyond distance (residue-level)              |

---

## Attributes

Attribute specifiers filter by numeric or boolean properties:

**Atom attributes** (use `@@`):

    @@bfactor>40           — atoms with B-factor greater than 40
    @@bfactor<10           — atoms with B-factor less than 10
    @@occupancy<1.0        — atoms with partial occupancy
    @@charge!=0            — atoms with non-zero partial charge

**Residue attributes** (use `::`):

    ::num_atoms>=10        — residues with 10 or more atoms
    ::ss_type="H"          — residues with helix secondary structure type

**Model attributes** (use `##`):

    ##name=myprotein       — models named 'myprotein'

Comparison operators: `=`, `!=`, `<`, `<=`, `>`, `>=`

---

## Combinations

Boolean operators combine atomspecs:

| Operator | Meaning | Example                              |
|----------|---------|--------------------------------------|
| `&`      | AND     | `protein & helix`                    |
| `|`      | OR      | `protein | nucleic`                  |
| `~`      | NOT     | `~solvent` (everything but solvent)  |

Parentheses control precedence:

    (protein | nucleic) & @@bfactor>40      — high B-factor polymer atoms
    protein & ~helix & ~strand             — coil regions of protein
    #1 & (helix | strand)                  — secondary structure of model 1
    ligand | (protein & @@bfactor>60)      — ligands or high B-factor protein atoms

---

## Common Patterns

Frequently used atomspec patterns:

    #1                          — all atoms in model 1
    #1/A                        — chain A of model 1
    #1/A:100-200                — residues 100-200 in chain A of model 1
    #1/A:100-200@ca             — CA atoms in that range
    protein                     — all protein atoms
    protein & helix             — helical protein regions
    ligand                      — all ligand atoms
    ~(protein | nucleic | solvent | ions)   — everything else (often ligands + misc)
    @@bfactor>40                — high B-factor atoms
    protein & @@bfactor>40      — high B-factor protein atoms
    /A:100 @< 5.0               — atoms within 5 Å of residue 100 chain A
    solvent & /A                — water in chain A
    :HIS,HID,HIE,HIP            — histidine residues (all protonation states)
    @ca & protein               — all alpha-carbons
    nucleic & backbone          — nucleic acid backbone atoms
    #1 & ~solvent               — model 1 without solvent

---

## Quick Reference Card

| Task                              | Atomspec Example                        |
|-----------------------------------|-----------------------------------------|
| Select model 1                    | `#1`                                    |
| Select chain A                    | `/A`                                    |
| Select residue 100                | `:100`                                  |
| Select alpha-carbon atoms         | `@ca`                                   |
| Select residue 100, chain A, model 1 | `#1/A:100`                           |
| Select a residue range            | `#1/A:100-200`                          |
| Select CA atoms in range          | `#1/A:100-200@ca`                       |
| All protein                       | `protein`                               |
| All ligands                       | `ligand`                                |
| Protein helices                   | `protein & helix`                       |
| Protein strands                   | `protein & strand`                      |
| Exclude solvent                   | `~solvent`                              |
| High B-factor atoms               | `@@bfactor>40`                          |
| Atoms near a selection            | `selection @< 5.0`                      |
| Multiple chains                   | `/A,B,C`                                |
| Multiple residues                 | `:100,105,200-210`                      |
| Nucleic acid backbone             | `nucleic & backbone`                    |
| Everything but water/ions         | `~(solvent | ions)`                     |
"""


def get_atomspec_guide() -> str:
    """Return the ChimeraX atomspec reference guide."""
    return ATOMSPEC_GUIDE


def _find_parent_directory(path: str, dir_name: str) -> Optional[str]:
    """Walk up from path looking for a directory named dir_name."""
    while path:
        if os.path.basename(path) == dir_name:
            return path
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return None


def _installation_dir_from_path(path: str) -> Optional[str]:
    """Infer a ChimeraX installation root from a file or directory path."""
    from sys import platform as sys_platform

    if sys_platform == 'darwin':
        cdir = _find_parent_directory(path, 'Contents')
    elif sys_platform == 'win32':
        cdir = _find_parent_directory(path, 'bin')
    else:
        cdir = _find_parent_directory(path, 'bin') or _find_parent_directory(path, 'lib')

    if cdir:
        return os.path.dirname(cdir)
    return None


def _candidate_installation_directories() -> list[str]:
    """Return common ChimeraX installation roots for the current platform."""
    from sys import platform as sys_platform

    candidates: list[str] = []

    if sys_platform == 'darwin':
        import glob as _glob
        candidates.extend(sorted(_glob.glob('/Applications/ChimeraX*.app'), reverse=True))
        candidates.extend(sorted(_glob.glob(os.path.expanduser('~/Applications/ChimeraX*.app')), reverse=True))
    elif sys_platform == 'win32':
        import glob as _glob

        bases = [
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
            os.environ.get("LOCALAPPDATA"),
        ]
        patterns = [
            "ChimeraX*",
            "UCSF/ChimeraX*",
            "RBVI/ChimeraX*",
        ]
        for base in bases:
            if not base:
                continue
            for pattern in patterns:
                candidates.extend(sorted(_glob.glob(os.path.join(base, pattern)), reverse=True))
    else:
        import glob as _glob

        candidates.extend([
            "/opt/UCSF/ChimeraX",
            "/opt/chimerax",
            "/usr/local/chimerax",
            "/usr/local/UCSF/ChimeraX",
            "/usr/share/chimerax",
        ])
        candidates.extend(sorted(_glob.glob('/opt/ChimeraX*'), reverse=True))
        candidates.extend(sorted(_glob.glob('/opt/UCSF/ChimeraX*'), reverse=True))

    deduped: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return deduped


def _find_chimerax_installation_directory() -> Optional[str]:
    """Find the ChimeraX installation directory using multiple strategies."""
    import sys as _sys

    search_paths = [os.path.realpath(_sys.executable), os.path.abspath(__file__)]
    for exe_name in ("ChimeraX", "chimerax", "ChimeraX.exe"):
        resolved = shutil.which(exe_name)
        if resolved:
            search_paths.append(os.path.realpath(resolved))

    for base_path in search_paths:
        install_dir = _installation_dir_from_path(base_path)
        if install_dir:
            return install_dir

    for candidate in _candidate_installation_directories():
        if os.path.exists(candidate):
            return candidate

    return None


def get_docs_path() -> Optional[str]:
    """Return the path to ChimeraX HTML documentation, or None if not found."""
    install_dir = _find_chimerax_installation_directory()
    if install_dir is None:
        return None

    candidate_paths = []
    platform = sys.platform
    if platform == 'darwin':
        candidate_paths.append(os.path.join(install_dir, 'Contents', 'share', 'docs'))
    elif platform == 'win32':
        candidate_paths.extend([
            os.path.join(install_dir, 'bin', 'share', 'docs'),
            os.path.join(install_dir, 'share', 'docs'),
        ])
    else:
        candidate_paths.extend([
            os.path.join(install_dir, 'share', 'docs'),
            os.path.join(install_dir, 'bin', 'share', 'docs'),
        ])

    for docs_path in candidate_paths:
        if os.path.isdir(docs_path):
            return docs_path
    return None


def list_available_commands() -> list:
    """List available ChimeraX commands by scanning the docs directory."""
    docs_path = get_docs_path()
    if docs_path is None:
        return []

    cmd_dir = os.path.join(docs_path, 'user', 'commands')
    if not os.path.isdir(cmd_dir):
        return []

    commands = []
    for filename in os.listdir(cmd_dir):
        if filename.endswith('.html'):
            commands.append(filename[:-5])  # strip .html extension

    return sorted(commands)


def get_command_doc(command_name: str) -> str:
    """Retrieve and convert ChimeraX command documentation to markdown."""
    docs_path = get_docs_path()
    if docs_path is None:
        return f"Documentation not found: ChimeraX installation could not be located."

    cmd_file = os.path.join(docs_path, 'user', 'commands', f'{command_name}.html')
    if not os.path.isfile(cmd_file):
        return f"Documentation not found for command: {command_name}"

    with open(cmd_file, 'r', encoding='utf-8', errors='replace') as f:
        html_content = f.read()

    # Pre-process with BeautifulSoup: replace <br> inside <td> with spaces
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_content, 'html.parser')
    for td in soup.find_all('td'):
        for br in td.find_all('br'):
            br.replace_with(' ')
    processed_html = str(soup)

    # Convert HTML to markdown using html2text
    import html2text
    converter = html2text.HTML2Text()
    converter.body_width = 0
    converter.unicode_snob = True
    converter.ignore_images = True
    converter.ignore_links = True
    markdown = converter.handle(processed_html)

    # Strip HTML copyright comment header (lines starting with <!--)
    lines = markdown.splitlines()
    # Remove leading comment-like lines that html2text may have carried over
    start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('<!--') or stripped.startswith('-->') or (
            stripped == '' and i == start
        ):
            start = i + 1
        elif stripped.startswith('<!--'):
            start = i + 1
        else:
            break

    markdown = '\n'.join(lines[start:])

    # Strip footer: everything after last '---' or '* * *' near end of document
    # Find the last occurrence of a horizontal rule near the end
    parts_dash = markdown.rsplit('\n---', 1)
    parts_star = markdown.rsplit('\n* * *', 1)

    # Use whichever split point is later in the document (longer first part = later split)
    if len(parts_dash) == 2 and len(parts_star) == 2:
        if len(parts_dash[0]) >= len(parts_star[0]):
            markdown = parts_dash[0]
        else:
            markdown = parts_star[0]
    elif len(parts_dash) == 2:
        markdown = parts_dash[0]
    elif len(parts_star) == 2:
        markdown = parts_star[0]

    markdown = markdown.strip()

    # Prepend command header
    header = f"# ChimeraX Command: {command_name}\n\n"
    return header + markdown
