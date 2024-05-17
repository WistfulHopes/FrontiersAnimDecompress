import bpy
from bpy.props import (BoolProperty, FloatProperty)

from .animation.anim_import import FrontiersAnimImport
from .animation.anim_export import FrontiersAnimExport
from .animation.batch_export import FrontiersAnimBatchExport

from .skeleton.skeleton_export import HedgehogSkeletonExport
from .skeleton.skeleton_import import HedgehogSkeletonImport

from .ui import side_panel


bl_info = {
    "name": "Sonic Frontiers Animation Tools",
    "author": "AdelQ, WistfulHopes, Turk645",
    "version": (2, 0, 0),
    "blender": (4, 1, 0),
    "location": "File > Import/Export",
    "description": "Animation and skeleton importer/exporter for Hedgehog Engine 2 games with compressed animations",
    # TODO: Update HedgeDocs for this tool
    # "doc_url": "https://hedgedocs.com/guides/hedgehog-engine/rangers/animation/import-export/",
    "tracker_url": "https://github.com/AdelQue/FrontiersAnimDecompress/issues/",
    "category": "Import-Export",
}


def register():
    # Import/Export
    bpy.utils.register_class(FrontiersAnimImport)
    bpy.utils.register_class(FrontiersAnimExport)
    bpy.utils.register_class(FrontiersAnimBatchExport)

    bpy.utils.register_class(HedgehogSkeletonImport)
    bpy.utils.register_class(HedgehogSkeletonExport)

    bpy.types.TOPBAR_MT_file_import.append(FrontiersAnimImport.menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(FrontiersAnimExport.menu_func_export)

    bpy.types.TOPBAR_MT_file_import.append(HedgehogSkeletonImport.menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(HedgehogSkeletonExport.menu_func_export)

    side_panel.register()

    # Needs to persist between restarts
    # Batch exports will hopelessly break if these don't load
    bpy.types.Action.pxd_export = BoolProperty(
        name="Export PXD Animation",
        description="Marks action for batch export",
        default=True,
    )
    bpy.types.Action.pxd_root = BoolProperty(
        name="Export PXD Root Motion",
        description="Enables root motion for batch export",
        default=True,
    )
    bpy.types.Action.pxd_fps = FloatProperty(
        name="PXD Frame Rate",
        description="FPS value to write to PXD Animation file",
        default=30.0,
    )


def unregister():
    # Import/Export
    bpy.utils.unregister_class(FrontiersAnimExport)
    bpy.utils.unregister_class(FrontiersAnimImport)
    bpy.utils.unregister_class(FrontiersAnimBatchExport)

    bpy.utils.unregister_class(HedgehogSkeletonImport)
    bpy.utils.unregister_class(HedgehogSkeletonExport)

    bpy.types.TOPBAR_MT_file_import.remove(FrontiersAnimImport.menu_func_import)
    bpy.types.TOPBAR_MT_file_export.remove(FrontiersAnimExport.menu_func_export)

    bpy.types.TOPBAR_MT_file_import.remove(HedgehogSkeletonImport.menu_func_import)
    bpy.types.TOPBAR_MT_file_export.remove(HedgehogSkeletonExport.menu_func_export)

    side_panel.unregister()


if __name__ == "__main__":
    register()
