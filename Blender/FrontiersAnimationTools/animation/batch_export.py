import bpy
import os
from bpy_extras.io_utils import ExportHelper
from bpy.props import (BoolProperty,
                       StringProperty,
                       CollectionProperty
                       )
from .anim_export import anim_export
from ..ui.func_ops import filter_actions


class FrontiersAnimBatchExport(bpy.types.Operator, ExportHelper):
    bl_idname = "export_anim.frontiers_anim_batch"
    bl_label = "Export"
    bl_description = "Batch exports compressed Sonic Frontiers animations"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ""

    filepath: StringProperty(subtype='FILE_PATH', )
    files: CollectionProperty(type=bpy.types.PropertyGroup)

    bool_yx_skel:   BoolProperty(
        name="Use YX Bone Orientation",
        description="Enable if your skeleton was reoriented for Blender's YX orientation instead of Frontiers' XZ",
        default=False,
    )

    def __init__(self):
        self.bool_root_motion = False

    def draw(self, context):
        layout = self.layout

        ui_bone_box = layout.box()
        ui_bone_box.label(text="Armature Settings", icon='ARMATURE_DATA')

        ui_orientation_row = ui_bone_box.row()
        ui_orientation_row.prop(self, "bool_yx_skel", )

    def execute(self, context):
        base_dir = os.path.dirname(self.filepath)
        arm_active = bpy.context.active_object
        scene_active = bpy.context.scene
        frame_active = scene_active.frame_current
        action_active = arm_active.animation_data.action
        filtered_actions = filter_actions(bpy.data.actions, context)

        print("Exporting PXD Animations...")
        num_anims = len(filtered_actions)
        status_len = 1
        for i, action in enumerate(filtered_actions):
            # Single line status printing
            status = f"{i + 1} / {num_anims}\t{action.name}"
            print(' ' * status_len, end=f'\r{status}\r')
            status_len = len(status) + 32

            if action.pxd_root:
                self.bool_root_motion = True
            else:
                self.bool_root_motion = False

            action_path = f"{base_dir}\\{action.name}.anm.pxd"
            arm_active.animation_data.action = action
            frame_rate = action.pxd_fps
            anim_export(self,
                        action_path,
                        arm_active,
                        action,
                        round(action.frame_start),
                        round(action.frame_end),
                        frame_rate,
                        )

        print(' ' * status_len, end=f"\rFinished exporting {num_anims} animations.\n")
        arm_active.animation_data.action = action_active
        scene_active.frame_current = frame_active
        self.report({'INFO'}, f"Successfully exported {len(filtered_actions)} animations")
        return {'FINISHED'}
