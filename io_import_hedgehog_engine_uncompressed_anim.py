bl_info = {
    "name": "Hedgehog Engine 2 Decompressed Animation Import",
    "author": "Turk, WistfulHopes, AdelQ",
    "version": (1, 11, 0),
    "blender": (3, 3, 0),
    "location": "File > Import-Export",
    "description": "A script to import decompressed animations from Hedgehog Engine 2 games",
    "warning": "",
    "category": "Import-Export",
}
import bpy
import os
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
from collections import deque

class HedgeEngineAnimation(bpy.types.Operator, ImportHelper):
    bl_idname = "custom_import_scene.hedgeenganimdecomp"
    bl_label = "Import"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".outanim"
    filter_glob: StringProperty(
            default="*.outanim",
            options={'HIDDEN'},
            )
    filepath: StringProperty(subtype='FILE_PATH',)
    files: CollectionProperty(type=bpy.types.PropertyGroup)

    scale_correct: EnumProperty(
        items=[
            ("accurate", "Accurate", "Correct bone relocations as a result of parent scaling", 1),
            ("legacy", "Legacy", "Import using the original plugin's method (inaccurate, but good for revisiting old .outanim exports)", 2),
            ],
        name="Scale Mode",
        description="Determine how the scale data in the animation is read",
        default="accurate",
        )

    use_yx_orientation: BoolProperty(
        name="Use YX Bone Orientation",
        description="If your imported skeleton was reoritented to use Y and X instead of X and Z as the primary and secondary axis respectively, enable this option to read the animation for Blender's bone orientation",
        default=False,
        )

    loop_anim: EnumProperty(
        items=[
            ("loopAuto", "Auto", "Fix loop if \"_loop\" is in the file name", 1),
            ("loopYes", "Yes", "Copies the first frame to the last frame", 2),
            ("loopNo", "No", "Import the last frame's pose data from the file", 3),
            ],
        name="Loop",
        description="For animations that got messed up from being recompressed and decompressed multiple times",
        default="loopNo",
        )
        
    use_root_motion: BoolProperty(
        name="Import Root Motion",
        description="Finds associated animation file for transformation of the \"Reference\" bone",
        default=True,
        )
    
    def draw(self, context):
        layout = self.layout
        uiSceneBox = layout.box()
        uiSceneBox.label(text="Animation Settings",icon='ACTION')
        uiSceneRowLoop = uiSceneBox.row()
        uiSceneRowLoop.label(text="Fix Loop:")
        uiSceneRowLoop.prop(self, "loop_anim", text="")

        uiBoneBox = layout.box()
        uiBoneBox.label(text="Armature Settings",icon='ARMATURE_DATA')
        uiScaleCorrectRow = uiBoneBox.row()
        uiScaleCorrectRow.label(text="Scale Mode:")
        uiScaleCorrectRow.prop(self, "scale_correct", text="")

        uiOrientationRow = uiBoneBox.row()
        uiOrientationRow.prop(self, "use_yx_orientation",)
        
        uiFileBox = layout.box()
        uiFileBox.label(text="File Settings",icon="FILE_BLANK")
        uiRootMotionRow = uiFileBox.row()
        uiRootMotionRow.prop(self, "use_root_motion")
        
    def execute(self, context):
        Arm = bpy.context.active_object
        if not Arm:
            raise ValueError("No active object. Please select an armature as your active object.")
        if Arm.type != 'ARMATURE':
            raise TypeError(f"Active object \"{Arm.name}\" is not an armature. Please select an armature.")
        Scene = bpy.context.scene
        CurrentFrame = Scene.frame_current
        CurrentMode = bpy.context.mode
        utils_set_mode("POSE")
        for Bone in Arm.data.bones:
            Bone.inherit_scale = 'ALIGNED'

        for animfile in self.files:
            CurFile = open(os.path.join(os.path.dirname(self.filepath), animfile.name),"rb")
            RootFilename = os.path.basename(animfile.name) + "-root"
            CurRootFile = 0
            if RootFilename in os.listdir(os.path.dirname(self.filepath) + "\\") and self.use_root_motion == True:
                CurRootFile = open(os.path.join(os.path.dirname(self.filepath), RootFilename),"rb")
            
            AnimName = os.path.basename(animfile.name)
            for x in [".outanim", ".anm", ".pxd"]:
                AnimName = AnimName.replace(x, "")
                
            Arm.animation_data_create()
            action = bpy.data.actions.new(AnimName)
            Arm.animation_data.action = action
            
            PlayRate = struct.unpack('<f', CurFile.read(0x4))[0]
            FrameCount = int.from_bytes(CurFile.read(4),byteorder='little')
            BoneCount = int.from_bytes(CurFile.read(4),byteorder='little')
            
            Framerate = (FrameCount - 1) / PlayRate
            Scene.render.fps = round(Framerate)
            Scene.render.fps_base = Scene.render.fps / Framerate
            Scene.frame_start = 0
            Scene.frame_end = FrameCount - 1
            
            loopCheck = False
            if self.loop_anim == "loopYes":
                loopCheck = True
            elif self.loop_anim == "loopAuto":
                if "_loop" in animfile.name:
                    loopCheck = True

            for x in range(FrameCount): 
                CurFile.seek(0xC+0x30*BoneCount*x)
                if loopCheck and x == FrameCount - 1:
                    CurFile.seek(0xC)
                Scene.frame_set(x)

                # Establish dictionary for all bones rather than index. Slower, but can be used for applying animations to different skeletons in future.
                BoneMats = {}
                for Bone in Arm.pose.bones:
                    BoneMats.update({Bone.name:mathutils.Matrix()})
                BoneMatsNoScale = BoneMats.copy()

                # Extract and store anim data
                for y in range(BoneCount):
                    Bone = Arm.pose.bones[y]

                    tmpQuat = struct.unpack('<ffff', CurFile.read(0x10))
                    tmpPos = struct.unpack('<fff', CurFile.read(0xC))
                    tmpFloat = struct.unpack('<f', CurFile.read(0x4))[0] #TODO: Figure out what this value actually does. Seems to always be different
                    tmpScl = struct.unpack('<fff', CurFile.read(0xC))
                    CurFile.read(4) # Always 1.0 as far as I've seen

                    if self.use_yx_orientation:
                        tmpPos = mathutils.Vector((tmpPos[2],tmpPos[0],tmpPos[1]))
                        tmpQuat = mathutils.Quaternion((tmpQuat[3],tmpQuat[2],tmpQuat[0],tmpQuat[1]))
                        if tmpScl != (0.0,0.0,0.0):
                            tmpScl = mathutils.Vector((tmpScl[2],tmpScl[0],tmpScl[1]))
                        else:
                            tmpScl = mathutils.Vector((1.0,1.0,1.0))
                    else:
                        tmpPos = mathutils.Vector((tmpPos[0],tmpPos[1],tmpPos[2]))
                        tmpQuat = mathutils.Quaternion((tmpQuat[3],tmpQuat[0],tmpQuat[1],tmpQuat[2]))
                        if tmpScl != (0.0,0.0,0.0):
                            tmpScl = mathutils.Vector((tmpScl[0],tmpScl[1],tmpScl[2]))
                        else:
                            tmpScl = mathutils.Vector((1.0,1.0,1.0))

                    BoneMat = mathutils.Matrix.LocRotScale(tmpPos, tmpQuat, tmpScl)
                    BoneMats.update({Bone.name:BoneMat})

                    BoneMatNoScale = mathutils.Matrix.LocRotScale(tmpPos, tmpQuat, mathutils.Vector((1.0,1.0,1.0)))
                    BoneMatsNoScale.update({Bone.name:BoneMatNoScale})  
                    
                ### APPLY TRANSFORMS ###
                
                # Method 1: BFS algorithm to go down the parent hierarchy calculating the unscaled position matrices.
                # Needs scene updates to be accurate. Keeps track of bone hierarchy level so scene updates only after each level rather than per bone.
                # More complex than stardard BFS algorithm, but HUUUUUUGE performance improvement by updating the scene less. 
                
                if self.scale_correct == 'accurate':
                    for y in root_bones(Arm):
                        queue = deque([(y, 0)])

                        CurrentLevel = 0
                        BonesInLevel = 1
                        BonesProcessed = 0
                        
                        while queue:
                            Bone, Level = queue.popleft()
                            Arm.data.bones[Bone.name].inherit_scale = 'ALIGNED'
                            if Level != CurrentLevel:   
                                CurrentLevel = Level
                                BonesProcessed = 1
                                BonesInLevel = len(queue) + 1
                            else:
                                BonesProcessed += 1

                            if self.use_yx_orientation:
                                ParentMat = mathutils.Matrix() @ mathutils.Matrix.Rotation(math.radians(-90.0), 4, 'X') @ mathutils.Matrix.Rotation(math.radians(-90.0), 4, 'Z')
                            else:
                                ParentMat = mathutils.Matrix()
                                
                            # Get unscaled transform matrix of parent bone and use that as basis to get the correct position
                            for z in reversed(Bone.parent_recursive):
                                ParentMat @= BoneMatsNoScale[z.name]

                            tmpPos, tmpQuat, tmpScl = BoneMats[Bone.name].decompose()

                            Bone.rotation_quaternion = Arm.convert_space(pose_bone=Bone,matrix = ParentMat @ ((mathutils.Quaternion(tmpQuat)).to_matrix().to_4x4()),from_space='POSE',to_space='LOCAL').to_quaternion()
                            Bone.location = Arm.convert_space(pose_bone=Bone,matrix = ParentMat @ ((mathutils.Matrix.Translation(tmpPos))),from_space='POSE',to_space='LOCAL').translation
                            Bone.scale = tmpScl

                            Bone.keyframe_insert('location')
                            Bone.keyframe_insert('rotation_quaternion')
                            Bone.keyframe_insert('scale')

                            for z in Bone.children:
                                queue.append((z, Level + 1))

                            if BonesProcessed == BonesInLevel: 
                                bpy.context.view_layer.update()

                # Method 2: Functions near identically to original plugin. Useful for reimporting custom animations from the old plugin (should not be used for default animations in most cases)
                elif self.scale_correct == 'legacy':
                    for y in range(BoneCount):
                        Bone = Arm.pose.bones[y]
                        if Bone.parent:
                            ParentMat = Bone.parent.matrix.copy()
                        elif self.use_yx_orientation:
                            ParentMat = mathutils.Matrix() @ mathutils.Matrix.Rotation(math.radians(-90.0), 4, 'X') @ mathutils.Matrix.Rotation(math.radians(-90.0), 4, 'Z')
                        else:
                            ParentMat = mathutils.Matrix()

                        tmpPos, tmpQuat, tmpScl = BoneMats[Bone.name].decompose()

                        Bone.rotation_quaternion = Arm.convert_space(pose_bone=Bone,matrix = ParentMat @ ((mathutils.Quaternion(tmpQuat)).to_matrix().to_4x4()),from_space='POSE',to_space='LOCAL').to_quaternion()
                        Bone.keyframe_insert('rotation_quaternion')

                        Bone.location = Arm.convert_space(pose_bone=Bone,matrix = ParentMat @ ((mathutils.Matrix.Translation(tmpPos))),from_space='POSE',to_space='LOCAL').translation
                        Bone.keyframe_insert('location')

                        Bone.scale = tmpScl
                        Bone.keyframe_insert('scale')

                else:
                    raise TypeError("None or invalid scale correction method.")
            
                if CurRootFile:
                    Bone = Arm.pose.bones[0]
                    CurRootFile.seek(0xC+0x30*x)
                    if loopCheck and x == FrameCount - 1:
                        CurRootFile.seek(0xC)
                    
                    tmpQuat = struct.unpack('<ffff', CurRootFile.read(0x10))
                    tmpPos = struct.unpack('<fff', CurRootFile.read(0xC))
                    tmpFloat = struct.unpack('<f', CurRootFile.read(0x4))[0]
                    tmpScl = struct.unpack('<fff', CurRootFile.read(0xC))
                    CurRootFile.read(4)

                    if self.use_yx_orientation:
                        tmpPos = mathutils.Vector((tmpPos[0],tmpPos[1],tmpPos[2]))
                        tmpQuat = mathutils.Quaternion((tmpQuat[3],tmpQuat[2],tmpQuat[0],tmpQuat[1]))
                        if tmpScl != (0.0,0.0,0.0):
                            tmpScl = mathutils.Vector((tmpScl[2],tmpScl[0],tmpScl[1]))
                        else:
                            tmpScl = mathutils.Vector((1.0,1.0,1.0))
                    else:
                        tmpPos = mathutils.Vector((tmpPos[0],tmpPos[1],tmpPos[2]))
                        tmpQuat = mathutils.Quaternion((tmpQuat[3],tmpQuat[0],tmpQuat[1],tmpQuat[2]))
                        if tmpScl != (0.0,0.0,0.0):
                            tmpScl = mathutils.Vector((tmpScl[0],tmpScl[1],tmpScl[2]))
                        else:
                            tmpScl = mathutils.Vector((1.0,1.0,1.0))
                    
                    BoneMat = mathutils.Matrix.LocRotScale(tmpPos, tmpQuat, tmpScl)
                    if self.use_yx_orientation:
                        BoneMat @= mathutils.Matrix.Rotation(math.radians(-90.0), 4, 'X') @ mathutils.Matrix.Rotation(math.radians(-90.0), 4, 'Z')
                    
                    Bone.matrix = BoneMat 
                    Bone.keyframe_insert('rotation_quaternion')
                    Bone.keyframe_insert('location')
                    Bone.keyframe_insert('scale')
            
            if CurRootFile:
                CurRootFile.close()
                del CurRootFile   
                
            CurFile.close()
            del CurFile
        
        # Reset frame and mode 
        Scene.frame_current = CurrentFrame
        utils_set_mode(CurrentMode)
        
        return {'FINISHED'}

def root_bones(Arm):
    return [Bone for Bone in Arm.pose.bones if not Bone.parent]

def utils_set_mode(mode):
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode=mode, toggle=False)

def menu_func_import(self, context):
    self.layout.operator(HedgeEngineAnimation.bl_idname, text="HE2 Decompressed Animation (.outanim)")

def register():
    bpy.utils.register_class(HedgeEngineAnimation)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
    bpy.utils.unregister_class(HedgeEngineAnimation)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)

if __name__ == "__main__":
    register()