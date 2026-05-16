"""Pure Python keyframe-event generation.

Extracted from timeline.py so the encoding rules can be unit-tested without
Blender. `compute_events` takes any iterable of objects exposing `.id`,
`.start`, `.end` (typically CaptionLine PropertyGroups, but plain dataclasses
work too) and returns a sorted list of (frame, value) keyframe events ready
to feed to keyframe_insert.
"""
from __future__ import annotations

NO_CAPTION = -1


def compute_events(lines, gap_frames: int = 0):
    """Compute (frame, value) keyframe events from a list of caption lines.

    Each line contributes a start keyframe (frame=line.start, value=line.id).
    A NO_CAPTION (-1) end-sentinel is added at line.end ONLY if no other line
    is in progress at that frame -- otherwise the still-active line would be
    cut off.

    `gap_frames`: when a line ends at exactly the frame another line starts,
    shift the end-sentinel earlier by this many frames so the screen briefly
    blanks out before the next line. 0 = no gap (lines run continuously).

    Overlap policy: 'later start wins' -- the line whose start frame is most
    recently passed takes the screen.

    Returns a list of (frame, value) tuples sorted by frame. Frame numbers
    are ints. Always includes a leading sentinel at (first_start - 1) so
    Blender's constant-extrapolation doesn't bleed the first line backward
    to negative infinity.

    Empty input returns an empty list.
    """
    if not lines:
        return []

    by_frame: dict[int, int] = {}
    sorted_lines = sorted(lines, key=lambda l: l.start)
    starts_set = {l.start for l in sorted_lines}

    # Leading sentinel: blank before the first line starts.
    first_start = sorted_lines[0].start
    by_frame[first_start - 1] = NO_CAPTION

    # Line-start events.
    for line in sorted_lines:
        by_frame[line.start] = line.id

    # End sentinels with overlap/gap handling.
    for line in sorted_lines:
        sentinel_frame = line.end
        if gap_frames > 0 and line.end in starts_set:
            sentinel_frame = line.end - gap_frames

        if sentinel_frame in by_frame:
            # Another event already claims this frame; line-starts win.
            continue

        # Skip if another line is in-progress at the sentinel frame (overlap).
        # Using sentinel_frame rather than line.end matters when gap_frames
        # shifted the sentinel earlier: the next line might not have started
        # yet at the shifted frame, so the gap is legal.
        covering = any(
            other is not line and other.start <= sentinel_frame < other.end
            for other in sorted_lines
        )
        if covering:
            continue

        by_frame[sentinel_frame] = NO_CAPTION

    return sorted(by_frame.items())


def pick_insertion_frame(lines, active_index, frame_current, duration, gap):
    """Decide a start frame for a new line. Returns an int >= 0.

    The decision tree:
      Rule 1: lines is empty -- return max(frame_current, 0).
      Rule 2: active_index is valid (0 <= active_index < len(lines)) --
              chain off the active line by returning the first open slot at or
              after active.end + gap.
      Rule 3: no active line and the window [frame_current, frame_current +
              duration] fits cleanly against all existing ranges with gap
              padding on both sides -- honor the playhead and return
              max(frame_current, 0).
      Rule 4: otherwise -- append at the tail by returning the first open
              slot at or after max(end for _, end in ranges) + gap.

    Existing lines are never shifted to make room. When the natural slot is
    blocked, the slot-finder walks forward through the occupied ranges until
    a clear window opens. The returned frame is always clamped to >= 0.
    """
    if not lines:
        return max(int(frame_current), 0)

    ranges = _occupied_ranges(lines)

    if 0 <= active_index < len(lines):
        active = lines[active_index]
        return max(_find_open_slot(ranges, active.end + gap, duration, gap), 0)

    # Clamp the playhead to >= 0 BEFORE checking fit. Otherwise a wildly
    # negative frame_current can pass _fits (the padded window misses positive
    # ranges entirely) and return 0, which may overlap an existing line.
    clamped = max(int(frame_current), 0)
    if _fits(ranges, clamped, duration, gap):
        return clamped

    max_end = max(end for _, end in ranges)
    return max(_find_open_slot(ranges, max_end + gap, duration, gap), 0)


def shift_line_timings(lines, frames):
    """Compute the (start, end) pairs for every line after shifting by `frames`.

    Returns `(effective_frames, [(new_start, new_end), ...])`. Negative
    shifts that would push any line below frame 0 are clamped: the effective
    shift becomes `-min(starts)`, so the entire batch moves by the largest
    safe amount. Relative timing between lines is always preserved (lines
    never pile up at 0 from clamping).

    Pure function. Caller is responsible for applying the new timings to
    Blender's CollectionProperty.
    """
    if not lines:
        return frames, []
    if frames < 0:
        earliest_start = min(int(l.start) for l in lines)
        frames = max(frames, -earliest_start)
    new_pairs = [(int(l.start) + frames, int(l.end) + frames) for l in lines]
    return frames, new_pairs


def _occupied_ranges(lines):
    """Sorted [(start, end), ...] tuples from any iterable with .start/.end.

    Duplicates are preserved (legacy data may have multiple lines with the
    same start frame). Sort key is start; ties broken by end.
    """
    return sorted((int(l.start), int(l.end)) for l in lines)


def _find_open_slot(ranges, after, duration, gap):
    """First frame >= `after` where the window [frame, frame + duration] does
    not overlap any range in `ranges`, allowing `gap` frames of padding on
    both sides.

    Collision predicate: a range (s, e) blocks the candidate window iff
    `frame < e AND frame + duration > s` (strict half-open -- frame == e is
    free, matching the sentinel-at-line.end convention used elsewhere).
    When blocked by (s, e), the next probe is e + gap.

    Walks forward through `ranges` until an open slot is found. Always
    returns a valid frame, never raises, never None. With no ranges the
    function returns `after` unchanged.
    """
    candidate = int(after)
    while True:
        blocker = _blocking_range(ranges, candidate, duration, gap)
        if blocker is None:
            return candidate
        # A blocker (s, e) must have e + gap > candidate (otherwise the padded
        # window couldn't have reached it), so the next probe always advances.
        _, blocker_end = blocker
        candidate = blocker_end + gap


def _blocking_range(ranges, frame, duration, gap):
    """Return the first range that overlaps the padded candidate window, or
    None if the window is clear. Used by `_find_open_slot`.
    """
    window_start = frame - gap
    window_end = frame + duration + gap
    for s, e in ranges:
        if window_start < e and window_end > s:
            return (s, e)
    return None


def _fits(ranges, frame, duration, gap):
    """True if [frame, frame + duration] (padded by `gap` on both sides) fits
    against `ranges` without collision. Thin wrapper used by Rule 3 of
    `pick_insertion_frame`.
    """
    return _blocking_range(ranges, int(frame), int(duration), int(gap)) is None
