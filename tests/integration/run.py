"""Tier 3 integration runner.

DESTRUCTIVE. The runner clears caption lines and removes the master object
between tests. Always run in an isolated Blender process, NEVER against
your working file:

    blender --background --factory-startup --python tests/integration/run.py

If a captions_tool/ checkout lives outside the standard addons directory,
point at it first:

    set BLCAP_REPO=C:\\path\\to\\blender-captions
    blender --background --factory-startup --python tests/integration/run.py

If the runner is invoked interactively (Blender UI is up, bpy.app.background
is False), it refuses to start unless BLCAP_TEST_INTERACTIVE_OK=1 is set.
Even then, it saves the current .blend file first so a crash can't take
unsaved work with it.

The runner discovers every test_*.py file in tests/integration/, imports it,
calls each function whose name starts with `test_`, and prints PASS / FAIL
with the assertion message on failure. Returns exit code 0 on all-pass, 1
otherwise. Exit code 2 means the runner refused to start.
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


def _safety_gate() -> int | None:
    """Refuse to run against a live user session unless explicitly opted in.

    Returns an exit code if the gate failed, or None to proceed.
    """
    if bpy.app.background:
        return None  # --background is the intended path; proceed
    if os.environ.get("BLCAP_TEST_INTERACTIVE_OK") != "1":
        print()
        print("REFUSING TO RUN: this runner is destructive (clears caption lines,")
        print("removes the master object, mutates F-curves between tests) and")
        print("would damage your working file.")
        print()
        print("Run via the intended path instead:")
        print("    blender --background --factory-startup --python tests/integration/run.py")
        print("or:")
        print("    .\\tasks.ps1 test-blender")
        print()
        print("To bypass this gate INSIDE your current Blender session,")
        print("set BLCAP_TEST_INTERACTIVE_OK=1 first. The runner will then save")
        print("your current .blend before starting, but a crash mid-test can still")
        print("leave the in-memory scene in a destroyed state.")
        return 2

    # Bypass requested. Save the user's working file before anything destructive.
    filepath = bpy.data.filepath
    if filepath:
        try:
            bpy.ops.wm.save_mainfile()
            print(f"Saved {filepath} before running tests.")
        except Exception as exc:
            print(f"WARNING: couldn't auto-save current file: {exc}")
            print("Aborting -- save manually, then re-run.")
            return 2
    else:
        print("WARNING: current Blender session has no .blend filepath.")
        print("Unsaved scene data WILL be destroyed by the tests.")
        print("Save your work manually, then set BLCAP_TEST_INTERACTIVE_OK=1 and re-run.")
        return 2

    return None


def _run() -> int:
    gate = _safety_gate()
    if gate is not None:
        return gate

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
