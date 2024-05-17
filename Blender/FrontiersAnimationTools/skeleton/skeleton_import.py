# Original skeleton import function from .model importer by Turk645
# https://github.com/Turk645/Hedgehog-Engine-2-Mesh-Blender-Importer

import bpy
import io
import os
import struct
import mathutils
from bpy_extras.io_utils import ImportHelper
from bpy.props import (BoolProperty,
                       FloatProperty,
                       StringProperty,
                       EnumProperty,
                       CollectionProperty
                       )


class HedgehogSkeletonImport(bpy.types.Operator, ImportHelper):
    bl_idname = "import_skeleton.frontiers_skel"
    bl_label = "Import"
    bl_description = "Imports PXD skeleton from Hedgehog Engine 2 games"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".pxd"
    filter_glob: StringProperty(
        default="*.pxd",
        options={'HIDDEN'},
    )
    filepath: StringProperty(subtype='FILE_PATH', )
    files: CollectionProperty(type=bpy.types.PropertyGroup)

    use_yx_orientation: BoolProperty(
        name="Convert to YX Bone Orientation",
        description="Reorient bones from XZ to YX to make bones coincide with limbs and enable mirror support",
        default=False,
    )

    get_bone_lengths: BoolProperty(
        name="Approximate Bone Lengths",
        description="Calculate and apply approximate bone lengths",
        default=True,
    )

    def update_min_length(self, context):
        if self.get_bone_lengths_min > self.get_bone_lengths_max:
            self.get_bone_lengths_min = self.get_bone_lengths_max

    def update_max_length(self, context):
        if self.get_bone_lengths_min > self.get_bone_lengths_max:
            self.get_bone_lengths_max = self.get_bone_lengths_min

    get_bone_lengths_min: FloatProperty(
        name="Min",
        description="Calculated bone length will not exceed any lower than this value",
        default=0.025,
        min=0.01,
        soft_max=1.0,
        update=update_max_length,
    )

    get_bone_lengths_max: FloatProperty(
        name="Max",
        description="Calculated bone length will not exceed any higher than this value",
        default=0.600,
        min=0.01,
        soft_max=1.0,
        update=update_min_length,
    )

    get_bone_lengths_end: EnumProperty(
        items=[
            ("prevLength", "Parent Length", "Set end bone lengths to be the same as their respective parents", 1),
            ("minLength", "Minimum length", "Set end bone lengths to the minimum", 2),
            ("customLength", "Custom length", "Set end bone lengths to specified value", 3),
        ],
        name="End Bone Length",
        description="How the end bones' lengths will be determined",
        default="prevLength",
    )

    get_bone_lengths_custom: FloatProperty(
        name="End Bone Length",
        description="Constant end bone length",
        default=0.100,
        min=0.01,
        soft_max=1.0,
    )

    aligned_scale: BoolProperty(
        name="Aligned Scale Inheritance",
        description="Set bone scale inheritance mode to \"Aligned,\" the common non-shearing method used in games",
        default=True,
    )

    def draw(self, context):
        layout = self.layout

        ui_bone_box = layout.box()
        ui_bone_box.label(text="Armature Settings", icon="ARMATURE_DATA")

        ui_bone_box.prop(self, "use_yx_orientation")
        ui_bone_box.prop(self, "aligned_scale")
        ui_bone_box.prop(self, "get_bone_lengths")

        ui_length_box = ui_bone_box.box()
        ui_length_row = ui_length_box.row()
        ui_length_row.prop(self, "get_bone_lengths_min")
        ui_length_row.prop(self, "get_bone_lengths_max")

        ui_length_end_row = ui_length_box.row()
        ui_length_end_row.label(text="End Bone Length")
        ui_length_end_row.prop(self, "get_bone_lengths_end", text="")

        if self.get_bone_lengths_end == "customLength":
            ui_length_box.prop(self, "get_bone_lengths_custom")

        ui_length_box.enabled = self.get_bone_lengths

    def execute(self, context):
        bpy.ops.object.select_all(action='DESELECT')
        for file in self.files:
            skel_file = open(os.path.join(os.path.dirname(self.filepath), file.name), "rb")
            if not self.skel_check(skel_file):
                return {'CANCELLED'}

            skel_name = file.name
            for ext in [".skl", ".pxd"]:
                skel_name = skel_name.replace(ext, "")

            skel_file.seek(0x48)
            skel_parenting_offset = int.from_bytes(skel_file.read(4), byteorder='little') + 0x40
            skel_file.seek(4, 1)
            skel_parenting_count = int.from_bytes(skel_file.read(4), byteorder='little')
            skel_file.seek(0x68)
            skel_name_table = int.from_bytes(skel_file.read(4), byteorder='little') + 0x40
            skel_file.seek(0x88)
            skel_pos_offset = int.from_bytes(skel_file.read(4), byteorder='little') + 0x40

            armature_data = bpy.data.armatures.new(f"{skel_name}_skeleton")
            armature_obj = bpy.data.objects.new(f"{skel_name}_skeleton", armature_data)
            armature_obj.show_in_front = True

            bpy.context.collection.objects.link(armature_obj)
            bpy.context.view_layer.objects.active = armature_obj
            armature_obj.rotation_euler = (1.5707963705062866, 0, 0)
            bpy.ops.object.select_all(action='DESELECT')
            armature_obj.select_set(True)

            utils_set_mode('EDIT')

            skel_table = []
            for x in range(skel_parenting_count):
                skel_file.seek(skel_parenting_offset + x * 0x2)
                bone_parent = int.from_bytes(skel_file.read(2), byteorder='little', signed=True)
                skel_file.seek(skel_name_table + x * 0x10)
                skel_name_offset = int.from_bytes(skel_file.read(4), byteorder='little') + 0x40
                skel_file.seek(skel_name_offset)
                bone_name = read_zero_term_string(skel_file)
                skel_file.seek(skel_pos_offset + x * 0x30)
                tmp_vec = struct.unpack('<fff', skel_file.read(4 * 3))
                if self.use_yx_orientation:
                    bone_vec = (tmp_vec[2], tmp_vec[0], tmp_vec[1])
                else:
                    bone_vec = (tmp_vec[0], tmp_vec[1], tmp_vec[2])
                skel_file.seek(4, 1)
                temp_rot = struct.unpack('<ffff', skel_file.read(4 * 4))
                if self.use_yx_orientation:
                    bone_rot = (temp_rot[3], temp_rot[2], temp_rot[0], temp_rot[1])
                else:
                    bone_rot = (temp_rot[3], temp_rot[0], temp_rot[1], temp_rot[2])

                skel_table.append({"loc": bone_vec, "rot": bone_rot})

                edit_bone = armature_obj.data.edit_bones.new(bone_name)
                edit_bone.use_connect = False
                edit_bone.use_inherit_rotation = True

                if self.aligned_scale:
                    edit_bone.inherit_scale = 'ALIGNED'

                edit_bone.use_local_location = True
                edit_bone.head = (0, 0, 0)
                if self.use_yx_orientation:
                    edit_bone.tail = (0.1, 0, 0)
                    edit_bone.roll = -1.5707963705062866
                else:
                    edit_bone.tail = (0, 0.1, 0)
                if bone_parent > -1:
                    edit_bone.parent = armature_obj.data.edit_bones[bone_parent]
            utils_set_mode('POSE')

            for x in range(skel_parenting_count):
                pbone = armature_obj.pose.bones[x]
                pbone.rotation_mode = 'QUATERNION'
                pbone.rotation_quaternion = skel_table[x]["rot"]
                pbone.location = skel_table[x]["loc"]

            bpy.ops.pose.armature_apply()

            # Set bone lengths
            if self.get_bone_lengths:
                utils_set_mode('EDIT')
                for x in range(skel_parenting_count):
                    edit_bone = armature_obj.data.edit_bones[x]
                    child_bone = None

                    # Find child with the most children as the bone to calculate length from
                    for child_bone_test in edit_bone.children:
                        test = 0
                        count = len(child_bone_test.children_recursive)
                        if child_bone_test == edit_bone.children[0] or test < count:
                            test = count
                            child_bone = child_bone_test

                    if child_bone:
                        length = (edit_bone.head - child_bone.head).length
                    elif self.get_bone_lengths_end == "prevLength":
                        length = edit_bone.parent.length
                    elif self.get_bone_lengths_end == "customLength":
                        length = self.get_bone_lengths_custom
                    else:
                        length = self.get_bone_lengths_min

                    if length > self.get_bone_lengths_max:
                        edit_bone.length = self.get_bone_lengths_max
                    elif length < self.get_bone_lengths_min:
                        edit_bone.length = self.get_bone_lengths_min
                    else:
                        edit_bone.length = length

            utils_set_mode('OBJECT')

            skel_file.close()
            del skel_file

        return {'FINISHED'}

    def menu_func_import(self, context):
        self.layout.operator(
            HedgehogSkeletonImport.bl_idname,
            text="Hedgehog Engine 2 Skeleton (.skl.pxd)",
            icon='OUTLINER_OB_ARMATURE'
        )

    def skel_check(self, file):
        file.seek(0x40, 0)
        magic = file.read(4)
        version = int.from_bytes(file.read(4), byteorder='little')
        const = int.from_bytes(file.read(4), byteorder='little')
        if magic != b'KSXP':
            self.report({'ERROR'}, f"{file.name}: Not a valid PXD skeleton file")
            return False
        if version != 512 or const != 104:
            self.report({'ERROR'}, f"{file.name}: Wrong PXD version")
            return False
        file.seek(0, 0)
        return True


def read_zero_term_string(file):
    temp_bytes = []
    while True:
        b = file.read(1)
        if b is None or b[0] == 0:
            return bytes(temp_bytes).decode('utf-8')
        else:
            temp_bytes.append(b[0])


def utils_set_mode(mode):
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode=mode, toggle=False)
