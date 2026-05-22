"""App handlers that bridge timeline state to the live scene.

Three handlers:
  - frame_change_pre: writes the active line's text into the master body.
  - depsgraph_update_post: when the user drags keyframes in the dopesheet,
    reads them back into the PropertyGroup so the panel stays in sync.
  - load_post: re-attaches handlers after a .blend reopen.

A module-level _writing flag suppresses the drag-sync handler while operators
are programmatically rebuilding the F-curve, so writes don't echo back.
"""
import bpy
from bpy.app.handlers import persistent

from . import master, timeline

_writing = False


def begin_write():
    global _writing
    _writing = True


def end_write():
    global _writing
    _writing = False


@persistent
def on_frame_change(scene):
    for s in bpy.data.scenes:
        m = master.get(s)
        if m is None:
            continue
        line_id = timeline.active_line_id(m, s.frame_current)
        if line_id is None:
            m.data.body = ""
            continue
        for line in s.captions.lines:
            if line.id == line_id:
                m.data.body = line.text
                break
        else:
            m.data.body = ""


@persistent
def on_depsgraph_update(scene, depsgraph):
    if _writing:
        return
    m = master.get(scene)
    if m is None:
        return

    action_id = m.animation_data.action if m.animation_data else None
    relevant = False
    for u in depsgraph.updates:
        orig = getattr(u.id, "original", u.id)
        if orig == m or (action_id is not None and orig == action_id):
            relevant = True
            break
    if not relevant:
        return

    entries = timeline.read(m)
    by_id = {eid: (s, e) for (eid, s, e) in entries}
    begin_write()
    try:
        for line in scene.captions.lines:
            if line.id in by_id:
                s, e = by_id[line.id]
                if line.start != s:
                    line.start = s
                if e is not None and line.end != e:
                    line.end = e
    finally:
        end_write()


@persistent
def on_load_post(_):
    _attach()


def _attach():
    pairs = (
        (bpy.app.handlers.frame_change_pre, on_frame_change),
        (bpy.app.handlers.depsgraph_update_post, on_depsgraph_update),
        (bpy.app.handlers.load_post, on_load_post),
    )
    for handler_list, fn in pairs:
        if fn not in handler_list:
            handler_list.append(fn)


def _detach():
    pairs = (
        (bpy.app.handlers.frame_change_pre, on_frame_change),
        (bpy.app.handlers.depsgraph_update_post, on_depsgraph_update),
        (bpy.app.handlers.load_post, on_load_post),
    )
    for handler_list, fn in pairs:
        if fn in handler_list:
            handler_list.remove(fn)


def register():
    _attach()


def unregister():
    _detach()
