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
