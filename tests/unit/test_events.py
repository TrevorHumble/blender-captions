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
pick_insertion_frame = _events.pick_insertion_frame


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


# ---------------------------------------------------------------------------
# pick_insertion_frame -- smart placement for add_line (issue #13)
# ---------------------------------------------------------------------------


def test_pick_insertion_empty_returns_frame_current():
    """Rule 1: empty list -> use the playhead, clamped to 0."""
    assert pick_insertion_frame([], -1, 100, 48, 12) == 100
    assert pick_insertion_frame([], 0, 1, 48, 12) == 1


def test_pick_insertion_empty_with_negative_playhead_clamps_to_zero():
    """AC8: never return a negative start frame."""
    assert pick_insertion_frame([], -1, -50, 48, 12) == 0


def test_pick_insertion_no_active_playhead_in_clear_zone_uses_playhead():
    """Rule 3: with no selection and a clean playhead, honor the playhead."""
    lines = [L(1, 200, 250)]
    # Playhead at 50, line is at 200-250 -- window [50, 98] padded by 12 = [38, 110].
    # 110 < 200 - 12 = 188, so it's clear.
    assert pick_insertion_frame(lines, -1, 50, 48, 12) == 50


def test_pick_insertion_no_active_playhead_inside_line_appends_to_tail():
    """Rule 4: playhead is mid-line, no selection -> append at tail."""
    lines = [L(1, 10, 100)]
    # Playhead at 50 is inside (10, 100). Rule 3 fails, Rule 4 fires.
    # Tail = max_end (100) + gap (12) = 112.
    assert pick_insertion_frame(lines, -1, 50, 48, 12) == 112


def test_pick_insertion_with_active_chains_after_active():
    """AC2: selected line at [10,50], gap=12, dur=48 -> new line at 62."""
    lines = [L(1, 10, 50)]
    assert pick_insertion_frame(lines, 0, 999, 48, 12) == 62


def test_pick_insertion_with_active_walks_past_blocking_next_line():
    """AC3: active [10,50] + blocking [62,150], gap=12, dur=48 -> 162.

    Probe at 62 hits (62, 150). Skip to 150+12=162. Probe [162, 210]
    against the same range -- 162 >= 150 so clear.
    """
    lines = [L(1, 10, 50), L(2, 62, 150)]
    assert pick_insertion_frame(lines, 0, 0, 48, 12) == 162


def test_pick_insertion_gap_zero_chains_back_to_back():
    """AC5: gap=0 -> abutting lines stack at active.end."""
    lines = [L(1, 10, 50)]
    # With gap=0 and half-open semantics, frame 50 is FREE. Probe at 50 clear.
    assert pick_insertion_frame(lines, 0, 0, 20, 0) == 50


def test_pick_insertion_with_legacy_duplicate_starts_handled_safely():
    """Pre-existing data may have duplicate start frames (a legacy bug).
    The smart placement must not loop or crash on duplicates.
    """
    lines = [L(1, 100, 148), L(2, 100, 148)]
    # Active is index 0. after = 148 + 12 = 160. Probe at 160 clear of both
    # ranges (160 >= 148 for both).
    assert pick_insertion_frame(lines, 0, 0, 48, 12) == 160


def test_pick_insertion_negative_playhead_with_active_still_uses_active():
    """AC8 across Rule 2: negative playhead must not poison the active-line
    chaining path. Rule 2 ignores frame_current entirely.
    """
    lines = [L(1, 10, 50)]
    assert pick_insertion_frame(lines, 0, -500, 48, 12) == 62


def test_pick_insertion_negative_playhead_no_active_does_not_overlap():
    """AC8 + 'never overlap' regression. With a wildly negative playhead
    and no selection, the algorithm must not place a new line at 0 if doing
    so would overlap an existing line near the start of the timeline.
    """
    # Existing line at (5, 100). frame_current=-1000.
    # Rule 3: clamp playhead to 0 BEFORE fit-check. _fits(ranges, 0, 48, 12)
    # has window [-12, 60] vs (5, 100) -> 60 > 5 and -12 < 100 -> blocked.
    # Falls to Rule 4: max_end (100) + gap (12) = 112.
    result = pick_insertion_frame([L(1, 5, 100)], -1, -1000, 48, 12)
    assert result == 112


def test_pick_insertion_negative_playhead_no_active_with_clear_zone_clamps():
    """AC8 + Rule 3 happy path: negative playhead, no overlap risk near 0.
    Clamp to 0 and use 0 as the start.
    """
    # Line at (500, 600), playhead at -100. Padded window from 0 is [-12, 60]
    # vs (500, 600) -> clear. Returns 0.
    result = pick_insertion_frame([L(1, 500, 600)], -1, -100, 48, 12)
    assert result == 0


def test_find_open_slot_half_open_at_boundary_returns_end():
    """AC9 explicit: frame == range.end is FREE. _find_open_slot must return
    the boundary frame without skipping past it.
    """
    find_open_slot = _events._find_open_slot
    assert find_open_slot([(10, 50)], 50, 48, 0) == 50


def test_pick_insertion_no_active_duplicates_tail_append_safe():
    """Duplicate-start data must work on the tail-append path too, not just
    the active-line path.
    """
    # Two duplicate ranges, no active, playhead inside one of them.
    # Falls to Rule 4: max_end = 148, after = 148 + 12 = 160.
    lines = [L(1, 100, 148), L(2, 100, 148)]
    assert pick_insertion_frame(lines, -1, 120, 48, 12) == 160
