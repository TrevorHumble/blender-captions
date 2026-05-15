"""Tier 2 unit tests for captions_tool.events.compute_events.

Pure-Python, no Blender required. Run from the repo root:

    pytest tests/unit
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path

# Load captions_tool/events.py directly. Importing via the package would
# trigger captions_tool/__init__.py which pulls in bpy.
_EVENTS_PATH = Path(__file__).resolve().parent.parent.parent / "captions_tool" / "events.py"
_spec = importlib.util.spec_from_file_location("captions_events_under_test", _EVENTS_PATH)
_events = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_events)
compute_events = _events.compute_events
NO_CAPTION = _events.NO_CAPTION


@dataclass
class L:
    """Stand-in for CaptionLine PropertyGroup. compute_events only reads
    .id, .start, .end so a plain dataclass is enough."""
    id: int
    start: int
    end: int


def test_empty_list_returns_empty():
    assert compute_events([]) == []


def test_single_line_has_leading_sentinel_start_and_end():
    events = compute_events([L(id=7, start=10, end=50)])
    assert events == [(9, NO_CAPTION), (10, 7), (50, NO_CAPTION)]


def test_first_start_at_frame_zero_emits_negative_leading_sentinel():
    events = compute_events([L(id=1, start=0, end=10)])
    assert events[0] == (-1, NO_CAPTION)


def test_two_non_overlapping_lines_each_get_their_own_sentinel():
    events = compute_events([L(1, 10, 30), L(2, 50, 70)])
    assert events == [
        (9,  NO_CAPTION),  # leading
        (10, 1),
        (30, NO_CAPTION),  # end of line 1
        (50, 2),
        (70, NO_CAPTION),  # end of line 2
    ]


def test_abutting_lines_no_gap_no_sentinel_at_shared_frame():
    """When L1.end == L2.start and gap_frames=0, the line-start wins."""
    events = compute_events([L(1, 10, 30), L(2, 30, 50)], gap_frames=0)
    assert events == [
        (9,  NO_CAPTION),
        (10, 1),
        (30, 2),           # L2 starts here, no sentinel
        (50, NO_CAPTION),
    ]


def test_abutting_lines_with_gap_inserts_blank_before_next():
    """gap_frames=5 should pull the prior line's end-sentinel 5 frames earlier."""
    events = compute_events([L(1, 10, 30), L(2, 30, 50)], gap_frames=5)
    assert events == [
        (9,  NO_CAPTION),
        (10, 1),
        (25, NO_CAPTION),  # L1's end-sentinel pulled to 30 - 5 = 25
        (30, 2),
        (50, NO_CAPTION),
    ]


def test_overlap_later_start_wins_no_premature_end_sentinel():
    """Issue #9 regression. L1: 10-50 covered by L2: 30-70.
    L1's end-sentinel must NOT appear -- L2 still in progress at frame 50."""
    events = compute_events([L(1, 10, 50), L(2, 30, 70)])
    assert events == [
        (9,  NO_CAPTION),
        (10, 1),
        (30, 2),
        (70, NO_CAPTION),  # only L2's end, not L1's
    ]


def test_triple_overlap_chain():
    """A:10-50, B:30-70, C:60-90 -- only C's end-sentinel survives."""
    events = compute_events([L(1, 10, 50), L(2, 30, 70), L(3, 60, 90)])
    assert events == [
        (9,  NO_CAPTION),
        (10, 1),
        (30, 2),
        (60, 3),
        (90, NO_CAPTION),
    ]


def test_input_order_does_not_matter():
    """compute_events sorts internally; calling with reversed input is identical."""
    forward  = compute_events([L(1, 10, 30), L(2, 50, 70)])
    reversed_ = compute_events([L(2, 50, 70), L(1, 10, 30)])
    assert forward == reversed_


def test_gap_frames_only_applies_at_abutting_frames():
    """A gap_frames=5 setting should NOT affect lines with a natural gap."""
    # L1 ends at 30, L2 starts at 50 -- not abutting, no shift needed.
    events = compute_events([L(1, 10, 30), L(2, 50, 70)], gap_frames=5)
    assert events == [
        (9,  NO_CAPTION),
        (10, 1),
        (30, NO_CAPTION),
        (50, 2),
        (70, NO_CAPTION),
    ]


def test_unique_ids_only():
    """Each line.id should appear exactly once in the events as a positive value."""
    events = compute_events([L(101, 10, 30), L(202, 40, 60), L(303, 70, 90)])
    positive_values = [v for _, v in events if v >= 0]
    assert positive_values == [101, 202, 303]


def test_events_are_sorted_by_frame():
    events = compute_events([L(3, 100, 120), L(1, 10, 30), L(2, 50, 70)])
    frames = [f for f, _ in events]
    assert frames == sorted(frames)


def test_leading_sentinel_is_one_frame_before_earliest_start():
    """Even when input order is reversed, the leading sentinel sits one frame
    before the chronologically-first line."""
    events = compute_events([L(2, 200, 210), L(1, 50, 60)])
    assert events[0] == (49, NO_CAPTION)
