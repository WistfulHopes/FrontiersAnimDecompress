bl_info = {
    "name": "Hedgehog Engine 2 Uncompressed Animation Export",
    "author": "WistfulHopes, AdelQ",
    "version": (1, 1, 0),
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
from collections import deque 
        
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
    
    scale_correct: EnumProperty(
        items=[
            ("accurate", "Accurate", "Make output animation appear exactly as it does in the viewport by correcting bone offests from parent scaling (slower). Ensure that all your bones' scale inheritance mode is set to \"Aligned\" before exporting", 1),
            #("fast", "Fast", "Correct bone relocations, but don't update scene during relocations (slightly less accurate but visibly serviceable)", 2), #Not yet working right
            ("legacy", "Legacy", "Export using the original plugin's method (inaccurate display, but can (potentially) speed up the process of batch retargets if you know what you're doing. Use accurate mode wherever possible", 3),
            ],
        name="Scale Mode",
        description="Determine how the scale data in the animation is saved",
        default="accurate",
        )
    use_yx_orientation: BoolProperty(
        name="Use YX Bone Orientation",
        description="If your current skeleton uses YX orientation but your target skeleton uses XZ, enable this option to convert the animation to utilize XZ orientation",
        default=False,
        )

    def draw(self, context):
        layout = self.layout
        uiBoneBox = layout.box()
        uiBoneBox.label(text="Armature Settings",icon="ARMATURE_DATA")
        uiScaleCorrectRow = uiBoneBox.row()
        uiScaleCorrectRow.label(text="Scale Mode:")
        uiScaleCorrectRow.prop(self, "scale_correct", text="")

        uiOrientationRow = uiBoneBox.row()
        uiOrientationRow.prop(self, "use_yx_orientation",)
        
    def execute(self, context):
        Arm = bpy.context.active_object
        if not Arm:
            raise ValueError("No active object. Please select an armature as your active object.")
        Scene = bpy.context.scene
        
        if Arm.type == 'ARMATURE':
            CurFile = open(self.filepath,"wb")
            
            CurrentFrame = Scene.frame_current
            CurrentMode = bpy.context.mode
            
            utils_set_mode("POSE")
            
            for Bone in Arm.data.bones:
                Bone.inherit_scale = "ALIGNED"
            
            action = Arm.animation_data.action
            
            CurFile.write(struct.pack('<f', float(Scene.frame_end - Scene.frame_start) / Scene.render.fps))
            CurFile.write(struct.pack('<i', Scene.frame_end - Scene.frame_start + 1))
            CurFile.write(struct.pack('<i', len(Arm.pose.bones)))
            
            
            # Corrects bone positions as a result of scaling; should be used wherever possible
            if self.scale_correct == "accurate":
                for x in range(Scene.frame_end - Scene.frame_start + 1):
                    Scene.frame_set(Scene.frame_start + x)
                    
                    # Set up dictionaries
                    BoneMats = {}
                    BoneScales = {}
                    for y in Arm.pose.bones: 
                        BoneMats.update({y.name:mathutils.Matrix()})
                        BoneScales.update({y.name:y.scale.copy()})
                    BoneMatsNoScale = BoneMats.copy()
                    
                    # Get scaled positions
                    for y in range(len(Arm.pose.bones)):
                        Bone = Arm.pose.bones[y]
                        BoneMats.update({Bone.name:Bone.matrix.copy()})
                        Bone.scale = mathutils.Vector((1.0,1.0,1.0))
                    
                    # Apply scaled bone positions to unscaled bones, record new positions
                    for y in root_bones(Arm):
                        queue = deque([(y, 0)])
                        CurrentLevel = 0 
                        BonesInLevel = 1       
                        BonesProcessed = 0

                        while queue:
                            Bone, Level = queue.popleft()
                            if Level != CurrentLevel: #.............Track level of bone hierarchy, only updating scene once an entire level is cleared instead of for each bone (HUGE performance improvement)
                                bpy.context.view_layer.update()
                                CurrentLevel = Level
                                BonesProcessed = 1
                                BonesInLevel = len(queue) + 1
                            else:
                                BonesProcessed += 1

                            Bone.matrix.translation = BoneMats[Bone.name].translation 
                            
                            for z in Bone.children:
                                queue.append((z, Level + 1))
                            
                            if BonesProcessed == BonesInLevel:
                                bpy.context.view_layer.update() 
                                
                    # Caclulate and write transforms to file
                    for y in range(len(Arm.pose.bones)):
                        Bone = Arm.pose.bones[y]
                        if Bone.parent:
                            ParentMat = Bone.parent.matrix.copy()
                        else:
                            if self.use_yx_orientation:
                                ParentMat = mathutils.Matrix() @ mathutils.Matrix.Rotation(math.radians(-90.0), 4, 'X') @ mathutils.Matrix.Rotation(math.radians(-90.0), 4, 'Z')
                            else:
                                ParentMat = mathutils.Matrix() 

                        tmpQuat = (ParentMat.inverted() @ Bone.matrix.copy()).to_quaternion()
                        tmpPos = (ParentMat.inverted() @ mathutils.Matrix.Translation(Bone.matrix.translation)).translation
                        tmpScl = BoneScales[Bone.name]
                        
                        if self.use_yx_orientation:
                            CurFile.write(struct.pack('<ffff', tmpQuat[2],tmpQuat[3],tmpQuat[1],tmpQuat[0])) 
                            CurFile.write(struct.pack('<fff', tmpPos[1],tmpPos[2],tmpPos[0])) 
                            CurFile.write(struct.pack('<f', 0.0)) 
                            CurFile.write(struct.pack('<fff', tmpScl[1],tmpScl[2],tmpScl[0])) 
                            CurFile.write(struct.pack('<f', 1.0)) 
                        else:
                            CurFile.write(struct.pack('<ffff', tmpQuat[1],tmpQuat[2],tmpQuat[3],tmpQuat[0])) #......Rotations
                            CurFile.write(struct.pack('<fff', tmpPos[0],tmpPos[1],tmpPos[2])) #.....................Locations
                            CurFile.write(struct.pack('<f', 0.0)) #.................................................Unknown Float, has value but unsure of purpose
                            CurFile.write(struct.pack('<fff', tmpScl[0],tmpScl[1],tmpScl[2])) #.....................Scales
                            CurFile.write(struct.pack('<f', 1.0)) #.................................................Seems to always be 1.0
                        
            # Method used in original plugin. Not recommended if scaling is used
            elif self.scale_correct == "legacy":
                for x in range(Scene.frame_end - Scene.frame_start + 1):
                    Scene.frame_set(Scene.frame_start + x)
                    for y in range(len(Arm.pose.bones)):
                        Bone = Arm.pose.bones[y]
                        if Bone.parent:
                            Mat = Bone.parent.matrix.inverted() @ Arm.convert_space(pose_bone=Bone,matrix = Bone.matrix_basis,from_space='LOCAL',to_space='POSE')
                        else:
                            if self.use_yx_orientation:
                                Mat = Arm.convert_space(pose_bone=Bone,matrix = Bone.matrix_basis,from_space='LOCAL',to_space='POSE') @ mathutils.Matrix.Rotation(math.radians(90.0), 4, 'Z') @ mathutils.Matrix.Rotation(math.radians(90.0), 4, 'X')
                            else:
                                Mat = Arm.convert_space(pose_bone=Bone,matrix = Bone.matrix_basis,from_space='LOCAL',to_space='POSE')
                        
                        if self.use_yx_orientation:
                            tmpQuat = Mat.to_quaternion()
                            CurFile.write(struct.pack('<f', tmpQuat[2]))
                            CurFile.write(struct.pack('<f', tmpQuat[3]))
                            CurFile.write(struct.pack('<f', tmpQuat[1]))
                            CurFile.write(struct.pack('<f', tmpQuat[0]))
                            
                            tmpPos = Mat.translation
                            CurFile.write(struct.pack('<f', tmpPos[1]))
                            CurFile.write(struct.pack('<f', tmpPos[2]))
                            CurFile.write(struct.pack('<f', tmpPos[0]))
                            CurFile.write(struct.pack('<f', 0.0))
                            
                            tmpScl = Bone.scale
                            CurFile.write(struct.pack('<f', tmpScl[1]))
                            CurFile.write(struct.pack('<f', tmpScl[2]))
                            CurFile.write(struct.pack('<f', tmpScl[0]))
                            CurFile.write(struct.pack('<f', 0.0))
                        else:
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
            
            # TODO: add fast mode that is at least serviceable
            elif self.scale_correct == "fast":
                print("Eventually...")
            
            
            Scene.frame_current = CurrentFrame
            utils_set_mode(CurrentMode)             
            CurFile.close()
            del CurFile
        else:
                raise TypeError(f"Active object \"{Arm.name}\" is not an armature. Please select an armature.")
        return {'FINISHED'}
    
def utils_set_mode(mode):
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode=mode, toggle=False)
        
def root_bones(Arm):
    return [Bone for Bone in Arm.pose.bones if not Bone.parent]

def menu_func_export(self, context):
    self.layout.operator(HedgeEngineAnimationExport.bl_idname, text="HE2 Uncompressed Animation (.outanim)")
        
def register():
    bpy.utils.register_class(HedgeEngineAnimationExport)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    
def unregister():
    bpy.utils.unregister_class(HedgeEngineAnimationExport)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
        
if __name__ == "__main__":
    register()
