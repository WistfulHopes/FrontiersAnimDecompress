# Original skeleton export script by WistfulHopes
# https://github.com/WistfulHopes/FrontiersAnimDecompress/

import bpy
import io
import struct
import mathutils
from bpy_extras.io_utils import ExportHelper
from bpy.props import (BoolProperty,
                       StringProperty,
                       CollectionProperty
                       )



def offset_table(offset):
    offset_bits_2 = "{0:b}".format(offset >> 2)
    print(offset_bits_2)
    if offset > 16384:
        offset_bits = '11'
        for x in range(30 - len(offset_bits_2)):
            offset_bits += '0'
    elif offset > 64:
        offset_bits = '10'
        for x in range(14 - len(offset_bits_2)):
            offset_bits += '0'
    else:
        offset_bits = '01'
        for x in range(6 - len(offset_bits_2)):
            offset_bits += '0'
    return offset_bits + offset_bits_2


class BoneTransform:
    def __init__(self, pbone):
        mat = pbone.matrix_local
        if pbone.parent:
            mat = pbone.parent.matrix_local.inverted() @ pbone.matrix_local
        self.pos = mat.translation
        self.rot = mat.to_quaternion()


class MoveArray:
    def __init__(self, arm_obj):
        self.parent_indices = []
        self.name = []
        self.transform = []
        for x in range(len(arm_obj.pose.bones)):
            if (arm_obj.pose.bones[x].parent):
                self.parent_indices.append(arm_obj.pose.bones.find(arm_obj.pose.bones[x].parent.name))
            else:
                self.parent_indices.append(65535)
            self.name.append(bytes(arm_obj.pose.bones[x].name, 'ascii') + b'\x00')
            self.transform.append(BoneTransform(arm_obj.pose.bones[x].bone))


class HedgehogSkeletonExport(bpy.types.Operator, ExportHelper):
    bl_idname = "export_skeleton.frontiers_skel"
    bl_label = "Export"
    bl_description = "Exports PXD skeleton for Hedgehog Engine 2 games"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".pxd"
    filter_glob: StringProperty(
        default="*.pxd",
        options={'HIDDEN'},
    )
    filepath: StringProperty(subtype='FILE_PATH', )
    files: CollectionProperty(type=bpy.types.PropertyGroup)

    use_yx_orientation: BoolProperty(
        name="Convert from YX Bone Orientation",
        description="If your skeleton was imported from XZ to YX to function better in Blender, use this option to switch bones back from YX to XZ (important for in-game IK)",
        default=False,
    )

    def draw(self, context):
        layout = self.layout
        ui_bone_box = layout.box()
        ui_bone_box.label(text="Armature Settings", icon="ARMATURE_DATA")
        ui_bone_box.prop(self, "use_yx_orientation")

    @classmethod
    def poll(cls, context):
        obj = bpy.context.active_object
        if obj and obj.type == 'ARMATURE':
            return True
        else:
            return False

    def execute(self, context):
        arm_active = bpy.context.active_object
        if not arm_active:
            self.report({'INFO'}, f"No active armature. Please select an armature.")
            return {'CANCELLED'}
        if arm_active.type != 'ARMATURE':
            self.report({'INFO'}, f"Active object \"{arm_active.name}\" is not an armature. Please select an armature.")
            return {'CANCELLED'}

        buffer = io.BytesIO()

        magic = bytes('KSXP', 'ascii')
        buffer.write(magic)
        buffer.write(struct.pack('<i', 512))
        array = MoveArray(arm_active)

        parent_offset = 104
        null = 0

        buffer.write(parent_offset.to_bytes(8, 'little'))
        buffer.write(len(arm_active.pose.bones).to_bytes(8, 'little'))
        buffer.write(len(arm_active.pose.bones).to_bytes(8, 'little'))
        buffer.write(null.to_bytes(8, 'little'))

        name_offset = parent_offset + (len(arm_active.pose.bones) + 1) * 2
        if name_offset % 0x10 != 0:
            name_offset += 0x10 - name_offset % 0x10

        buffer.write(name_offset.to_bytes(8, 'little'))
        buffer.write(len(arm_active.pose.bones).to_bytes(8, 'little'))
        buffer.write(len(arm_active.pose.bones).to_bytes(8, 'little'))
        buffer.write(null.to_bytes(8, 'little'))

        matrix_offset = name_offset + len(arm_active.pose.bones) * 0x10

        buffer.write(matrix_offset.to_bytes(8, 'little'))
        buffer.write(len(arm_active.pose.bones).to_bytes(8, 'little'))
        buffer.write(len(arm_active.pose.bones).to_bytes(8, 'little'))
        buffer.write(null.to_bytes(8, 'little'))

        for x in range(len(arm_active.pose.bones)):
            parent_index = array.parent_indices[x].to_bytes(2, 'little')
            buffer.write(parent_index)

        if buffer.tell() % 0x10 != 0:
            for x in range(0x10 - buffer.tell() % 0x10):
                buffer.write(null.to_bytes(1, 'little'))

        name_data_offset = matrix_offset + len(arm_active.pose.bones) * 0x30

        for x in range(len(arm_active.pose.bones)):
            buffer.write(name_data_offset.to_bytes(16, 'little'))
            name_data_offset += len(array.name[x])

        for x in range(len(arm_active.pose.bones)):
            if self.use_yx_orientation:
                if not arm_active.pose.bones[x].parent:
                    # Identity matrix to swap YX to XZ
                    array.transform[x].rot @= mathutils.Quaternion((0.5, 0.5, 0.5, 0.5))
                buffer.write(struct.pack('<f', array.transform[x].pos[1]))
                buffer.write(struct.pack('<f', array.transform[x].pos[2]))
                buffer.write(struct.pack('<f', array.transform[x].pos[0]))
                buffer.write(struct.pack('<f', 0))
                buffer.write(struct.pack('<f', array.transform[x].rot[2]))
                buffer.write(struct.pack('<f', array.transform[x].rot[3]))
                buffer.write(struct.pack('<f', array.transform[x].rot[1]))
                buffer.write(struct.pack('<f', array.transform[x].rot[0]))
            else:
                buffer.write(struct.pack('<f', array.transform[x].pos[0]))
                buffer.write(struct.pack('<f', array.transform[x].pos[1]))
                buffer.write(struct.pack('<f', array.transform[x].pos[2]))
                buffer.write(struct.pack('<f', 0))
                buffer.write(struct.pack('<f', array.transform[x].rot[1]))
                buffer.write(struct.pack('<f', array.transform[x].rot[2]))
                buffer.write(struct.pack('<f', array.transform[x].rot[3]))
                buffer.write(struct.pack('<f', array.transform[x].rot[0]))

            buffer.write(struct.pack('<f', 1))
            buffer.write(struct.pack('<f', 1))
            buffer.write(struct.pack('<f', 1))
            buffer.write(struct.pack('<f', 0))

        string_table_size = 0

        for x in range(len(arm_active.pose.bones)):
            buffer.write(array.name[x])
            string_table_size += len(array.name[x])

        if buffer.tell() % 4 != 0:
            for x in range(4 - buffer.tell() % 4):
                buffer.write(null.to_bytes(1, 'little'))
                string_table_size += 1

        offset_table_size = 0

        bit = 66
        buffer.write(bit.to_bytes(1, 'little'))
        bit = 72
        buffer.write(bit.to_bytes(1, 'little'))
        buffer.write(bit.to_bytes(1, 'little'))

        offset_table_size += 3

        name_offset_bits = offset_table(name_offset - parent_offset + 0x20)
        name_offset_buffer = bytearray()
        index = 0
        while index < len(name_offset_bits):
            name_offset_buffer.append(int(name_offset_bits[index:index + 8], 2))
            index += 8

        offset_table_size += len(name_offset_buffer)

        buffer.write(name_offset_buffer)

        inbyte = 68
        for x in range(len(arm_active.pose.bones) - 1):
            buffer.write(inbyte.to_bytes(1, 'little'))
            offset_table_size += 1

        buffer.write(null.to_bytes(1, 'little'))
        offset_table_size += 1

        if buffer.tell() % 4 != 0:
            for x in range(4 - buffer.tell() % 4):
                buffer.write(null.to_bytes(1, 'little'))
                offset_table_size += 1

        with open(self.filepath, "wb") as file:
            buffer_size = buffer.getbuffer().nbytes

            bin_magic = bytes('BINA210L', 'ascii')
            file.write(bin_magic)
            file.write(struct.pack('<i', buffer_size + 0x40))
            file.write(struct.pack('<i', 1))

            data_magic = bytes('DATA', 'ascii')
            file.write(data_magic)
            file.write(struct.pack('<i', buffer_size + 0x30))
            file.write(struct.pack('<i', matrix_offset + len(arm_active.pose.bones) * 0x30))
            file.write(struct.pack('<i', string_table_size))
            file.write(struct.pack('<i', offset_table_size))
            file.write(struct.pack('<i', 0x18))
            file.write(null.to_bytes(24, 'little'))
            file.write(buffer.getvalue())

        return {'FINISHED'}

    def menu_func_export(self, context):
        self.layout.operator(
            HedgehogSkeletonExport.bl_idname,
            text="Hedgehog Engine 2 Skeleton (.skl.pxd)",
            icon='OUTLINER_OB_ARMATURE'
        )
