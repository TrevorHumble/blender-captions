"""Captions add-on for Blender 4.x.

Quick-and-dirty dialogue captions for animatics. One Text object displays
all lines; timing is keyframed and draggable in the dopesheet. Callable
headless via bpy.ops.captions.* for AI / MCP workflows.
"""
bl_info = {
    "name": "Captions",
    "author": "Trevor Humble",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > N-panel > Captions",
    "description": "Quick dialogue captions for animatics. One text object, draggable timing.",
    "category": "Animation",
}

import bpy

from . import api_docs, handlers, operators, props, ui

_MODULES = (props, operators, ui, handlers)


def _upsert_readme():
    name = "CAPTIONS_README"
    readme = bpy.data.texts.get(name)
    if readme is None:
        readme = bpy.data.texts.new(name)
        readme.write(api_docs.CAPTIONS_README)


def register():
    for m in _MODULES:
        m.register()
    _upsert_readme()
    print("Captions addon ready. Run bpy.ops.captions.print_api() for usage.")


def unregister():
    for m in reversed(_MODULES):
        m.unregister()
