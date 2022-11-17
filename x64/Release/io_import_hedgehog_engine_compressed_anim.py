bl_info = {
    "name": "Hedgehog Engine 2 Decompressed Animation Import",
    "author": "Turk, WistfulHopes",
    "version": (1, 0, 0),
    "blender": (2, 82, 0),
    "location": "File > Import-Export",
    "description": "A script to import decompressed animations from Hedgehog Engine 2 games",
    "warning": "",
    "category": "Import-Export",
}
import sys
import bpy
import bmesh
import os
import io
import struct
import math
import mathutils
from bpy.props import (BoolProperty,
                       FloatProperty,
                       StringProperty,
                       EnumProperty,
                       CollectionProperty
                       )
from bpy_extras.io_utils import ImportHelper

class HedgeEngineAnimation(bpy.types.Operator, ImportHelper):
    bl_idname = "custom_import_scene.hedgeenganimdecomp"
    bl_label = "Import"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".model"
    filter_glob: StringProperty(
            default="*.outanim",
            options={'HIDDEN'},
            )
    filepath: StringProperty(subtype='FILE_PATH',)
    files: CollectionProperty(type=bpy.types.PropertyGroup)
    
    def draw(self, context):
        pass
    def execute(self, context):
        for animfile in self.files:
            Arm = bpy.context.active_object
            Scene = bpy.context.scene
            if Arm.type == 'ARMATURE':
                CurFile = open(os.path.join(os.path.dirname(self.filepath), animfile.name),"rb")
                Arm.animation_data_create()
                action = bpy.data.actions.new(os.path.basename(animfile.name))
                Arm.animation_data.action = action

                PlayRate = struct.unpack('<f', CurFile.read(0x4))[0]
                FrameCount = int.from_bytes(CurFile.read(4),byteorder='little')
                Scene.render.fps = int(FrameCount/PlayRate)
                Scene.frame_end = FrameCount
                BoneCount = int.from_bytes(CurFile.read(8),byteorder='little')

                utils_set_mode("POSE")
                
                for x in range(FrameCount): #FrameCount
                    CurFile.seek(0xC+0x30*BoneCount*x)
                    Scene.frame_set(x)
                    for y in range(BoneCount):
                        Bone = Arm.pose.bones[y] 
                        if Bone.parent:
                            ParentMat = Bone.parent.matrix.copy()
                        else:
                            ParentMat = mathutils.Matrix()

                        tmpQuat = struct.unpack('<ffff', CurFile.read(0x10))
                        if Bone.parent:
                            tmpQuat = (tmpQuat[3],tmpQuat[2],tmpQuat[0],tmpQuat[1])
                            Bone.rotation_quaternion = Arm.convert_space(pose_bone=Bone,matrix = ParentMat @ ((mathutils.Quaternion(tmpQuat)).to_matrix().to_4x4()),from_space='POSE',to_space='LOCAL').to_quaternion()
                        else:
                            Bone.rotation_quaternion = mathutils.Quaternion()
                        Bone.keyframe_insert("rotation_quaternion")
                        
                        tmpPos = struct.unpack('<fff', CurFile.read(0xC))
                        tmpPos = (tmpPos[2],tmpPos[0],tmpPos[1])
                        Bone.location = Arm.convert_space(pose_bone=Bone,matrix = ParentMat @ ((mathutils.Matrix.Translation(tmpPos))),from_space='POSE',to_space='LOCAL').translation
                        Bone.keyframe_insert("location")

                        CurFile.read(4)
                        
                        tmpScl = struct.unpack('<fff', CurFile.read(0xC))
                        if tmpScl != (0.0,0.0,0.0):
                            Bone.scale = tmpScl
                            Bone.keyframe_insert("scale")
                        else:
                            Bone.scale = mathutils.Vector((1.0,1.0,1.0))
                            Bone.keyframe_insert("scale")
    
                        CurFile.read(4)
                
                CurFile.close()
                del CurFile

        return {'FINISHED'}

def utils_set_mode(mode):
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode=mode, toggle=False)

def menu_func_import(self, context):
    self.layout.operator(HedgeEngineAnimation.bl_idname, text="Hedgehog Engine Compressed (.outanim)")
        
def register():
    bpy.utils.register_class(HedgeEngineAnimation)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    
def unregister():
    bpy.utils.unregister_class(HedgeEngineAnimation)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
        
if __name__ == "__main__":
    register()
