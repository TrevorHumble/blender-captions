"""Tier 1: repo-hygiene checks. No Blender, no pytest, no network.

Run from the repo root:

    python tests/lint/check.py

Returns exit code 0 if everything passes, 1 otherwise. Each check prints
either PASS or FAIL with a one-line reason. The whole suite finishes in
under a second.
"""
from __future__ import annotations

import ast
import os
import re
import sys
import zipfile
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent.parent
ADDON = REPO / "captions_tool"
DIST = REPO / "dist"
SCRIPTS = REPO / "scripts"
SKILLS = REPO / "skills"

ERRORS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    """Record a check result. `detail` is shown when ok is False."""
    if ok:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}: {detail}")
        ERRORS.append(name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def bl_info_version() -> str:
    """Return version as 'X.Y.Z' from captions_tool/__init__.py bl_info."""
    src = read(ADDON / "__init__.py")
    match = re.search(r'"version"\s*:\s*\((\d+),\s*(\d+),\s*(\d+)\)', src)
    if not match:
        return ""
    return ".".join(match.groups())


def find_classes_in_module(path: Path) -> set[str]:
    """Return names of every class defined at module level."""
    tree = ast.parse(read(path))
    return {n.name for n in tree.body if isinstance(n, ast.ClassDef)}


def find_classes_tuple(path: Path) -> set[str]:
    """Return names referenced in a module-level `_CLASSES = (...)` tuple."""
    tree = ast.parse(read(path))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "_CLASSES" for t in node.targets):
            continue
        if not isinstance(node.value, ast.Tuple):
            continue
        return {elt.id for elt in node.value.elts if isinstance(elt, ast.Name)}
    return set()


def find_operator_ids() -> dict[str, str]:
    """Return {bl_idname: class_name} for every Operator subclass in operators.py."""
    src = read(ADDON / "operators.py")
    tree = ast.parse(src)
    result: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        is_op = any(
            (isinstance(b, ast.Attribute) and b.attr == "Operator")
            or (isinstance(b, ast.Name) and b.id == "Operator")
            for b in node.bases
        )
        if not is_op:
            continue
        for stmt in node.body:
            if (
                isinstance(stmt, ast.AnnAssign)
                and isinstance(stmt.target, ast.Name)
                and stmt.target.id == "bl_idname"
            ):
                if isinstance(stmt.value, ast.Constant):
                    result[stmt.value.value] = node.name
            elif (
                isinstance(stmt, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "bl_idname" for t in stmt.targets)
                and isinstance(stmt.value, ast.Constant)
            ):
                result[stmt.value.value] = node.name
    return result


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_version_consistency() -> None:
    version = bl_info_version()
    check("bl_info.version is parseable", bool(version), "couldn't find version in __init__.py")
    if not version:
        return

    # README install link + rebuild snippet
    readme = read(REPO / "README.md")
    expected_zip = f"captions_tool-{version}.zip"
    check(
        f"README references {expected_zip}",
        expected_zip in readme,
        f"README has no mention of {expected_zip}",
    )

    # SKILL.md install reference
    skill = read(SKILLS / "headless-captions" / "SKILL.md")
    check(
        f"SKILL.md references {expected_zip}",
        expected_zip in skill,
        f"SKILL.md missing {expected_zip}",
    )

    # dist contains the exact zip and nothing stale
    zips = sorted(DIST.glob("captions_tool-*.zip"))
    check("dist/ contains exactly one zip", len(zips) == 1, f"found {[z.name for z in zips]}")
    if zips:
        check(
            f"dist zip filename matches version ({expected_zip})",
            zips[0].name == expected_zip,
            f"found {zips[0].name}",
        )


def check_dist_zip_fresh() -> None:
    version = bl_info_version()
    if not version:
        return
    zip_path = DIST / f"captions_tool-{version}.zip"
    if not zip_path.exists():
        check("dist zip is fresh", False, f"{zip_path.name} doesn't exist")
        return

    # Compare zip contents against on-disk source. Different bytes = stale rebuild.
    stale: list[str] = []
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            # ZipFile entries are like "captions_tool/__init__.py"; map to disk.
            rel = info.filename.split("/", 1)[1] if "/" in info.filename else ""
            if not rel:
                continue
            disk_path = ADDON / rel
            if not disk_path.is_file():
                stale.append(f"{info.filename} (missing on disk)")
                continue
            disk_bytes = disk_path.read_bytes()
            with zf.open(info) as f:
                zip_bytes = f.read()
            if disk_bytes != zip_bytes:
                stale.append(info.filename)
    check("dist zip matches captions_tool/ source", not stale, f"stale: {stale[:3]}")


def check_operator_coverage() -> None:
    operator_ids = find_operator_ids()  # {bl_idname: class_name}

    readme = read(REPO / "README.md")
    api = read(ADDON / "api_docs.py")
    skill = read(SKILLS / "headless-captions" / "SKILL.md")

    missing_readme: list[str] = []
    missing_api: list[str] = []
    missing_skill: list[str] = []
    for bl_id in operator_ids:
        short = bl_id.removeprefix("captions.")
        if short not in readme:
            missing_readme.append(short)
        if short not in api:
            missing_api.append(short)
        if short not in skill:
            missing_skill.append(short)
    check("every operator listed in README", not missing_readme, f"missing: {missing_readme}")
    check("every operator listed in api_docs", not missing_api, f"missing: {missing_api}")
    check("every operator listed in SKILL.md", not missing_skill, f"missing: {missing_skill}")


def check_cleanup_class_list() -> None:
    cleanup_src = read(SCRIPTS / "cleanup.py")
    cleanup_list = set(re.findall(r'"(Caption[A-Za-z_]*|CAPTIONS_[A-Z_]+[a-z_]*)"', cleanup_src))

    registered: set[str] = set()
    for mod in ("props.py", "operators.py", "ui.py"):
        registered |= find_classes_tuple(ADDON / mod)

    missing = registered - cleanup_list
    extra = cleanup_list - registered
    check(
        "cleanup.py CAPTION_CLASSES matches registered _CLASSES",
        not missing and not extra,
        f"missing in cleanup: {sorted(missing)}; extra: {sorted(extra)}",
    )


def check_bl_idname_uniqueness() -> None:
    ids = find_operator_ids()
    seen: dict[str, str] = {}
    dupes: list[str] = []
    for bl_id, cls in ids.items():
        if bl_id in seen:
            dupes.append(f"{bl_id} ({cls}, {seen[bl_id]})")
        else:
            seen[bl_id] = cls
    check("bl_idname strings are unique", not dupes, f"duplicates: {dupes}")
    bad_prefix = [i for i in ids if not i.startswith("captions.")]
    check("every bl_idname is prefixed 'captions.'", not bad_prefix, f"offenders: {bad_prefix}")


def check_persistent_decorator_on_handlers() -> None:
    src = read(ADDON / "handlers.py")
    tree = ast.parse(src)
    handler_names = {"on_frame_change", "on_depsgraph_update", "on_load_post"}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or node.name not in handler_names:
            continue
        names = []
        for d in node.decorator_list:
            if isinstance(d, ast.Name):
                names.append(d.id)
            elif isinstance(d, ast.Attribute):
                names.append(d.attr)
        check(
            f"{node.name} has @persistent",
            "persistent" in names,
            f"decorators: {names}",
        )


def check_operator_docstrings_and_options() -> None:
    src = read(ADDON / "operators.py")
    tree = ast.parse(src)
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        is_op = any(
            (isinstance(b, ast.Attribute) and b.attr == "Operator")
            or (isinstance(b, ast.Name) and b.id == "Operator")
            for b in node.bases
        )
        if not is_op:
            continue
        has_docstring = (
            isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        )
        check(f"{node.name} has a docstring", has_docstring)


def check_no_user_specific_paths_in_skills() -> None:
    """Skills must be generic. No personal paths like C:\\Users\\<name>\\
    or /home/<name>/ should leak into committed skill files -- they'd
    embarrass us when someone else clones the repo and finds someone's
    home directory in a workflow doc.

    This check excludes itself (this file contains the patterns as
    string literals, which would otherwise trip the scan).
    """
    bad_patterns = [
        re.compile(r"[Cc]:[\\/]+[Uu]sers[\\/]+[^\\/<>]+"),
        re.compile(r"/home/[^/<>\s]+"),
        re.compile(r"/Users/[^/<>\s]+"),
    ]
    this_file = Path(__file__).resolve()
    offenders: list[str] = []
    for root in (SKILLS, REPO / "tests", REPO / "scripts"):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in (".md", ".py"):
                continue
            if path.resolve() == this_file:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for pat in bad_patterns:
                for match in pat.findall(text):
                    if "<" in match and ">" in match:
                        continue
                    offenders.append(f"{path.relative_to(REPO)}: {match[:60]}")
    check(
        "no user-specific paths in skills/tests/scripts",
        not offenders,
        f"offenders: {offenders[:3]}",
    )


def check_master_name_constant_used() -> None:
    """No hard-coded 'Captions' string in object/curve lookup contexts.

    Legitimate uses: bl_info["name"], bl_category, button labels. Bad uses:
    bpy.data.objects.get("Captions"), bpy.data.curves["Captions"], etc.
    """
    bad_patterns = [
        re.compile(r'bpy\.data\.objects(?:\.get)?\(\s*"Captions"'),
        re.compile(r'bpy\.data\.objects\[\s*"Captions"\s*\]'),
        re.compile(r'bpy\.data\.curves(?:\.get)?\(\s*"Captions"'),
        re.compile(r'bpy\.data\.curves\[\s*"Captions"\s*\]'),
    ]
    offenders: list[str] = []
    for py in ADDON.glob("*.py"):
        if py.name == "master.py":
            continue  # MASTER_NAME constant is defined here
        text = read(py)
        for pat in bad_patterns:
            if pat.search(text):
                offenders.append(f"{py.name} ({pat.pattern})")
    check(
        "no hard-coded 'Captions' in bpy.data lookups",
        not offenders,
        f"see: {offenders}",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("Running blender-captions Tier 1 lint checks...\n")
    print("Version consistency")
    check_version_consistency()
    print("\nDist zip freshness")
    check_dist_zip_fresh()
    print("\nOperator coverage in docs")
    check_operator_coverage()
    print("\nCleanup script class list")
    check_cleanup_class_list()
    print("\nbl_idname uniqueness + prefix")
    check_bl_idname_uniqueness()
    print("\n@persistent on handlers")
    check_persistent_decorator_on_handlers()
    print("\nOperator docstrings")
    check_operator_docstrings_and_options()
    print("\nMASTER_NAME usage")
    check_master_name_constant_used()
    print("\nNo personal paths in skills/tests")
    check_no_user_specific_paths_in_skills()

    print()
    if ERRORS:
        print(f"{len(ERRORS)} check(s) failed: {ERRORS}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
