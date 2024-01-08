bl_info = {
    "name": "Hedgehog Engine 2 Uncompressed Animation Export",
    "author": "WistfulHopes, AdelQ",
    "version": (1, 11, 0),
    "blender": (3, 3, 0),
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
            ("accurate", "Accurate", "Make output animation appear exactly as it does in the viewport by correcting bone offests from parent scaling (slower). Will set all bones' scale inheritance mode to \"Aligned\" before exporting", 1),
            ("legacy", "Legacy", "Export using the original plugin's method (inaccurate display, but can (potentially) speed up the process of batch retargets if you know what you're doing. Use accurate mode wherever possible", 3),
            ],
        name="Scale Mode",
        description="Determine how the scale data in the animation is saved",
        default="accurate",
        )
        
    use_scale_factor: EnumProperty(
        items=[
            ("none", "None", "Don't scale bone positions; ignore the skeleton object's scale and use the pose-space values", 0),
            ("object", "Object", "Scale the bone positions with the skeleton object's scale so the exported animation looks closer to what it does in the viewport (not recommended for non-uniform scales)", 1),
            ("manual", "Manual", "Manually set the factor to scale the positions by", 2),
            ],
        name="Scale Type",
        description="Scale the bone positions in your animation by a factor from the origin. Useful for animation conversions from animations that need skeletons at a specific scale (NOTE: Does not affect the scale of individual bones)",
        default="none",
        )
        
    scale_factor_value: FloatProperty(
        name="Factor",
        description="Factor to scale bone positions",
        default=1.0,
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
        
        uiUseScaleFactorRow = uiBoneBox.row()
        uiUseScaleFactorRow.label(text="Position Scale:")
        uiUseScaleFactorRow.prop(self, "use_scale_factor", text="")
        
        uiScaleFactorValueRow = uiBoneBox.row()
        uiScaleFactorValueRow.label(text="Scale Factor:")
        uiScaleFactorValueRow.prop(self, "scale_factor_value", text="")
        
        if self.use_scale_factor == "manual":
            scaleFactorEnable = True
        else:
            scaleFactorEnable = False
        
        uiScaleFactorValueRow.enabled = scaleFactorEnable

        uiOrientationRow = uiBoneBox.row()
        uiOrientationRow.prop(self, "use_yx_orientation")
        
    def execute(self, context):
        Arm = bpy.context.active_object
        Scene = bpy.context.scene
        if not Arm:
            raise ValueError("No active object. Please select an armature as your active object.")
        if Arm.type != 'ARMATURE':
            raise TypeError(f"Active object \"{Arm.name}\" is not an armature. Please select an armature.")
        objectScale = Arm.scale.copy()
        CurrentFrame = Scene.frame_current
        CurrentMode = bpy.context.mode
        utils_set_mode("POSE")
        for Bone in Arm.data.bones:
            Bone.inherit_scale = "ALIGNED"
        
        with open(self.filepath,"wb") as CurFile, open(self.filepath + "-root","wb") as CurFileRoot:
            action = Arm.animation_data.action
            
            Framerate = Scene.render.fps / Scene.render.fps_base

            CurFile.write(struct.pack('<f', float(Scene.frame_end - Scene.frame_start) / Framerate))
            CurFile.write(struct.pack('<i', Scene.frame_end - Scene.frame_start + 1))
            CurFile.write(struct.pack('<i', len(Arm.pose.bones)))
            CurFileRoot.write(struct.pack('<f', float(Scene.frame_end - Scene.frame_start) / Framerate))
            CurFileRoot.write(struct.pack('<i', Scene.frame_end - Scene.frame_start + 1))
            CurFileRoot.write(struct.pack('<i', 1))

            
            for x in range(Scene.frame_end - Scene.frame_start + 1):
                Scene.frame_set(Scene.frame_start + x)
                
                # Corrects bone positions as a result of scaling; should be used wherever possible
                if self.scale_correct == "accurate":
                    BoneMats = {}
                    BoneScales = {}
                    BoneLengths = {}
                    
                    # Get scaled positions, reset scales
                    for Bone in Arm.pose.bones:
                        BoneLengths.update({Bone.name:0.0})
                        BoneMats.update({Bone.name:Bone.matrix.copy()})
                        BoneScales.update({Bone.name:Bone.scale.copy()})
                        Bone.scale = mathutils.Vector((1.0,1.0,1.0))
                    
                    # Updated scaled positions to unscaled bones
                    queue_transforms(Arm, BoneMats)
                    
                    # Caclulate and write transforms to file
                    for Bone in Arm.pose.bones:
                        if Bone.parent:
                            ParentMat = Bone.parent.matrix.copy()
                        elif self.use_yx_orientation:
                            ParentMat = mathutils.Matrix() @ mathutils.Matrix.Rotation(math.radians(-90.0), 4, 'X') @ mathutils.Matrix.Rotation(math.radians(-90.0), 4, 'Z')
                        else:
                            ParentMat = mathutils.Matrix() 
                        tmpQuat = (ParentMat.inverted() @ Bone.matrix.copy()).to_quaternion()
                        tmpPos = (ParentMat.inverted() @ mathutils.Matrix.Translation(Bone.matrix.translation)).translation
                        tmpScl = BoneScales[Bone.name]
                        tmpLength = Bone.length
                        
                        if Bone.name == "Reference":
                            anim_export(CurFileRoot, tmpPos, tmpQuat, tmpScl, tmpLength, self)
                            anim_export(CurFile, (0.0,0.0,0.0), (1.0,0.0,0.0,0.0), (1,1,1), 0.0, self)
                        else:
                            anim_export(CurFile, tmpPos, tmpQuat, tmpScl, tmpLength, self)
                            
                            
                    # Restore old transforms in case of missing keyframes  
                    for Bone in Arm.pose.bones:
                        Bone.scale = BoneScales[Bone.name]
                    queue_transforms(Arm, BoneMats)
        
                # Original plug-in method, only marginally faster and does not treat scales properly
                elif self.scale_correct == "legacy":
                    for Bone in Arm.pose.bones:
                        if Bone.parent:
                            Mat = Bone.parent.matrix.inverted() @ Arm.convert_space(pose_bone=Bone,matrix = Bone.matrix_basis,from_space='LOCAL',to_space='POSE')
                        elif self.use_yx_orientation:
                            Mat = Arm.convert_space(pose_bone=Bone,matrix = Bone.matrix_basis,from_space='LOCAL',to_space='POSE') @ mathutils.Matrix.Rotation(math.radians(90.0), 4, 'Z') @ mathutils.Matrix.Rotation(math.radians(90.0), 4, 'X')
                        else:
                            Mat = Arm.convert_space(pose_bone=Bone,matrix = Bone.matrix_basis,from_space='LOCAL',to_space='POSE')
                        tmpQuat = Mat.to_quaternion()
                        tmpPos = Mat.translation
                        tmpScl = Bone.scale
                        
                        if Bone.name == "Reference":
                            anim_export(CurFileRoot, tmpPos, tmpQuat, tmpScl, tmpLength, self)
                            anim_export(CurFile, (0.0,0.0,0.0), (1.0,0.0,0.0,0.0), (1,1,1), 0.0, self)
                        else:
                            anim_export(CurFile, tmpPos, tmpQuat, tmpScl, 0.0, self)
            
                else:
                    raise TypeError("None or invalid scale correction method.")
            
        Scene.frame_current = CurrentFrame
        utils_set_mode(CurrentMode)             
        
        return {'FINISHED'}
    
def utils_set_mode(mode):
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode=mode, toggle=False)

def queue_transforms(Arm, BoneMats):
    root_bones = [Bone for Bone in Arm.pose.bones if not Bone.parent]
    for y in root_bones:
        queue = deque([(y, 0)])
        CurrentLevel = 0 
        BonesInLevel = 1       
        BonesProcessed = 0
        while queue:
            Bone, Level = queue.popleft()
            if Level != CurrentLevel:
                CurrentLevel = Level
                BonesProcessed = 1
                BonesInLevel = len(queue) + 1
            else:
                BonesProcessed += 1

            Bone.matrix.translation = BoneMats[Bone.name].translation 
            
            for ChildBone in Bone.children:
                queue.append((ChildBone, Level + 1))
            
            if BonesProcessed == BonesInLevel:
                bpy.context.view_layer.update() 

def anim_export(CurFile, tmpPos, tmpQuat, tmpScl, tmpLength, ClassSelf):
    if ClassSelf.use_scale_factor == "manual":
        tmpPos *= ClassSelf.scale_factor_value
    elif ClassSelf.use_scale_factor == "object":
        tmpPos = mathutils.Vector((tmpPos[0]*objectScale[0],tmpPos[1]*objectScale[1],tmpPos[2]*objectScale[2]))

    if ClassSelf.use_yx_orientation:
        CurFile.write(struct.pack('<ffff', tmpQuat[2],tmpQuat[3],tmpQuat[1],tmpQuat[0])) 
        CurFile.write(struct.pack('<fff', tmpPos[1],tmpPos[2],tmpPos[0])) 
        CurFile.write(struct.pack('<f', tmpLength)) 
        CurFile.write(struct.pack('<fff', tmpScl[1],tmpScl[2],tmpScl[0])) 
        CurFile.write(struct.pack('<f', 1.0)) 
    else:
        CurFile.write(struct.pack('<ffff', tmpQuat[1],tmpQuat[2],tmpQuat[3],tmpQuat[0]))
        CurFile.write(struct.pack('<fff', tmpPos[0],tmpPos[1],tmpPos[2]))
        CurFile.write(struct.pack('<f', tmpLength))
        CurFile.write(struct.pack('<fff', tmpScl[0],tmpScl[1],tmpScl[2]))
        CurFile.write(struct.pack('<f', 1.0))

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
