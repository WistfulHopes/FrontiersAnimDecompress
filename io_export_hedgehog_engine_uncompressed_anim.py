bl_info = {
    "name": "Hedgehog Engine 2 Uncompressed Animation Export",
    "author": "WistfulHopes",
    "version": (1, 0, 0),
    "blender": (2, 82, 0),
    "location": "File > Import-Export",
    "description": "A script to export uncompressed animations for Hedgehog Engine 2 games",
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
from bpy_extras.io_utils import ExportHelper

def utils_set_mode(mode):
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode=mode, toggle=False)
        
class HedgeEngineAnimationExport(bpy.types.Operator, ExportHelper):
    bl_idname = "custom_export_scene.hedgeenganimdecomp"
    bl_label = "export"
    filename_ext = ".outanim"
    filter_glob: StringProperty(
            default="*.outanim",
            options={'HIDDEN'},
            )
    filepath: StringProperty(subtype='FILE_PATH',)
    files: CollectionProperty(type=bpy.types.PropertyGroup)
    
    def draw(self, context):
        pass
    def execute(self, context):
        Arm = bpy.context.active_object
        Scene = bpy.context.scene
        if Arm.type == 'ARMATURE':
            CurFile = open(self.filepath,"wb")

            utils_set_mode("POSE")
            action = Arm.animation_data.action
            
            CurFile.write(struct.pack('<f', float(Scene.frame_end - Scene.frame_start + 1) / Scene.render.fps))
            CurFile.write(struct.pack('<i', Scene.frame_end - Scene.frame_start + 1))
            CurFile.write(struct.pack('<i', len(Arm.pose.bones)))
            
            for x in range(Scene.frame_end - Scene.frame_start + 1):
                Scene.frame_set(x)
                for y in range(len(Arm.pose.bones)):
                    Bone = Arm.pose.bones[y]
                    if Bone.parent:
                        Mat = Bone.parent.matrix.inverted() @ Arm.convert_space(pose_bone=Bone,matrix = Bone.matrix_basis,from_space='LOCAL',to_space='POSE')
                    else:
                        Mat = Arm.convert_space(pose_bone=Bone,matrix = Bone.matrix_basis,from_space='LOCAL',to_space='POSE')
                   
                    tmpQuat = Mat.to_quaternion()
                    CurFile.write(struct.pack('<f', tmpQuat[1]))
                    CurFile.write(struct.pack('<f', tmpQuat[2]))
                    CurFile.write(struct.pack('<f', tmpQuat[3]))
                    CurFile.write(struct.pack('<f', tmpQuat[0]))
                    
                    tmpPos = Mat.translation
                    CurFile.write(struct.pack('<f', tmpPos[0]))
                    CurFile.write(struct.pack('<f', tmpPos[1]))
                    CurFile.write(struct.pack('<f', tmpPos[2]))
                    CurFile.write(struct.pack('<f', 0.0))
                    
                    tmpScl = Bone.scale
                    CurFile.write(struct.pack('<f', tmpScl[0]))
                    CurFile.write(struct.pack('<f', tmpScl[1]))
                    CurFile.write(struct.pack('<f', tmpScl[2]))
                    CurFile.write(struct.pack('<f', 0.0))

            CurFile.close()
            del CurFile

        return {'FINISHED'}
    
def menu_func_export(self, context):
    self.layout.operator(HedgeEngineAnimationExport.bl_idname, text="Hedgehog Engine Uncompressed Export (.outanim)")
        
def register():
    bpy.utils.register_class(HedgeEngineAnimationExport)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    
def unregister():
    bpy.utils.unregister_class(HedgeEngineAnimationExport)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
        
if __name__ == "__main__":
    register()
