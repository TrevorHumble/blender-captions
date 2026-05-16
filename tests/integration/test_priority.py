"""The five highest-priority Blender integration tests.

These cover the regression risks the opus agent and I both flagged as the
most important to pin: F-curve round-trip, frame_change_pre body update,
overlap policy (issue #9), orphaned-master recovery (v0.1.6 fix), and
keyframe-type consistency.
"""
from __future__ import annotations

import json

import bpy

from captions_tool import master, timeline
from captions_tool.events import NO_CAPTION


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lines():
    return bpy.context.scene.captions.lines


def _import(dialogue):
    bpy.ops.captions.bulk_import(json_data=json.dumps(dialogue))


def _body_at(frame):
    bpy.context.scene.frame_set(frame)
    return bpy.context.scene.captions.master_object.data.body


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_bulk_import_round_trip():
    """timeline.read() returns the lines we wrote via bulk_import."""
    _import([
        {"text": "Hi",      "start": 1,  "end": 30},
        {"text": "Hello",   "start": 50, "end": 80},
    ])
    m = bpy.context.scene.captions.master_object
    entries = timeline.read(m)
    # entries is [(id, start, end), ...] -- ids are assigned 1..N
    starts_ends = sorted([(s, e) for (_id, s, e) in entries])
    assert starts_ends == [(1, 30), (50, 80)], f"got {starts_ends}"


def test_frame_change_pre_updates_body():
    """Scrubbing the timeline writes the active line's text into master.data.body."""
    _import([
        {"text": "FIRST",  "start": 10, "end": 30},
        {"text": "SECOND", "start": 50, "end": 70},
    ])
    assert _body_at(5)  == "",       f"pre-start body should be empty, got {_body_at(5)!r}"
    assert _body_at(20) == "FIRST",  f"mid-first should be FIRST, got {_body_at(20)!r}"
    assert _body_at(40) == "",       f"gap should be empty, got {_body_at(40)!r}"
    assert _body_at(60) == "SECOND", f"mid-second should be SECOND, got {_body_at(60)!r}"
    assert _body_at(80) == "",       f"post-end should be empty, got {_body_at(80)!r}"


def test_overlap_later_start_wins():
    """Issue #9 regression: when ranges overlap, the later-starting line wins
    and the earlier line's end-sentinel must not cut it off.
    """
    _import([
        {"text": "FIRST",  "start": 10, "end": 50},
        {"text": "SECOND", "start": 30, "end": 70},
    ])
    assert _body_at(20) == "FIRST",  f"got {_body_at(20)!r}"
    assert _body_at(40) == "SECOND", f"got {_body_at(40)!r}"
    assert _body_at(60) == "SECOND", f"frame 60 must stay on SECOND, got {_body_at(60)!r}"
    assert _body_at(80) == "",       f"got {_body_at(80)!r}"


def test_orphaned_master_recovery():
    """v0.1.6 fix: if the master gets unlinked from every scene (e.g. user
    deletes from outliner), select_master and create both re-link it.
    """
    _import([{"text": "X", "start": 5, "end": 15}])
    scene = bpy.context.scene
    m = scene.captions.master_object
    assert m is not None

    # Simulate the outliner delete: unlink from every collection it's in,
    # but keep the PointerProperty referring to it.
    for col in list(m.users_collection):
        col.objects.unlink(m)
    assert scene not in m.users_scene, "test setup failed: master still in scene"

    # select_master should re-link and select.
    result = bpy.ops.captions.select_master()
    assert result == {'FINISHED'}, f"select_master returned {result}"
    assert scene in m.users_scene, "master not re-linked to scene"
    assert bpy.context.view_layer.objects.active is m, "master not made active"


def test_keyframes_use_constant_breakdown():
    """Every keyframe written by timeline.write must be CONSTANT interpolation
    + BREAKDOWN type (the small distinct diamond chosen in v0.1.5).
    """
    _import([
        {"text": "A", "start": 1,  "end": 30},
        {"text": "B", "start": 50, "end": 80},
    ])
    m = bpy.context.scene.captions.master_object
    found_any = False
    for _container, fc in timeline._iter_fcurves(m.animation_data.action):
        if fc.data_path != '["caption_idx"]':
            continue
        for kp in fc.keyframe_points:
            found_any = True
            assert kp.interpolation == 'CONSTANT', f"frame {kp.co.x} has interp={kp.interpolation}"
            assert kp.type == 'BREAKDOWN', f"frame {kp.co.x} has type={kp.type}"
    assert found_any, "no caption_idx F-curve found"


# ---------------------------------------------------------------------------
# Smart placement for Add Line (issue #13)
# ---------------------------------------------------------------------------


def test_add_line_three_rapid_clicks_chain_non_overlapping():
    """AC7: three rapid + clicks with a selected line at [10,50] produce
    three new lines chained forward with default_duration spacing and
    gap_frames between them. None of the four lines overlap.
    """
    # Seed one line at [10, 50] and select it.
    _import([{"text": "FIRST", "start": 10, "end": 50}])
    caps = bpy.context.scene.captions
    caps.active_index = 0
    gap = caps.gap_frames
    dur = caps.default_duration

    bpy.ops.captions.add_line(text="A")  # all defaults: start=-1, end=-1
    bpy.ops.captions.add_line(text="B")
    bpy.ops.captions.add_line(text="C")

    assert len(caps.lines) == 4
    # The new lines were appended in collection order, with active_index moving
    # to each new one. By chaining off the prior active line:
    #   A: start = 50 + gap, end = start + dur
    #   B: start = A.end + gap
    #   C: start = B.end + gap
    starts = [line.start for line in caps.lines]
    ends = [line.end for line in caps.lines]
    assert starts[0] == 10 and ends[0] == 50
    assert starts[1] == 50 + gap and ends[1] == starts[1] + dur
    assert starts[2] == starts[1] + dur + gap and ends[2] == starts[2] + dur
    assert starts[3] == starts[2] + dur + gap and ends[3] == starts[3] + dur
    # No overlap between any pair.
    for i in range(len(caps.lines)):
        for j in range(i + 1, len(caps.lines)):
            assert ends[i] <= starts[j] or ends[j] <= starts[i], (
                f"lines {i} [{starts[i]}-{ends[i]}] and {j} [{starts[j]}-{ends[j]}] overlap"
            )


def test_add_line_explicit_start_bypasses_smart_placement():
    """AC6: passing start=N (N >= 0) explicitly always uses N, even if a
    line is active that would otherwise anchor the smart logic.
    """
    _import([{"text": "FIRST", "start": 10, "end": 50}])
    bpy.context.scene.captions.active_index = 0

    bpy.ops.captions.add_line(text="EXACT", start=999, end=1099)
    new_line = bpy.context.scene.captions.lines[-1]
    assert new_line.start == 999
    assert new_line.end == 1099


def test_add_line_no_active_uses_playhead_in_clear_zone():
    """AC4 inverse: no active line, playhead is in a clear zone -> honor
    the playhead. (When playhead is INSIDE a line, the addon falls back
    to append-at-tail; this test pins the clear-zone branch.)
    """
    _import([{"text": "FAR", "start": 500, "end": 600}])
    caps = bpy.context.scene.captions
    # Deselect by pointing active_index out of range.
    caps.active_index = len(caps.lines)  # invalid -> Rule 3 / Rule 4

    bpy.context.scene.frame_set(50)
    bpy.ops.captions.add_line(text="USING_PLAYHEAD")
    new_line = caps.lines[-1]
    # frame_current=50 with dur=default_duration (48) and gap=12 padding.
    # Padded window [38, 110] vs (500, 600): clear. Rule 3 hits, returns 50.
    assert new_line.start == 50


# ---------------------------------------------------------------------------
# Slip all lines (issue #3)
# ---------------------------------------------------------------------------


def test_slip_shifts_all_lines_forward():
    _import([
        {"text": "A", "start": 10, "end": 50},
        {"text": "B", "start": 60, "end": 100},
    ])
    result = bpy.ops.captions.slip(frames=20)
    assert result == {'FINISHED'}
    lines = bpy.context.scene.captions.lines
    assert (lines[0].start, lines[0].end) == (30, 70)
    assert (lines[1].start, lines[1].end) == (80, 120)


def test_slip_negative_clamp_preserves_relative_timing():
    """A negative slip larger than the earliest start frame must clamp the
    whole batch so lines don't pile up at 0.
    """
    _import([
        {"text": "A", "start": 5,  "end": 50},
        {"text": "B", "start": 20, "end": 60},
    ])
    result = bpy.ops.captions.slip(frames=-100)
    assert result == {'FINISHED'}
    lines = bpy.context.scene.captions.lines
    # Effective shift: -5 (clamped). A: 5-5=0. B: 20-5=15.
    assert (lines[0].start, lines[0].end) == (0, 45)
    assert (lines[1].start, lines[1].end) == (15, 55)
    # Relative spacing preserved.
    assert lines[1].start - lines[0].start == 15


def test_slip_zero_is_no_op():
    """Slip(0) returns CANCELLED rather than rebuilding the F-curve."""
    _import([{"text": "A", "start": 10, "end": 50}])
    result = bpy.ops.captions.slip(frames=0)
    assert result == {'CANCELLED'}
    line = bpy.context.scene.captions.lines[0]
    assert (line.start, line.end) == (10, 50)


def test_slip_on_empty_collection_returns_cancelled():
    """No lines to slip -> cancel cleanly, don't crash."""
    # Don't import anything.
    result = bpy.ops.captions.slip(frames=10)
    assert result == {'CANCELLED'}


# ---------------------------------------------------------------------------
# move_line UP/DOWN (v0.1.3 behavior, previously had zero coverage)
# ---------------------------------------------------------------------------


def test_move_line_up_swaps_timing_with_chronological_neighbor():
    """Pressing UP swaps the active line's timing with the line directly
    above it in the chronologically-sorted display. Text content stays in
    its original collection slot; only the start/end frames move.
    """
    _import([
        {"text": "FIRST",  "start": 10, "end": 30},
        {"text": "SECOND", "start": 50, "end": 70},
    ])
    caps = bpy.context.scene.captions
    caps.active_index = 1  # SECOND

    result = bpy.ops.captions.move_line(direction='UP')
    assert result == {'FINISHED'}

    # Text remains in collection order; timing swapped.
    assert caps.lines[0].text == "FIRST"
    assert caps.lines[1].text == "SECOND"
    assert (caps.lines[0].start, caps.lines[0].end) == (50, 70)
    assert (caps.lines[1].start, caps.lines[1].end) == (10, 30)


def test_move_line_down_swaps_timing_with_chronological_neighbor():
    """Symmetric to UP -- pressing DOWN on the first chronological line
    swaps it later.
    """
    _import([
        {"text": "FIRST",  "start": 10, "end": 30},
        {"text": "SECOND", "start": 50, "end": 70},
    ])
    caps = bpy.context.scene.captions
    caps.active_index = 0  # FIRST

    bpy.ops.captions.move_line(direction='DOWN')

    assert caps.lines[0].text == "FIRST"
    assert (caps.lines[0].start, caps.lines[0].end) == (50, 70)
    assert caps.lines[1].text == "SECOND"
    assert (caps.lines[1].start, caps.lines[1].end) == (10, 30)


def test_move_line_at_extremes_returns_cancelled():
    """UP at the top of the chronological list, and DOWN at the bottom,
    both return CANCELLED without mutating data.
    """
    _import([
        {"text": "A", "start": 10, "end": 30},
        {"text": "B", "start": 50, "end": 70},
    ])
    caps = bpy.context.scene.captions

    caps.active_index = 0  # chronologically first
    assert bpy.ops.captions.move_line(direction='UP') == {'CANCELLED'}
    assert (caps.lines[0].start, caps.lines[0].end) == (10, 30)

    caps.active_index = 1  # chronologically last
    assert bpy.ops.captions.move_line(direction='DOWN') == {'CANCELLED'}
    assert (caps.lines[1].start, caps.lines[1].end) == (50, 70)


# ---------------------------------------------------------------------------
# Issue #12 regression: rapid clicks with varied selection produce uniques
# ---------------------------------------------------------------------------


def test_add_line_five_clicks_varied_selection_produces_unique_starts():
    """Cycle through three existing lines, clicking + on each. All six
    resulting lines have unique start frames, and no two lines overlap.
    The original screenshot bug (lines piling at the same start frame)
    must not return.
    """
    _import([
        {"text": "A", "start": 10,  "end": 50},
        {"text": "B", "start": 100, "end": 140},
        {"text": "C", "start": 200, "end": 240},
    ])
    caps = bpy.context.scene.captions

    for i in range(3):
        caps.active_index = i
        bpy.ops.captions.add_line(text=f"NEW{i}")

    starts = [line.start for line in caps.lines]
    assert len(starts) == 6
    assert len(set(starts)) == 6, f"duplicate starts: {starts}"

    # Sort by start and verify no overlap.
    sorted_ranges = sorted((line.start, line.end) for line in caps.lines)
    for prev, nxt in zip(sorted_ranges, sorted_ranges[1:]):
        assert nxt[0] >= prev[1], f"overlap between {prev} and {nxt}"


# ---------------------------------------------------------------------------
# gap_frames update callback
# ---------------------------------------------------------------------------


def test_gap_frames_change_rebuilds_fcurve():
    """Setting scene.captions.gap_frames invokes the update callback which
    rebuilds the F-curve. The sentinel between two abutting lines should
    shift to reflect the new gap.
    """
    _import([
        {"text": "A", "start": 10, "end": 50},
        {"text": "B", "start": 50, "end": 90},
    ])
    scene = bpy.context.scene
    m = scene.captions.master_object

    def sentinels_between_a_and_b():
        """Return -1 sentinel frames inside (10, 50)."""
        frames = []
        if m.animation_data and m.animation_data.action:
            for _container, fc in timeline._iter_fcurves(m.animation_data.action):
                if fc.data_path != '["caption_idx"]':
                    continue
                for kp in fc.keyframe_points:
                    f = int(round(kp.co.x))
                    v = int(round(kp.co.y))
                    if v == -1 and 10 < f < 50:
                        frames.append(f)
        return frames

    scene.captions.gap_frames = 12
    assert 38 in sentinels_between_a_and_b(), (
        f"with gap=12, expected sentinel at 38, got {sentinels_between_a_and_b()}"
    )

    scene.captions.gap_frames = 24
    assert 26 in sentinels_between_a_and_b(), (
        f"with gap=24, expected sentinel at 26, got {sentinels_between_a_and_b()}"
    )

    scene.captions.gap_frames = 12  # restore default


# ---------------------------------------------------------------------------
# set_active_frame robustness
# ---------------------------------------------------------------------------


def test_set_active_frame_with_invalid_active_index_returns_cancelled():
    """If active_index points outside the collection (e.g. -1 or past end),
    set_active_frame must return CANCELLED cleanly, not crash.
    """
    _import([{"text": "A", "start": 10, "end": 30}])
    caps = bpy.context.scene.captions

    caps.active_index = 99
    assert bpy.ops.captions.set_active_frame(which='START') == {'CANCELLED'}

    caps.active_index = -1
    assert bpy.ops.captions.set_active_frame(which='END') == {'CANCELLED'}
