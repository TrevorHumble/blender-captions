"""Tier 2 unit tests for captions_tool.timeline._parse_keyframes.

Pure-Python, no Blender required. Run from the repo root:

    pytest tests/unit
"""
from __future__ import annotations

import types
from pathlib import Path

# timeline.py imports bpy at the top level. Stub it before loading the module
# so importlib doesn't choke.
import sys
import types as _types

# Provide a minimal bpy stub so the module-level `import bpy` succeeds.
_bpy_stub = _types.ModuleType("bpy")
sys.modules.setdefault("bpy", _bpy_stub)

# timeline.py also does `from .events import compute_events, NO_CAPTION as _NONE`.
# Load events.py directly first and register it under the package namespace that
# timeline.py expects.
import importlib.util

_CAPTIONS_TOOL = Path(__file__).resolve().parent.parent.parent / "captions_tool"

_events_spec = importlib.util.spec_from_file_location(
    "captions_tool.events", _CAPTIONS_TOOL / "events.py"
)
_events_mod = importlib.util.module_from_spec(_events_spec)
sys.modules["captions_tool.events"] = _events_mod
_events_spec.loader.exec_module(_events_mod)

# Also register the package itself so relative imports resolve.
_pkg_stub = _types.ModuleType("captions_tool")
_pkg_stub.events = _events_mod
sys.modules.setdefault("captions_tool", _pkg_stub)

# Now load timeline.py.
_timeline_spec = importlib.util.spec_from_file_location(
    "captions_tool.timeline", _CAPTIONS_TOOL / "timeline.py"
)
_timeline_mod = importlib.util.module_from_spec(_timeline_spec)
sys.modules["captions_tool.timeline"] = _timeline_mod
_timeline_spec.loader.exec_module(_timeline_mod)

_parse_keyframes = _timeline_mod._parse_keyframes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def MockKP(x, y):
    """Minimal stand-in for a Blender keyframe point. Only .co.x / .co.y needed."""
    co = types.SimpleNamespace(x=x, y=y)
    return types.SimpleNamespace(co=co)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_parse_keyframes_overlap_returns_none_for_covered_end():
    """Issue #9 regression. L1: 10-50 covered by L2: 30-70.
    L1's end must be None (no dedicated sentinel); L2's end must be 70."""
    kps = [MockKP(9, -1), MockKP(10, 1), MockKP(30, 2), MockKP(70, -1)]
    result = _parse_keyframes(kps)
    by_id = {eid: end for (eid, _start, end) in result}
    assert by_id[1] is None
    assert by_id[2] == 70


def test_parse_keyframes_non_overlap_returns_sentinel_frame():
    kps = [MockKP(10, 1), MockKP(50, -1), MockKP(60, 2), MockKP(100, -1)]
    result = _parse_keyframes(kps)
    by_id = {eid: end for (eid, _start, end) in result}
    assert by_id[1] == 50
    assert by_id[2] == 100


def test_parse_keyframes_trailing_line_returns_none():
    kps = [MockKP(10, 1)]
    result = _parse_keyframes(kps)
    assert result == [(1, 10, None)]
