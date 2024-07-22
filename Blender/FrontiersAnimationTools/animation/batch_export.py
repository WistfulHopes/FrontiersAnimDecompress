import bpy
import os
from bpy_extras.io_utils import ExportHelper
from bpy.props import (BoolProperty,
                       StringProperty,
                       CollectionProperty
                       )
from .anim_export import anim_export
from ..ui.func_ops import filter_actions
from .console_output import BatchProgress


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

    bool_start_zero: BoolProperty(
        name="Sample From Frame 0",
        description="Enable to start sampling the animation from frame 0 regardless of the specified frame range. "
                    "Will not affect output frame range.\n\n"
                    "(NOTE: Will take longer if animation starts in middle of timeline, but useful for advanced users "
                    "using features such as physics simulations)",
        default=False,
    )

    def __init__(self):
        self.bool_root_motion = False
        self.bool_compress = True
        self.bool_additive = False

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if bpy.data.actions and obj and obj.type == 'ARMATURE':
            return True
        else:
            return False

    def draw(self, context):
        layout = self.layout

        ui_scene_box = layout.box()
        ui_scene_box.label(text="Animation Settings", icon='ACTION')

        ui_zero_row = ui_scene_box.row()
        ui_zero_row.prop(self, "bool_start_zero", )

        ui_bone_box = layout.box()
        ui_bone_box.label(text="Armature Settings", icon='ARMATURE_DATA')

        ui_orientation_row = ui_bone_box.row()
        ui_orientation_row.prop(self, "bool_yx_skel", )

    def execute(self, context):
        base_dir = os.path.dirname(self.filepath)
        arm_active = context.active_object
        scene_active = context.scene
        frame_active = scene_active.frame_current
        action_active = arm_active.animation_data.action
        filtered_actions = filter_actions(bpy.data.actions, context)

        progress = BatchProgress(self, num_items=len(filtered_actions), method='EXPORT')

        for i, action in enumerate(filtered_actions):
            progress.resume(item_num=i, name=action.name)

            if action.pxd_root:
                self.bool_root_motion = True
            else:
                self.bool_root_motion = False

            if action.pxd_additive:
                self.bool_additive = True
            else:
                self.bool_additive = False

            # TODO: Implement uncompressed animation export
            # if action.pxd_compress:
                # self.bool_compress = True
            # else:
                # self.bool_compress = False

            action_path = f"{base_dir}\\{action.name}.anm.pxd"
            arm_active.animation_data.action = action
            frame_rate = action.pxd_fps
            if not anim_export(self,
                               action_path,
                               arm_active,
                               action,
                               round(action.frame_start),
                               round(action.frame_end),
                               frame_rate,
                               ):
                progress.update_error(name=action.name)

        progress.finish()

        # Restore previous scene params
        arm_active.animation_data.action = action_active
        scene_active.frame_current = frame_active
        return {'FINISHED'}
