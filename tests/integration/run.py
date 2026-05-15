"""Tier 3 integration runner.

Run inside Blender:

    blender --background --factory-startup --python tests/integration/run.py

Or, if the captions_tool/ source is checked out somewhere outside the addons
directory, point sys.path at it before launching:

    set BLCAP_REPO=C:\\path\\to\\blender-captions
    blender --background --factory-startup --python tests/integration/run.py

The runner discovers every test_*.py file in tests/integration/, imports it,
calls each function whose name starts with `test_`, and prints PASS / FAIL
with the assertion message on failure. Returns exit code 0 on all-pass, 1
otherwise.

State isolation: each test runs after `reset_addon_state()` clears the
scene's caption lines and removes the master object + curve, so tests
don't see each other's data.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import traceback
from pathlib import Path

import bpy


# ---------------------------------------------------------------------------
# Bootstrap: find and enable the addon
# ---------------------------------------------------------------------------

def _bootstrap_addon() -> None:
    """Make sure captions_tool is importable and registered."""
    repo_env = os.environ.get("BLCAP_REPO")
    if repo_env:
        repo_root = Path(repo_env)
    else:
        # This file is tests/integration/run.py; repo root is two parents up.
        repo_root = Path(__file__).resolve().parent.parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    # If a previous run left the addon registered, clean up first.
    if "captions_tool" in sys.modules:
        try:
            sys.modules["captions_tool"].unregister()
        except Exception:
            pass
        for mod in list(sys.modules):
            if mod == "captions_tool" or mod.startswith("captions_tool."):
                del sys.modules[mod]

    import captions_tool
    captions_tool.register()
    print(f"Addon loaded from {repo_root / 'captions_tool'}")


# ---------------------------------------------------------------------------
# Per-test state isolation
# ---------------------------------------------------------------------------

def reset_addon_state() -> None:
    """Wipe scene captions data + master object so each test starts clean."""
    scene = bpy.context.scene
    if hasattr(scene, "captions"):
        scene.captions.lines.clear()
        scene.captions.active_index = 0
        scene.captions.master_object = None
        scene.captions.next_id = 1

    for obj_name in ("Captions",):
        if obj_name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[obj_name], do_unlink=True)
        if obj_name in bpy.data.curves:
            bpy.data.curves.remove(bpy.data.curves[obj_name])


# ---------------------------------------------------------------------------
# Discovery and dispatch
# ---------------------------------------------------------------------------

def _discover_tests():
    """Yield (test_name, callable) for every test_* function in tests/integration/test_*.py."""
    test_dir = Path(__file__).resolve().parent
    for path in sorted(test_dir.glob("test_*.py")):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            print(f"  IMPORT-FAIL {path.name}: {exc}")
            yield f"{path.stem}::__import__", lambda: (_ for _ in ()).throw(exc)
            continue
        for attr in sorted(dir(module)):
            if not attr.startswith("test_"):
                continue
            fn = getattr(module, attr)
            if callable(fn):
                yield f"{path.stem}::{attr}", fn


def _run() -> int:
    _bootstrap_addon()

    passed: list[str] = []
    failed: list[tuple[str, str]] = []

    print()
    for name, fn in _discover_tests():
        reset_addon_state()
        try:
            fn()
        except Exception:
            tb = traceback.format_exc(limit=3)
            failed.append((name, tb))
            print(f"  FAIL  {name}")
            continue
        passed.append(name)
        print(f"  PASS  {name}")

    print()
    print(f"{len(passed)} passed, {len(failed)} failed")
    for name, tb in failed:
        print(f"\n--- {name} ---\n{tb}")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(_run())
