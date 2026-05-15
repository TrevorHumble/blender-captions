"""Captions timeline: which line plays at which frame.

This module is the only place that knows how timing is encoded in Blender.
Callers see three operations -- write, read, active_line_id -- and never touch
the custom property or F-curve directly.

Encoding:
  - INT custom property "caption_idx" on the master Text object.
  - Each line contributes ONE keyframe at (line.start, line.id) with CONSTANT
    interpolation. A "-1" sentinel keyframe is inserted at line.end when no
    other line starts at that frame, so the caption clears when nothing else
    takes over.
  - Lines are addressed by stable `id`, not by collection position.
"""
import bpy

from .events import compute_events, NO_CAPTION as _NONE

_PROP = "caption_idx"
_PATH = f'["{_PROP}"]'


def write(master_obj, lines, gap_frames=0):
    """Rebuild the F-curve to match `lines`. Idempotent.

    `gap_frames` inserts a blank-frame gap between adjacent dialogue lines
    where one line ends at exactly the frame another starts. 0 = no gap.
    """
    _ensure_prop(master_obj)
    _clear_fcurve(master_obj)

    if not lines:
        master_obj[_PROP] = _NONE
        return

    events = compute_events(lines, gap_frames)
    for frame, value in events:
        master_obj[_PROP] = value
        master_obj.keyframe_insert(data_path=_PATH, frame=frame)

    fc = _get_fcurve(master_obj)
    if fc is not None:
        for kp in fc.keyframe_points:
            kp.interpolation = 'CONSTANT'
            # BREAKDOWN renders as a small diamond, visually distinct from the
            # default yellow KEYFRAME. Recolor it via Preferences > Themes >
            # Dope Sheet > "Keyframe Breakdown" if you want a specific hue.
            kp.type = 'BREAKDOWN'
        fc.update()


def read(master_obj):
    """Return [(line_id, start, end), ...] derived from the F-curve.

    Each positive-valued keyframe is a line start. The line's effective end is
    the next keyframe in time order (whether sentinel or another line's start).
    """
    fc = _get_fcurve(master_obj)
    if fc is None:
        return []
    keys = sorted(
        ((int(round(kp.co.x)), int(round(kp.co.y))) for kp in fc.keyframe_points),
        key=lambda k: k[0],
    )
    result = []
    for i, (frame, value) in enumerate(keys):
        if value < 0:
            continue
        end = keys[i + 1][0] if i + 1 < len(keys) else frame
        result.append((value, frame, end))
    return result


def active_line_id(master_obj, frame):
    """Which line's id is showing at this frame? None if no caption."""
    fc = _get_fcurve(master_obj)
    if fc is None:
        return None
    value = int(round(fc.evaluate(frame)))
    return value if value >= 0 else None


# ---- internals --------------------------------------------------------------

def _ensure_prop(obj):
    if _PROP not in obj.keys():
        obj[_PROP] = _NONE
        obj.id_properties_ui(_PROP).update(min=_NONE)


def _iter_fcurves(action):
    """Yield all F-curves on `action`, supporting both legacy and layered Action APIs."""
    if hasattr(action, "layers") and len(action.layers) > 0:
        for layer in action.layers:
            for strip in layer.strips:
                for cb in getattr(strip, "channelbags", ()):
                    for fc in cb.fcurves:
                        yield cb, fc
    elif hasattr(action, "fcurves"):
        for fc in action.fcurves:
            yield action, fc


def _get_fcurve(obj):
    if obj.animation_data is None or obj.animation_data.action is None:
        return None
    for _container, fc in _iter_fcurves(obj.animation_data.action):
        if fc.data_path == _PATH:
            return fc
    return None


def _clear_fcurve(obj):
    if obj.animation_data is None or obj.animation_data.action is None:
        return
    action = obj.animation_data.action
    for container, fc in list(_iter_fcurves(action)):
        if fc.data_path == _PATH:
            container.fcurves.remove(fc)
            return
