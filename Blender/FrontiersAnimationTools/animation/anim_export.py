import bpy
import mathutils
import math
import struct
import os
import io
from bpy_extras.io_utils import ExportHelper
from bpy.props import (BoolProperty,
                       StringProperty,
                       CollectionProperty
                       )
from ..FrontiersAnimDecompress.process_buffer import compress


def anim_export(self, filepath, arm_active, action_active, start_frame, end_frame, frame_rate):
    rms = 1 / math.sqrt(2)
    null = 0

    frame_count = end_frame - start_frame + 1
    duration = (frame_count - 1) / frame_rate
    bone_count = len(arm_active.pose.bones)

    buffer_main = io.BytesIO()
    buffer_root = io.BytesIO()

    buffer_main.write(struct.pack('<f', duration))
    buffer_main.write(struct.pack('<f', frame_rate))
    buffer_main.write(struct.pack('<i', frame_count))
    buffer_main.write(struct.pack('<i', bone_count))

    if self.bool_root_motion:
        buffer_root.write(struct.pack('<f', duration))
        buffer_root.write(struct.pack('<f', frame_rate))
        buffer_root.write(struct.pack('<i', frame_count))
        buffer_root.write(struct.pack('<i', 1))

    for frame in range(frame_count):
        bpy.context.scene.frame_set(start_frame + frame)

        # Build unscaled matrix map and separate scale map
        matrix_map_temp = {}
        scale_map_temp = {}
        for pbone in arm_active.pose.bones:
            tmp_loc, tmp_rot, tmp_scale = pbone.matrix.decompose()
            tmp_matrix = mathutils.Matrix.LocRotScale(tmp_loc, tmp_rot, mathutils.Vector((1.0, 1.0, 1.0)))
            matrix_map_temp.update({pbone.name: tmp_matrix})
            scale_map_temp.update({pbone.name: pbone.scale.copy()})  # normal scale is different from matrix scale

        # Negate unscaled parent matrices, write to buffer with actual scales
        for pbone in arm_active.pose.bones:
            if pbone.parent:
                tmp_parent_matrix = matrix_map_temp[pbone.parent.name]
                tmp_bone_length = pbone.length
            else:
                tmp_parent_matrix = mathutils.Matrix()
                tmp_bone_length = 0.0
            tmp_matrix = tmp_parent_matrix.inverted() @ matrix_map_temp[pbone.name]
            tmp_loc, tmp_rot, tmp_scale = tmp_matrix.decompose()
            tmp_scale = scale_map_temp[pbone.name]

            if self.bool_yx_skel:
                if not pbone.parent:
                    # Identity matrix to swap YX to XZ
                    tmp_rot @= mathutils.Quaternion((0.5, 0.5, 0.5, 0.5))
                buffer_main.write(struct.pack('<ffff', tmp_rot[2], tmp_rot[3], tmp_rot[1], tmp_rot[0]))
                buffer_main.write(struct.pack('<fff', tmp_loc[1], tmp_loc[2], tmp_loc[0]))
                buffer_main.write(struct.pack('<f', tmp_bone_length * tmp_scale[1]))
                buffer_main.write(struct.pack('<fff', tmp_scale[1], tmp_scale[2], tmp_scale[0]))
                buffer_main.write(struct.pack('<f', 1.0))
            else:
                buffer_main.write(struct.pack('<ffff', tmp_rot[1], tmp_rot[2], tmp_rot[3], tmp_rot[0]))
                buffer_main.write(struct.pack('<fff', tmp_loc[0], tmp_loc[1], tmp_loc[2]))
                buffer_main.write(struct.pack('<f', tmp_bone_length * tmp_scale[0]))
                buffer_main.write(struct.pack('<fff', tmp_scale[0], tmp_scale[1], tmp_scale[2]))
                buffer_main.write(struct.pack('<f', 1.0))

        if self.bool_root_motion:
            tmp_loc = arm_active.location.copy()
            tmp_rot = mathutils.Quaternion((rms, -rms, 0.0, 0.0)) @ arm_active.rotation_quaternion.copy()
            tmp_scale = arm_active.scale.copy()

            buffer_root.write(struct.pack('<ffff', tmp_rot[1], tmp_rot[2], tmp_rot[3], tmp_rot[0]))
            buffer_root.write(struct.pack('<fff', tmp_loc[0], tmp_loc[2], -tmp_loc[1]))
            buffer_root.write(struct.pack('<f', 0.0))
            buffer_root.write(struct.pack('<fff', tmp_scale[0], tmp_scale[1], tmp_scale[2]))
            buffer_root.write(struct.pack('<f', 1.0))

    main_buffer_compressed = compress(buffer_main.getvalue())
    if not len(main_buffer_compressed.getvalue()):
        self.report({'WARNING'}, f"{action_active.name} buffer failed to compress.")
        return {'CANCELLED'}

    root_buffer_compressed = compress(buffer_root.getvalue())
    if not len(root_buffer_compressed.getvalue()) and self.bool_root_motion is True:
        self.report({'WARNING'}, f"{action_active.name} root buffer failed to compress.")
        return {'CANCELLED'}

    del buffer_main
    del buffer_root

    with open(filepath, "wb") as file:
        main_buffer_size = main_buffer_compressed.getbuffer().nbytes
        root_buffer_size = root_buffer_compressed.getbuffer().nbytes

        if self.bool_root_motion and root_buffer_size:
            main_chunk_size = main_buffer_size + 0x10 - main_buffer_size % 0x10
            root_chunk_size = root_buffer_size + 4 - root_buffer_size % 4
            file_size = 0x80 + main_chunk_size + root_chunk_size + 4
        else:
            file_size = 0x80 + main_buffer_size + 4 - main_buffer_size % 4 + 4

        # BINA
        bin_magic = bytes('BINA210L', 'ascii')
        file.write(bin_magic)
        file.write(struct.pack('<i', file_size))
        file.write(struct.pack('<i', 1))

        # DATA
        data_magic = bytes('DATA', 'ascii')
        file.write(data_magic)
        file.write(struct.pack('<i', file_size - 0x10))
        file.write(struct.pack('<i', file_size - 0x10 - 0x34))
        file.write(struct.pack('<i', 0))

        file.write(struct.pack('<i', 4))
        file.write(struct.pack('<i', 0x18))
        file.write(null.to_bytes(24, 'little'))

        # PXAN
        pxan_magic = bytes('NAXP', 'ascii')
        file.write(pxan_magic)
        file.write(struct.pack('<i', 0x200))
        file.write(struct.pack('<i', 0x800))
        file.write(struct.pack('<i', 0))

        file.write(struct.pack('<i', 0x18))
        file.write(struct.pack('<i', 0))
        file.write(struct.pack('<f', duration))
        file.write(struct.pack('<i', frame_count))

        file.write(struct.pack('<i', bone_count))
        file.write(struct.pack('<i', 0))
        file.write(struct.pack('<q', 0x40))

        # Root offset
        if root_buffer_size:
            file.write(struct.pack('<q', main_buffer_size + 0x40 + 0x10 - main_buffer_size % 0x10))
        else:
            file.write(struct.pack('<q', 0))
        file.write(struct.pack('<q', 0))

        # Compressed track
        file.write(main_buffer_compressed.getvalue())
        if root_buffer_size:
            file.write(null.to_bytes(0x10 - main_buffer_size % 0x10, 'little'))
            # Root track
            file.write(root_buffer_compressed.getvalue())
            file.write(null.to_bytes(4 - root_buffer_size % 4, 'little'))
            file.write(struct.pack('<i', 0x00424644))
        else:
            file.write(null.to_bytes(4 - main_buffer_size % 4, 'little'))
            file.write(struct.pack('<i', 0x00004644))


class FrontiersAnimExport(bpy.types.Operator, ExportHelper):
    bl_idname = "export_anim.frontiers_anim"
    bl_label = "Export"
    bl_description = "Exports compressed Sonic Frontiers animation"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".pxd"
    filter_glob: StringProperty(
        default="*.pxd",
        options={'HIDDEN'},
    )
    filepath: StringProperty(subtype='FILE_PATH', )
    files: CollectionProperty(type=bpy.types.PropertyGroup)

    bool_yx_skel: BoolProperty(
        name="Use YX Bone Orientation",
        description="Enable if your skeleton was reoriented for Blender's YX orientation instead of Frontiers' XZ",
        default=False,
    )

    bool_root_motion: BoolProperty(
        name="Export Root Motion",
        description="Enable to export the animation of the armature object as root motion",
        default=True,
    )

    def draw(self, context):
        layout = self.layout
        ui_scene_box = layout.box()
        ui_scene_box.label(text="Animation Settings", icon='ACTION')

        ui_root_row = ui_scene_box.row()
        ui_root_row.prop(self, "bool_root_motion", )

        ui_bone_box = layout.box()
        ui_bone_box.label(text="Armature Settings", icon='ARMATURE_DATA')

        ui_orientation_row = ui_bone_box.row()
        ui_orientation_row.prop(self, "bool_yx_skel", )

    @classmethod
    def poll(cls, context):
        obj = bpy.context.active_object
        if obj and obj.type == 'ARMATURE':
            return True
        else:
            return False

    def execute(self, context):
        arm_active = bpy.context.active_object
        scene_active = bpy.context.scene
        frame_active = scene_active.frame_current
        if not arm_active:
            raise ValueError("No active object. Please select an armature as your active object.")
        if arm_active.type != 'ARMATURE':
            raise TypeError(f"Active object \"{arm_active.name}\" is not an armature. Please select an armature.")

        for bone in arm_active.data.bones:
            bone.inherit_scale = 'ALIGNED'

        action_active = arm_active.animation_data.action
        frame_rate = scene_active.render.fps / scene_active.render.fps_base

        anim_export(self,
                    self.filepath,
                    arm_active,
                    action_active,
                    scene_active.frame_start,
                    scene_active.frame_end,
                    frame_rate
                    )

        scene_active.frame_current = frame_active
        return{'FINISHED'}

    def menu_func_export(self, context):
        self.layout.operator(
            FrontiersAnimExport.bl_idname,
            text="Frontiers Compressed Animation (.anm.pxd)",
            icon='ACTION'
        )

