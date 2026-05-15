"""Captions add-on for Blender 4.x.

Quick-and-dirty dialogue captions for animatics. One Text object displays
all lines; timing is keyframed and draggable in the dopesheet. Callable
headless via bpy.ops.captions.* for AI / MCP workflows.
"""
bl_info = {
    "name": "Captions",
    "author": "Trevor Humble",
    "version": (0, 1, 4),
    "blender": (4, 2, 0),
    "location": "View3D > N-panel > Captions",
    "description": "Quick dialogue captions for animatics. One text object, draggable timing.",
    "category": "Animation",
}

import bpy

from . import api_docs, handlers, operators, props, ui

_MODULES = (props, operators, ui, handlers)


def _upsert_readme():
    """Write the API reference into a Text datablock.

    Blender restricts bpy.data access during register() at install time --
    accessing bpy.data.texts raises AttributeError on a _RestrictData proxy.
    Deferring via a timer runs this after register completes when data is
    available.
    """
    if not hasattr(bpy.data, "texts"):
        return 0.1  # bpy.data still restricted; retry shortly
    name = "CAPTIONS_README"
    readme = bpy.data.texts.get(name)
    if readme is None:
        readme = bpy.data.texts.new(name)
        readme.write(api_docs.CAPTIONS_README)
    return None  # done -- unregister the timer


def register():
    for m in _MODULES:
        m.register()
    bpy.app.timers.register(_upsert_readme, first_interval=0.1)
    print("Captions addon ready. Run bpy.ops.captions.print_api() for usage.")


def unregister():
    for m in reversed(_MODULES):
        m.unregister()
