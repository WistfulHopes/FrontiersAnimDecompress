bl_info = {
    "name": "Hedgehog Engine 2 Decompressed Animation Import",
    "author": "Turk, WistfulHopes, AdelQ",
    "version": (1, 1, 0),
    "blender": (3, 3, 0),
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
from collections import deque

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

    scale_correct: EnumProperty(
        items=[
            ("accurate", "Accurate", "Correct bone relocations as a result of parent scaling", 1),
            #("fast", "Fast", "Correct bone relocations, but don't update scene during relocations (slightly less accurate but visibly serviceable)", 2), #Not yet working right
            ("legacy", "Legacy", "Import using the original plugin's method (inaccurate, but good for revisiting old .outanim exports)", 3),
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
            ("loopAuto", "Auto", "Automatically determine if the animation is a loop based on the file name", 1),
            ("loopYes", "Yes", "Treat the animation as a looping animation, shifting the start frame by +1", 2),
            ("loopNo", "No", "Play the whole animation from start to end. May result in hitching during viewport playback if it's supposed to be a loop, but still recommended for batch animation conversions", 3),
            ],
        name="Loop",
        description="Determines if this animation is meant to be a loop. This shifts the start frame by one to prevent hitching during playback (start frame still needs to be shifted back before export)",
        default="loopNo",
        )

    def draw(self, context):
        layout = self.layout
        uiSceneBox = layout.box()
        uiSceneBox.label(text="Animation Settings",icon="ACTION")
        uiSceneRowLoop = uiSceneBox.row()
        uiSceneRowLoop.label(text="Is Loop?")
        uiSceneRowLoop.prop(self, "loop_anim", text="")

        uiBoneBox = layout.box()
        uiBoneBox.label(text="Armature Settings",icon="ARMATURE_DATA")
        uiScaleCorrectRow = uiBoneBox.row()
        uiScaleCorrectRow.label(text="Scale Mode:")
        uiScaleCorrectRow.prop(self, "scale_correct", text="")

        uiOrientationRow = uiBoneBox.row()
        uiOrientationRow.prop(self, "use_yx_orientation",)


    def execute(self, context):
        for animfile in self.files:
            Arm = bpy.context.active_object
            if not Arm:
                raise ValueError("No active object. Please select an armature as your active object.")
            Scene = bpy.context.scene
            Mode = "Accurate"

            if Arm.type == 'ARMATURE':

                CurFile = open(os.path.join(os.path.dirname(self.filepath), animfile.name),"rb")

                Arm.animation_data_create()
                action = bpy.data.actions.new(os.path.basename(animfile.name))
                Arm.animation_data.action = action
                
                loopCheck = False
                if self.loop_anim == "loopYes":
                    loopCheck = True
                elif self.loop_anim == "loopAuto":
                    if "_loop" in animfile.name:
                        loopCheck = True
                
                PlayRate = struct.unpack('<f', CurFile.read(0x4))[0]
                FrameCount = int.from_bytes(CurFile.read(4),byteorder='little')
                BoneCount = int.from_bytes(CurFile.read(4),byteorder='little')

                Scene.render.fps = int((FrameCount - 1) / PlayRate)
                if loopCheck:
                    Scene.frame_start = 1
                else:
                    Scene.frame_start = 0
                Scene.frame_end = FrameCount - 1

                CurrentFrame = Scene.frame_current
                CurrentMode = bpy.context.mode

                utils_set_mode("POSE")

                for Bone in Arm.data.bones:
                    Bone.inherit_scale = "ALIGNED"

                for x in range(FrameCount): #FrameCount
                    CurFile.seek(0xC+0x30*BoneCount*x)
                    Scene.frame_set(x)

                    # Make entire dictionary with all bones beforehand in case BoneCount variable is less than actual bone count
                    # (Useful for things like ModelFBX Skeletons with extra bones like "Mesh_Body")
                    BoneMats = {}
                    for y in Arm.pose.bones:
                        BoneMats.update({y.name:mathutils.Matrix()})
                    BoneMatsNoScale = BoneMats.copy()

                    # Extract and store anim data
                    for y in range(BoneCount):
                        Bone = Arm.pose.bones[y]

                        tmpQuat = struct.unpack('<ffff', CurFile.read(0x10))
                        tmpPos = struct.unpack('<fff', CurFile.read(0xC))
                        tmpFloat = struct.unpack('<f', CurFile.read(0x4)) #TODO: Figure out what this value actually does. Seems to always be different
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

                    # Method 1: BFS Algorithm to go down the parent hierarchy calculating the unscaled position matrices
                    if self.scale_correct == "accurate":
                        for y in root_bones(Arm):
                            queue = deque([(y, 0)])

                            CurrentLevel = 0
                            BonesInLevel = 1
                            BonesProcessed = 0

                            while queue:
                                Bone, Level = queue.popleft()
                                Arm.data.bones[Bone.name].inherit_scale = 'ALIGNED'
                                if Level != CurrentLevel:   # Track level of bone hierarchy, only updating scene once an entire level is cleared instead of for each bone (HUGE performance improvement)
                                    #bpy.context.view_layer.update() # 33% faster without this update, potentially unforseen consequences :P
                                    CurrentLevel = Level
                                    BonesProcessed = 1
                                    BonesInLevel = len(queue) + 1
                                else:
                                    BonesProcessed += 1

                                if self.use_yx_orientation:
                                    ParentMat = mathutils.Matrix() @ mathutils.Matrix.Rotation(math.radians(-90.0), 4, 'X') @ mathutils.Matrix.Rotation(math.radians(-90.0), 4, 'Z')
                                else:
                                    ParentMat = mathutils.Matrix()

                                for z in reversed(Bone.parent_recursive):
                                    ParentMat @= BoneMatsNoScale[z.name]

                                tmpPos, tmpQuat, tmpScl = BoneMats[Bone.name].decompose() # Use scaled transform of active bone,

                                Bone.rotation_quaternion = Arm.convert_space(pose_bone=Bone,matrix = ParentMat @ ((mathutils.Quaternion(tmpQuat)).to_matrix().to_4x4()),from_space='POSE',to_space='LOCAL').to_quaternion()
                                Bone.location = Arm.convert_space(pose_bone=Bone,matrix = ParentMat @ ((mathutils.Matrix.Translation(tmpPos))),from_space='POSE',to_space='LOCAL').translation
                                Bone.scale = tmpScl

                                Bone.keyframe_insert("location")
                                Bone.keyframe_insert("rotation_quaternion")
                                Bone.keyframe_insert("scale")

                                for z in Bone.children:
                                    queue.append((z, Level + 1))

                                if BonesProcessed == BonesInLevel: # Update once entire level is processed
                                    bpy.context.view_layer.update()



                    # Method 2: Calculate location offset using `Bone.parent.matrix`. Does not require updates but may end up slightly inaccurate.
                    # WIP, not working right. It is not expected to be 100% accurate, but should at least look visually similar from afar.
                    elif self.scale_correct == "fast":
                        Offsets = {}

                        # Calculate and store bone offsets between scaled and unscaled parents, negate any offsets from the parents in the process (hence why its using BFS to go from top to bottom)
                        # This loop is whats causing issues. Offset calculations seem somewhat accurate for most bones, but some like the toes and cuffs don't work right for some reason.
                        for y in root_bones(Arm):
                            queue = deque([y])
                            while queue:
                                Bone = queue.popleft()
                                BoneMat = BoneMats[Bone.name]

                                ParentMat = mathutils.Matrix()
                                ParentMatNoScale = mathutils.Matrix()

                                for z in reversed(Bone.parent_recursive):
                                    ParentMat @= BoneMats[z.name]
                                    ParentMatNoScale @= BoneMatsNoScale[z.name]

                                BoneLoc = (ParentMat @ BoneMat).translation
                                BoneLocNoScale = (ParentMatNoScale @ BoneMat).translation
                                BoneDif = BoneLoc - BoneLocNoScale

                                if Bone.parent:
                                    BoneDif -= Offsets[Bone.parent.name]
                                    Offsets.update({Bone.name:BoneDif})
                                else:
                                    Offsets.update({Bone.name:BoneDif})

                                for z in Bone.children:
                                    queue.append(z)

                        # Apply Transforms like legacy mode, section should be fine
                        for y in range(BoneCount):
                            Bone = Arm.pose.bones[y]
                            if Bone.parent:
                                ParentMat = Bone.parent.matrix.copy()
                            else:
                                ParentMat = mathutils.Matrix()

                            tmpPos, tmpQuat, tmpScl = BoneMats[Bone.name].decompose()

                            Bone.rotation_quaternion = Arm.convert_space(pose_bone=Bone,matrix = ParentMat @ ((mathutils.Quaternion(tmpQuat)).to_matrix().to_4x4()),from_space='POSE',to_space='LOCAL').to_quaternion()
                            Bone.keyframe_insert("rotation_quaternion")

                            Bone.location = Arm.convert_space(pose_bone=Bone,matrix = ParentMat @ ((mathutils.Matrix.Translation(tmpPos))),from_space='POSE',to_space='LOCAL').translation
                            #Bone.location = Arm.convert_space(pose_bone=Bone,matrix = mathutils.Matrix.Translation((ParentMat @ mathutils.Matrix.Translation(tmpPos)).translation - Offset),from_space='POSE',to_space='LOCAL').translation
                            Bone.keyframe_insert("location")

                            Bone.scale = tmpScl
                            Bone.keyframe_insert("scale")

                        # Apply global offsets in separate loop after scene update. Unfortunately needed, but only needed once per frame and isn't too much of a slowdown
                        bpy.context.view_layer.update() # TODO: Try to avoid a scene update
                        for y in range(BoneCount):
                            Bone = Arm.pose.bones[y]
                            Offset = Offsets[Bone.name]
                            Bone.matrix.translation = Bone.matrix.translation - Offset
                            Bone.keyframe_insert("location")



                    # Method 3: Functions identically to original plugin. Useful for reimporting custom animations from the old plugin (should not be used for default animations)
                    elif self.scale_correct == "legacy":
                        for y in range(BoneCount):
                            Bone = Arm.pose.bones[y]
                            if Bone.parent:
                                ParentMat = Bone.parent.matrix.copy()
                            else:
                                ParentMat = mathutils.Matrix()

                            tmpPos, tmpQuat, tmpScl = BoneMats[Bone.name].decompose()

                            Bone.rotation_quaternion = Arm.convert_space(pose_bone=Bone,matrix = ParentMat @ ((mathutils.Quaternion(tmpQuat)).to_matrix().to_4x4()),from_space='POSE',to_space='LOCAL').to_quaternion()
                            Bone.keyframe_insert("rotation_quaternion")

                            Bone.location = Arm.convert_space(pose_bone=Bone,matrix = ParentMat @ ((mathutils.Matrix.Translation(tmpPos))),from_space='POSE',to_space='LOCAL').translation
                            Bone.keyframe_insert("location")

                            Bone.scale = tmpScl
                            Bone.keyframe_insert("scale")

                    else:
                        raise TypeError("Invalid scale correction method.")




                Scene.frame_current = CurrentFrame
                utils_set_mode(CurrentMode)
                CurFile.close()
                del CurFile

            else:
                raise TypeError(f"Active object \"{Arm.name}\" is not an armature. Please select an armature.")
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
