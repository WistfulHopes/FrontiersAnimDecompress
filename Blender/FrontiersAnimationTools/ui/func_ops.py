# Use for 3D Viewport side panel operators and functions

import bpy
import math
import mathutils
from bpy.props import (BoolProperty,
                       FloatProperty,
                       IntProperty,
                       StringProperty,
                       EnumProperty,
                       CollectionProperty
                       )


class MakeFrontiersActionActive(bpy.types.Operator):
    bl_label = "Set Action As Active"
    bl_idname = "anim_custom.make_frontiers_array"
    bl_description = "Sets this action as the active action, and sets the scene's FPS and frame range to accommodate"

    anim_name: StringProperty(default="")

    def execute(self, context):
        rms = 1 / math.sqrt(2)
        arm_active = context.active_object
        scene_active = context.scene

        if self.anim_name:
            action = bpy.data.actions[self.anim_name]
            if not arm_active.animation_data:
                arm_active.animation_data_create()
            arm_active.animation_data.action = action
            scene_active.render.fps = int(round(action.pxd_fps))
            scene_active.render.fps_base = scene_active.render.fps / action.pxd_fps
            scene_active.frame_start = round(action.frame_start)
            scene_active.frame_end = round(action.frame_end)

            if not action.pxd_root:
                arm_active.rotation_quaternion = mathutils.Quaternion((rms, rms, 0.0, 0.0))
                arm_active.location = mathutils.Vector((0.0, 0.0, 0.0))
                arm_active.scale = mathutils.Vector((1.0, 1.0, 1.0))

        return {'FINISHED'}


class ClearFrontiersFakeUser(bpy.types.Operator):
    bl_label = "Remove Action Persistence"
    bl_idname = "anim_custom.clear_frontiers_array"
    bl_description = "Removes fake users from all filtered actions. These actions will be lost upon file closure"

    def execute(self, context):
        filtered_actions = filter_actions(bpy.data.actions, context)
        num_done = 0
        for action in filtered_actions:
            if action.use_fake_user:
                action.use_fake_user = False
            else:
                num_done += 1
        if num_done == len(filtered_actions):
            self.report({'INFO'}, f"{num_done} actions already non-persistent")
        else:
            self.report({'INFO'}, f"Removed persistence from {len(filtered_actions) - num_done} actions")
        return {'FINISHED'}


class MakeFrontiersActionPersistent(bpy.types.Operator):
    bl_label = "Make Actions Persistent"
    bl_idname = "anim_custom.make_actions_persistent"
    bl_description = "Gives fake user to all filtered actions so they are saved after closing the file"

    def execute(self, context):
        filtered_actions = filter_actions(bpy.data.actions, context)
        num_done = 0
        for action in filtered_actions:
            if action.use_fake_user:
                num_done += 1
            else:
                action.use_fake_user = True
        if num_done == len(filtered_actions):
            self.report({'INFO'}, f"{num_done} actions already persistent")
        else:
            self.report({'INFO'}, f"Made {len(filtered_actions) - num_done} actions persistent")
        return {'FINISHED'}


class SetTransformModes(bpy.types.Operator):
    bl_label = "Correct Scale Mode"
    bl_idname = "skel_custom.inherit_aligned_scale"
    bl_description = "Sets correct transform types for use in HE2. Use this if the scale looks wrong for some reason"

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if obj and obj.type == 'ARMATURE':
            return True
        else:
            return False

    def execute(self, context):
        arm_active = context.active_object
        arm_active.rotation_mode = 'QUATERNION'
        for bone in arm_active.data.bones:
            if bone.inherit_scale != 'ALIGNED':
                bone.inherit_scale = 'ALIGNED'
        return {'FINISHED'}


def filter_actions(action_list, context):
    return [action for action in action_list if
            action.pxd_export and
            action.name.startswith(context.scene.frontiers_anim_prefix) and
            context.scene.frontiers_anim_contains in action.name]



