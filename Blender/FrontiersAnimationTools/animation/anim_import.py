import bpy
import mathutils
import math
import struct
import os
import io
import time
from bpy_extras.io_utils import ImportHelper
from bpy.props import (BoolProperty,
                       StringProperty,
                       EnumProperty,
                       CollectionProperty
                       )
from ..FrontiersAnimDecompress.process_buffer import decompress
from .console_output import BatchProgress

RMS = 1 / math.sqrt(2)


# Convert to global matrix with locations being unaffected by scale
def get_matrix_map_global(obj, matrix_map_local, scale_map):
    # Get global matrix of raw bone tracks, which are relative to parent track's local space.
    # Location is assumed to be unaffected by scale. Parent bone scaling in Blender affects locations
    # of child bones, so final position and rotation matrices must be calculated without scale first.
    matrix_map_global = {}
    for pbone in obj.pose.bones:
        matrix = mathutils.Matrix()
        scale = scale_map[pbone.name].copy()

        # Get final transform matrix and scale separately
        for parent_bone in reversed(pbone.parent_recursive):
            if parent_bone.name in matrix_map_local:
                matrix @= matrix_map_local[parent_bone.name]
                scale *= scale_map[parent_bone.name]
        matrix @= matrix_map_local[pbone.name]

        # Substitute proper scale in matrix with unscaled bone transform
        tmp_loc, tmp_rot, tmp_scale = matrix.decompose()
        matrix = mathutils.Matrix.LocRotScale(tmp_loc, tmp_rot, scale)
        matrix_map_global.update({pbone.name: matrix})
    return matrix_map_global


# Convert back to local space without scene update
def set_pose_matrices_global(obj, matrix_map_global, frame, keyframe_rules=None, truth_table=None, is_compressed=False):
    # Update global positions without needing bpy.context.view_layer.update() based on example in Blender docs:
    # https://docs.blender.org/api/current/bpy.types.Bone.html#bpy.types.Bone.convert_local_to_pose

    if not keyframe_rules:
        keyframe_rules = set()

    def rec(pbone, parent_matrix):
        if pbone.name in matrix_map_global:
            # Compute and assign local matrix, using the new parent matrix
            matrix = matrix_map_global[pbone.name].copy()
            if pbone.parent:
                pbone.matrix_basis = pbone.bone.convert_local_to_pose(matrix,
                                                                      pbone.bone.matrix_local,
                                                                      parent_matrix=parent_matrix,
                                                                      parent_matrix_local=pbone.parent.bone.matrix_local,
                                                                      invert=True)
            else:
                pbone.matrix_basis = pbone.bone.convert_local_to_pose(matrix,
                                                                      pbone.bone.matrix_local,
                                                                      invert=True)

        else:
            # Compute the updated pose matrix from local and new parent matrix
            if pbone.parent:
                matrix = pbone.bone.convert_local_to_pose(pbone.matrix_basis,
                                                          pbone.bone.matrix_local,
                                                          parent_matrix=parent_matrix,
                                                          parent_matrix_local=pbone.parent.bone.matrix_local)
            else:
                matrix = pbone.bone.convert_local_to_pose(pbone.matrix_basis, pbone.bone.matrix_local)

        if truth_table and not is_compressed:
            bone_key = truth_table[pbone.name]
            if bone_key[0]:
                pbone.keyframe_insert('location', frame=frame, options=keyframe_rules)
            if bone_key[1]:
                pbone.keyframe_insert('rotation_quaternion', frame=frame, options=keyframe_rules)
            if bone_key[2]:
                pbone.keyframe_insert('scale', frame=frame, options=keyframe_rules)
        else:

            pbone.keyframe_insert('location', frame=frame, options=keyframe_rules)
            pbone.keyframe_insert('rotation_quaternion', frame=frame, options=keyframe_rules)
            pbone.keyframe_insert('scale', frame=frame, options=keyframe_rules)

        # Recursively process children, passing the new matrix through
        for child in pbone.children:
            rec(child, matrix)

    # Scan all bone trees from their roots
    for pbone in obj.pose.bones:
        if not pbone.parent:
            rec(pbone, None)


# Parse keyframes into nested list for uncompressed animations
def get_uncompressed_frame_table(anim_file, frame_count, track_count, table_offset):
    # track_table[frame index][track index][loc/rot/scale]
    # avoid bones/dictionaries so function may be used for root motion
    frame_table = []
    for frame in range(frame_count):
        tmp_track_table = []
        for track in range(track_count):
            tmp_track_table.append([None, None, None])  # Location, Rotation, Scale
        frame_table.append(tmp_track_table)

    for track in range(track_count):
        anim_file.seek(table_offset + 0x48 * track)

        loc_count = int.from_bytes(anim_file.read(8), byteorder='little')
        loc_frame_offset = int.from_bytes(anim_file.read(8), byteorder='little') + 0x40
        loc_data_offset = int.from_bytes(anim_file.read(8), byteorder='little') + 0x40

        rot_count = int.from_bytes(anim_file.read(8), byteorder='little')
        rot_frame_offset = int.from_bytes(anim_file.read(8), byteorder='little') + 0x40
        rot_data_offset = int.from_bytes(anim_file.read(8), byteorder='little') + 0x40

        scale_count = int.from_bytes(anim_file.read(8), byteorder='little')
        scale_frame_offset = int.from_bytes(anim_file.read(8), byteorder='little') + 0x40
        scale_data_offset = int.from_bytes(anim_file.read(8), byteorder='little') + 0x40

        for i in range(loc_count):
            anim_file.seek(loc_frame_offset + 0x2 * i)
            tmp_frame = int.from_bytes(anim_file.read(2), byteorder='little')
            anim_file.seek(loc_data_offset + 0x10 * i)
            tmp_loc = struct.unpack('<fff', anim_file.read(0xC))
            frame_table[tmp_frame][track][0] = tmp_loc

        for i in range(rot_count):
            anim_file.seek(rot_frame_offset + 0x2 * i)
            tmp_frame = int.from_bytes(anim_file.read(2), byteorder='little')
            anim_file.seek(rot_data_offset + 0x10 * i)
            tmp_rot = struct.unpack('<ffff', anim_file.read(0x10))
            frame_table[tmp_frame][track][1] = tmp_rot

        for i in range(scale_count):
            anim_file.seek(scale_frame_offset + 0x2 * i)
            tmp_frame = int.from_bytes(anim_file.read(2), byteorder='little')
            anim_file.seek(scale_data_offset + 0x10 * i)
            tmp_scale = struct.unpack('<fff', anim_file.read(0xC))
            frame_table[tmp_frame][track][2] = tmp_scale

    return frame_table


class PXDAnimParam:
    def __init__(self, file):
        self.name = str()
        file.seek(8)
        file_size = int.from_bytes(file.read(4), byteorder='little')

        file.seek(0x40)
        magic = file.read(4)
        if magic != b'NAXP':
            self.error = f"Not a valid PXD animation file"
            return
        version = int.from_bytes(file.read(4), byteorder='little')
        if version != 512:
            self.error = "Unsupported PXD version"
            return
        flag_additive = int.from_bytes(file.read(1), byteorder='little')
        flag_compressed = int.from_bytes(file.read(1), byteorder='little')

        if flag_additive == 1:
            self.is_additive = True
        else:
            self.is_additive = False

        if flag_compressed == 8:
            self.is_compressed = True
        else:
            self.is_compressed = False

        file.seek(0x58)
        self.duration = struct.unpack('<f', file.read(4))[0]
        self.frame_count = int.from_bytes(file.read(4), byteorder='little')
        if self.duration != 0.0:
            self.frame_rate = (self.frame_count - 1) / self.duration
        else:
            self.frame_rate = 30.0
        self.track_count = int.from_bytes(file.read(8), byteorder='little')
        self.main_offset = int.from_bytes(file.read(8), byteorder='little')
        if self.main_offset:
            self.main_offset += 0x40
        else:
            self.main_offset = None

        self.root_offset = int.from_bytes(file.read(8), byteorder='little')
        if self.root_offset:
            self.root_offset += 0x40

        # Animations compressed with old FrontiersAnimDecompress had non-existent root chunk offsets beyond EOF
        if (self.root_offset > (file_size - 0x40)) or (not self.root_offset):
            self.root_offset = None

        file.seek(0)
        self.error = None


class FrontiersAnimImport(bpy.types.Operator, ImportHelper):
    bl_idname = "import_anim.frontiers_anim"
    bl_label = "Import"
    bl_description = "Imports compressed Sonic Frontiers animation"
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
        name="Import Root Motion",
        description="Import root motion animation onto skeleton object's transform",
        default=True,
    )

    bool_keyframe_needed: BoolProperty(
        name="Insert Needed Keyframes Only",
        description="Refrains from inserting keyframes if values are exact same as previous frame (not working)",
        default=False,
    )

    enum_loop_check: EnumProperty(
        items=[
            ("loop_auto", "Auto", "Pad the animation if \"_loop\" is in the file name", 1),
            ("loop_yes", "Yes", "Force pad the animation", 2),
            ("loop_no", "No", "Import file contents like normal", 3),
        ],
        name="Pad loop",
        description="(NOTE: Does not work on uncompressed animations)\n"
                    "(NOTE: May or may not cause issues with 360deg rotations)\n\n"
                    "Imports the animation with copies of the animation before and after the export range. Useful for advanced users trying to do things like smoothly looping physics animations",
        default="loop_no",
    )

    def __init__(self):
        self.bool_skel_conv = False
        self.keyframe_rules = set()
        self.frame_count_loop = 0
        self.pad_loop = False

    def draw(self, context):
        layout = self.layout
        ui_scene_box = layout.box()
        ui_scene_box.label(text="Animation Settings", icon='ACTION')

        ui_scene_row_loop = ui_scene_box.row()
        ui_scene_row_loop.label(text="Pad Loop:")
        ui_scene_row_loop.prop(self, "enum_loop_check", text="")

        ui_scene_row_root_motion = ui_scene_box.row()
        ui_scene_row_root_motion.prop(self, "bool_root_motion", )

        # Currently not working as expected, meant to only insert keyframes if local transform is different
        # ui_scene_row_needed = ui_scene_box.row()
        # ui_scene_row_needed.prop(self, "bool_keyframe_needed")

        ui_bone_box = layout.box()
        ui_bone_box.label(text="Armature Settings", icon='ARMATURE_DATA')

        ui_orientation_row = ui_bone_box.row()
        ui_orientation_row.prop(self, "bool_yx_skel", )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if obj and obj.type == 'ARMATURE':
            return True
        else:
            return False

    def execute(self, context):
        # Scene check and setup
        arm_active = context.active_object
        scene_active = context.scene

        if not arm_active:
            self.report({'INFO'}, f"No active armature. Please select an armature.")
            return {'CANCELLED'}
        if arm_active.type != 'ARMATURE':
            self.report({'INFO'}, f"Active object \"{arm_active.name}\" is not an armature. Please select an armature.")
            return {'CANCELLED'}

        arm_active.rotation_mode = 'QUATERNION'
        bone_count = len(arm_active.pose.bones)
        for bone in arm_active.data.bones:
            bone.inherit_scale = 'ALIGNED'

        # Status logging
        self.progress = BatchProgress(self, num_items=len(self.files), method='IMPORT')

        for f, file in enumerate(self.files):
            # Begin import
            anim_file = open(os.path.join(os.path.dirname(self.filepath), file.name), "rb")
            anim_param = PXDAnimParam(anim_file)
            self.progress.update_frame_count(anim_param.frame_count)
            self.progress.resume(frame_num=-1, name=file.name, item_num=f)

            if (not anim_param) or anim_param.error:
                self.progress.update_error(name=file_name, error=anim_param.error)
                continue

            scene_active.render.fps = int(round(anim_param.frame_rate))
            scene_active.render.fps_base = scene_active.render.fps / anim_param.frame_rate

            if bone_count != anim_param.track_count:
                self.report(
                    {'WARNING'},
                    f"Bone count of \"{arm_active.data.name}\" ({bone_count}) does not match track count of \"{file.name}\" ({anim_param.track_count}). Results may not turn out as expected."
                )

            anim_name = file.name
            for ext in [".outanim", ".anm", ".pxd"]:
                anim_name = anim_name.replace(ext, "")
            anim_param.name = anim_name
            arm_active.animation_data_create()
            action_active = bpy.data.actions.new(anim_name)
            arm_active.animation_data.action = action_active
            action_active.use_frame_range = True

            self.keyframe_rules = set()

            if self.enum_loop_check == "loop_yes" or (self.enum_loop_check == "loop_auto" and "_loop" in anim_name):
                self.pad_loop = True

            # frame_count_loop used ubiquitously in case of padding
            if self.pad_loop and anim_param.is_compressed:
                self.keyframe_rules.add('INSERTKEY_CYCLE_AWARE')
                self.frame_count_loop = 3 * (anim_param.frame_count - 1) + 1
                # Weird Blender behavior requires this to be set later
                # action_active.frame_start = anim_param.frame_count - 1
                # action_active.frame_end = self.frame_count_loop - anim_param.frame_count
                action_active.use_cyclic = True
            else:
                self.frame_count_loop = anim_param.frame_count
                scene_active.frame_start = action_active.frame_start = 0
                scene_active.frame_end = action_active.frame_end = self.frame_count_loop - 1

            action_active.pxd_export = True
            action_active.pxd_fps = anim_param.frame_rate
            action_active.pxd_root = self.bool_root_motion
            action_active.pxd_compress = anim_param.is_compressed
            action_active.pxd_additive = anim_param.is_additive

            if anim_param.is_compressed:
                import_action = self.import_compressed(arm_active, anim_file, anim_param)
            else:
                import_action = self.import_uncompressed(arm_active, anim_file, anim_param)
            anim_file.close()
            del anim_file
            if not import_action:
                self.progress.update_error(error=f"{file.name} compressed animation import couldn't be processed. File skipped.")
                continue

            # Mainly for uncompressed actions, doesn't really affect actions where every possible keyframe is filled
            for fcurve in action_active.fcurves:
                for point in fcurve.keyframe_points:
                    point.interpolation = 'LINEAR'

            # Keyframes become invisible if this is set earlier than anim import.
            if self.pad_loop and anim_param.is_compressed:
                scene_active.frame_start = action_active.frame_start = anim_param.frame_count - 1
                scene_active.frame_end = action_active.frame_end = self.frame_count_loop - anim_param.frame_count

        self.progress.finish()

        return {'FINISHED'}

    def import_compressed(self, arm_active, anim_file, anim_data):
        frame_count = anim_data.frame_count
        track_count = anim_data.track_count
        bone_count = len(arm_active.data.bones)
        main_offset = anim_data.main_offset
        root_offset = anim_data.root_offset

        anim_file.seek(main_offset)
        main_buffer_length = int.from_bytes(anim_file.read(4), byteorder='little')
        anim_file.seek(main_offset)
        main_buffer_compressed = anim_file.read(main_buffer_length)
        main_buffer = decompress(main_buffer_compressed)
        if not len(main_buffer.getvalue()):
            self.progress.update_error(error=f"{anim_data.name} buffer failed to initialize. File skipped.")
            return False
        del main_buffer_compressed

        if self.bool_root_motion and (root_offset is not None):
            anim_file.seek(root_offset, 0)
            root_buffer_length = int.from_bytes(anim_file.read(4), byteorder='little')
            anim_file.seek(root_offset, 0)
            root_buffer_compressed = anim_file.read(root_buffer_length)
            root_buffer = decompress(root_buffer_compressed)
            if not len(root_buffer.getvalue()):
                self.report({'WARNING'},f"{anim_data.name} root buffer failed to initialize. Importing without root motion.")
                root_buffer = None
            del root_buffer_compressed
        else:
            root_buffer = None

        # Nice for sanity check, but not necessary
        duration_acl = struct.unpack('<f', main_buffer.read(0x4))[0]
        frame_rate_acl = struct.unpack('<f', main_buffer.read(0x4))[0]
        frame_count_acl = int.from_bytes(main_buffer.read(4), byteorder='little')
        track_count_acl = int.from_bytes(main_buffer.read(4), byteorder='little')

        for frame in range(self.frame_count_loop):
            self.progress.resume(frame_num=frame)
            if self.pad_loop:
                main_buffer.seek(0x10 + (0x30 * track_count * (frame % (frame_count - 1))))
            else:
                main_buffer.seek(0x10 + (0x30 * track_count * frame))

            matrix_map_local = {}
            scale_map = {}

            for i in range(bone_count):
                pbone = arm_active.pose.bones[i]
                if i in range(track_count):
                    r0, r1, r2, r3 = struct.unpack('<ffff', main_buffer.read(0x10))
                    p0, p1, p2 = struct.unpack('<fff', main_buffer.read(0xC))
                    main_buffer.read(4)  # Float: Bone length
                    s0, s1, s2 = struct.unpack('<fff', main_buffer.read(0xC))
                    main_buffer.read(4)  # Float: 1.0

                    if self.bool_yx_skel:
                        tmp_rot = mathutils.Quaternion((r3, r2, r0, r1))
                        tmp_loc = mathutils.Vector((p2, p0, p1))
                        if not pbone.parent:
                            tmp_rot @= mathutils.Quaternion((0.5, -0.5, -0.5, -0.5))
                    else:
                        tmp_rot = mathutils.Quaternion((r3, r0, r1, r2))
                        tmp_loc = mathutils.Vector((p0, p1, p2))

                    matrix = mathutils.Matrix.LocRotScale(tmp_loc, tmp_rot, mathutils.Vector((1.0, 1.0, 1.0)))
                    matrix_map_local.update({pbone.name: matrix})

                    if (s0, s1, s2) != (0.0, 0.0, 0.0):
                        if self.bool_yx_skel:
                            tmp_scale = mathutils.Vector((s2, s0, s1))
                        else:
                            tmp_scale = mathutils.Vector((s0, s1, s2))
                    else:
                        tmp_scale = mathutils.Vector((1.0, 1.0, 1.0))

                    scale_map.update({pbone.name: tmp_scale})
                else:
                    matrix_map_local.update({pbone.name: mathutils.Matrix()})
                    scale_map.update({pbone.name: mathutils.Vector((1.0, 1.0, 1.0))})

            matrix_map_global = get_matrix_map_global(arm_active, matrix_map_local, scale_map)
            set_pose_matrices_global(arm_active, matrix_map_global, frame, keyframe_rules=self.keyframe_rules, is_compressed=True)

            if root_buffer:
                if self.pad_loop:
                    root_buffer.seek(0x10 + (0x30 * (frame % (frame_count - 1))))
                else:
                    root_buffer.seek(0x10 + (0x30 * frame))

                r0, r1, r2, r3 = struct.unpack('<ffff', root_buffer.read(0x10))
                p0, p1, p2 = struct.unpack('<fff', root_buffer.read(0xC))
                root_buffer.read(4)  # Float: Bone length
                s0, s1, s2 = struct.unpack('<fff', root_buffer.read(0xC))
                root_buffer.read(4)  # Float: 1.0

                tmp_rot = mathutils.Quaternion((RMS, RMS, 0.0, 0.0))
                tmp_rot @= mathutils.Quaternion((r3, r0, r1, r2))
                tmp_loc = mathutils.Vector((p0, -p2, p1))
                if (s0, s1, s2) != (0.0, 0.0, 0.0):
                    tmp_scale = mathutils.Vector((s0, s1, s2))
                else:
                    tmp_scale = mathutils.Vector((1.0, 1.0, 1.0))

                arm_active.rotation_quaternion = tmp_rot
                arm_active.location = tmp_loc
                arm_active.scale = tmp_scale

                arm_active.keyframe_insert('rotation_quaternion', frame=frame, options=self.keyframe_rules)
                arm_active.keyframe_insert('location', frame=frame, options=self.keyframe_rules)
                arm_active.keyframe_insert('scale', frame=frame, options=self.keyframe_rules)

            elif self.bool_root_motion and not root_buffer:
                self.report({'INFO'}, "No root motion chunk found.")
        return True

    def import_uncompressed(self, arm_active, anim_file, anim_data):
        frame_count = anim_data.frame_count
        track_count = anim_data.track_count
        bone_count = len(arm_active.data.bones)
        main_offset = anim_data.main_offset
        root_offset = anim_data.root_offset

        # Carry over local transformation if there's no new keyframe.
        # Needed for global transformation conversion to correct locations as a result of scaling.
        matrix_basis_carry = {}
        for pbone in arm_active.pose.bones:
            matrix_basis_carry[pbone.name] = mathutils.Matrix()

        frame_table = get_uncompressed_frame_table(anim_file, frame_count, track_count, main_offset)

        root_basis_carry = mathutils.Matrix() @ mathutils.Quaternion((RMS, RMS, 0.0, 0.0)).to_matrix().to_4x4()
        if self.bool_root_motion:
            if root_offset:
                root_frame_table = get_uncompressed_frame_table(anim_file, frame_count, 1, root_offset)
            else:
                self.report({'INFO'}, "No root motion chunk found. Skipping root motion import")

        for frame in range(frame_count):
            self.progress.resume(frame_num=frame)
            track_table = frame_table[frame]
            if self.bool_root_motion and root_offset:
                root_table = root_frame_table[frame][0]
            matrix_map_local = {}
            scale_map = {}

            # Need track_table status as dictionary for set_pose_matrices_global function.
            truth_table = {}
            for pbone in arm_active.pose.bones:
                truth_table[pbone.name] = [False, False, False]

            for i in range(bone_count):
                pbone = arm_active.pose.bones[i]
                if i in range(track_count):
                    bone_table = track_table[i]
                    bone_key = truth_table[pbone.name]
                    tmp_loc, tmp_rot, tmp_scale = matrix_basis_carry[pbone.name].decompose()

                    if bone_table[0]:  # Location
                        p0, p1, p2 = bone_table[0]
                        if self.bool_yx_skel:
                            tmp_loc = mathutils.Vector((p2, p0, p1))
                        else:
                            tmp_loc = mathutils.Vector((p0, p1, p2))
                        bone_key[0] = True

                    if bone_table[1]:  # Rotation
                        r0, r1, r2, r3 = bone_table[1]
                        if self.bool_yx_skel:
                            tmp_rot = mathutils.Quaternion((r3, r2, r0, r1))
                            if not pbone.parent:
                                tmp_rot @= mathutils.Quaternion((0.5, -0.5, -0.5, -0.5))
                        else:
                            tmp_rot = mathutils.Quaternion((r3, r0, r1, r2))
                        bone_key[1] = True

                    if bone_table[2]:  # Scale
                        s0, s1, s2 = bone_table[2]
                        if (s0, s1, s2) != (0.0, 0.0, 0.0):
                            if self.bool_yx_skel:
                                tmp_scale = mathutils.Vector((s2, s0, s1))
                            else:
                                tmp_scale = mathutils.Vector((s0, s1, s2))
                        else:
                            tmp_scale = mathutils.Vector((1.0, 1.0, 1.0))
                        bone_key[2] = True

                    matrix_basis_carry[pbone.name] = mathutils.Matrix.LocRotScale(tmp_loc, tmp_rot, tmp_scale)
                    matrix = mathutils.Matrix.LocRotScale(tmp_loc, tmp_rot, mathutils.Vector((1.0, 1.0, 1.0)))
                    matrix_map_local[pbone.name] = matrix
                    scale_map[pbone.name] = tmp_scale
                else:
                    matrix_map_local.update({pbone.name: mathutils.Matrix()})
                    scale_map.update({pbone.name: mathutils.Vector((1.0, 1.0, 1.0))})

            matrix_map_global = get_matrix_map_global(arm_active, matrix_map_local, scale_map)
            set_pose_matrices_global(arm_active, matrix_map_global, frame, truth_table=truth_table)

            if self.bool_root_motion and root_offset:
                # Always reorient for Z-up space, should work regardless if pose-space of skeleton is Y-up or Z-up
                tmp_loc, tmp_rot, tmp_scale = root_basis_carry.decompose()
                if root_table[0]:  # Location
                    p0, p1, p2 = root_table[0]
                    tmp_loc = mathutils.Vector((p0, -p2, p1))
                    arm_active.location = tmp_loc
                    arm_active.keyframe_insert('location', frame=frame, options=self.keyframe_rules)

                if root_table[1]:  # Rotation
                    r0, r1, r2, r3 = root_table[1]
                    tmp_rot = mathutils.Quaternion((RMS, RMS, 0.0, 0.0))
                    tmp_rot @= mathutils.Quaternion((r3, r0, r1, r2))
                    arm_active.rotation_quaternion = tmp_rot
                    arm_active.keyframe_insert('rotation_quaternion', frame=frame, options=self.keyframe_rules)

                if root_table[2]:  # Scale
                    s0, s1, s2 = root_table[2]
                    if (s0, s1, s2) != (0.0, 0.0, 0.0):
                        tmp_scale = mathutils.Vector((s0, s1, s2))
                    else:
                        tmp_scale = mathutils.Vector((1.0, 1.0, 1.0))
                        arm_active.scale = tmp_scale
                    arm_active.keyframe_insert('scale', frame=frame, options=self.keyframe_rules)

                root_basis_carry = mathutils.Matrix.LocRotScale(tmp_loc, tmp_rot, tmp_scale)

        return True

    def menu_func_import(self, context):
        self.layout.operator(
            FrontiersAnimImport.bl_idname,
            text="Frontiers Compressed Animation (.anm.pxd)",
            icon='ACTION',
        )
