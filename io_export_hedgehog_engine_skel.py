bl_info = {
    "name": "Hedgehog Engine 2 Skeleton Export",
    "author": "WistfulHopes",
    "version": (1, 11, 0),
    "blender": (3, 3, 0),
    "location": "File > Import-Export",
    "description": "A script to export skeletons for Hedgehog Engine 2 games",
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
import binascii
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
     
def offset_table(offset):
    offset_bits_2 = "{0:b}".format((offset) >> 2)
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
    def __init__(self, Arm, Bone, useYX):
        self.pos = ()
        self.rot = ()
        Mat = Bone.matrix_local
        if Bone.parent:
            Mat = Bone.parent.matrix_local.inverted() @ Bone.matrix_local
        Pos = Mat.translation
        Rot = Mat.to_quaternion()
        if useYX:
            if not Bone.parent:
                Rot @= mathutils.Quaternion((0.5,0.5,0.5,0.5))
            self.pos = (Pos[1], Pos[2], Pos[0])
            self.rot = (Rot[2], Rot[3], Rot[1], Rot[0])
        else:
            self.pos = (Pos[0], Pos[1], Pos[2])
            self.rot = (Rot[1], Rot[2], Rot[3], Rot[0])

class MoveArray:
    def __init__(self, Arm, useYX):
        self.parent_indices = []
        self.name = []
        self.transform = []
        for x in range(len(Arm.pose.bones)):
            if (Arm.pose.bones[x].parent):
                self.parent_indices.append(Arm.pose.bones.find(Arm.pose.bones[x].parent.name))
            else:
                self.parent_indices.append(65535)
            self.name.append(bytes(Arm.pose.bones[x].name, 'ascii') + b'\x00')
            self.transform.append(BoneTransform(Arm, Arm.pose.bones[x].bone,useYX))

class HedgeEngineSkelExport(bpy.types.Operator, ExportHelper):
    bl_idname = "custom_export_scene.hedgeengskel"
    bl_label = "export"
    filename_ext = ".pxd"
    filter_glob: StringProperty(
            default="*.pxd",
            options={'HIDDEN'},
            )
    filepath: StringProperty(subtype='FILE_PATH',)
    files: CollectionProperty(type=bpy.types.PropertyGroup)
    
    use_yx_orientation: BoolProperty(
        name="Use YX Bone Orientation",
        description="If your skeleton was imported from XZ to YX to function better in Blender, use this option to switch bones back from YX to XZ (important for in-game IK)",
        default=False,
        )
    
    def draw(self, context):
        layout = self.layout
        uiBoneBox = layout.box()
        uiBoneBox.label(text="Armature Settings",icon="ARMATURE_DATA")
        uiBoneBox.prop(self, "use_yx_orientation")
        
    def execute(self, context):
        Arm = bpy.context.active_object
        Scene = bpy.context.scene
        if not Arm:
            raise ValueError("No active object. Please select an armature as your active object.")
        if Arm.type != 'ARMATURE':
            raise TypeError(f"Active object \"{Arm.name}\" is not an armature. Please select an armature.")
            
        with open(self.filepath,"wb") as CurFile:
            magic = bytes('KSXP', 'ascii')
            
            CurFile.write(magic)
            CurFile.write(struct.pack('<i', 512))
            useYX = self.use_yx_orientation
            Array = MoveArray(Arm, useYX)
            
            ParentOffset = 104
            Null = 0
            
            CurFile.write(ParentOffset.to_bytes(8, 'little'))
            CurFile.write(len(Arm.pose.bones).to_bytes(8, 'little'))
            CurFile.write(len(Arm.pose.bones).to_bytes(8, 'little'))
            CurFile.write(Null.to_bytes(8, 'little'))
            
            NameOffset = ParentOffset + (len(Arm.pose.bones) + 1) * 2
            if NameOffset % 0x10 != 0:
                NameOffset += 0x10 - NameOffset % 0x10
            
            CurFile.write(NameOffset.to_bytes(8, 'little'))
            CurFile.write(len(Arm.pose.bones).to_bytes(8, 'little'))
            CurFile.write(len(Arm.pose.bones).to_bytes(8, 'little'))
            CurFile.write(Null.to_bytes(8, 'little'))
            
            MatrixOffset = NameOffset + len(Arm.pose.bones) * 0x10
            
            CurFile.write(MatrixOffset.to_bytes(8, 'little'))
            CurFile.write(len(Arm.pose.bones).to_bytes(8, 'little'))
            CurFile.write(len(Arm.pose.bones).to_bytes(8, 'little'))
            CurFile.write(Null.to_bytes(8, 'little'))
            
            for x in range(len(Arm.pose.bones)):
                ParentIndex = Array.parent_indices[x].to_bytes(2, 'little')
                CurFile.write(ParentIndex)

            if CurFile.tell() % 0x10 != 0:
                for x in range(0x10 - CurFile.tell() % 0x10):
                    CurFile.write(Null.to_bytes(1, 'little'))
                
            NameDataOffset = MatrixOffset + len(Arm.pose.bones) * 0x30
            
            for x in range(len(Arm.pose.bones)):
                CurFile.write(NameDataOffset.to_bytes(16, 'little'))
                NameDataOffset += len(Array.name[x])
            
            for x in range(len(Arm.pose.bones)):
                CurFile.write(struct.pack('<f', Array.transform[x].pos[0]))
                CurFile.write(struct.pack('<f', Array.transform[x].pos[1]))
                CurFile.write(struct.pack('<f', Array.transform[x].pos[2]))
                CurFile.write(struct.pack('<f', 0))
                CurFile.write(struct.pack('<f', Array.transform[x].rot[0]))
                CurFile.write(struct.pack('<f', Array.transform[x].rot[1]))
                CurFile.write(struct.pack('<f', Array.transform[x].rot[2]))
                CurFile.write(struct.pack('<f', Array.transform[x].rot[3]))
                CurFile.write(struct.pack('<f', 1))
                CurFile.write(struct.pack('<f', 1))
                CurFile.write(struct.pack('<f', 1))
                CurFile.write(struct.pack('<f', 0))
            
            StringTableSize = 0
            
            for x in range(len(Arm.pose.bones)):
                CurFile.write(Array.name[x])
                StringTableSize += len(Array.name[x])
            
            if CurFile.tell() % 4 != 0:
                for x in range(4 - CurFile.tell() % 4):
                    CurFile.write(Null.to_bytes(1, 'little'))
                    StringTableSize += 1
            
            OffsetTableSize = 0
           
            bit = 66
            CurFile.write(bit.to_bytes(1, 'little'))
            bit = 72
            CurFile.write(bit.to_bytes(1, 'little'))
            CurFile.write(bit.to_bytes(1, 'little'))
            
            OffsetTableSize += 3
            
            name_offset_bits = offset_table(NameOffset - ParentOffset + 0x20)
            name_offset_buffer = bytearray()
            index = 0
            while index < len(name_offset_bits):
                name_offset_buffer.append( int(name_offset_bits[index:index+8], 2))
                index += 8
            
            OffsetTableSize += len(name_offset_buffer)
            
            CurFile.write(name_offset_buffer)
            
            inbyte = 68
            for x in range(len(Arm.pose.bones) - 1):
                CurFile.write(inbyte.to_bytes(1, 'little'))
                OffsetTableSize += 1
            
            CurFile.write(Null.to_bytes(1, 'little'))
            OffsetTableSize += 1
            
            if CurFile.tell() % 4 != 0:
                for x in range(4 - CurFile.tell() % 4):
                    CurFile.write(Null.to_bytes(1, 'little'))
                    OffsetTableSize += 1
        
        with open(self.filepath,"rb+") as CurFile:
            Content = CurFile.read()
            CurFile.seek(0, 0)
            
            bin_magic = bytes('BINA210L', 'ascii')
            CurFile.write(bin_magic)
            CurFile.write(struct.pack('<i', len(Content)+0x40))
            CurFile.write(struct.pack('<i', 1))
            
            data_magic = bytes('DATA', 'ascii')
            CurFile.write(data_magic)
            CurFile.write(struct.pack('<i', len(Content)+0x30))
            CurFile.write(struct.pack('<i', MatrixOffset + len(Arm.pose.bones) * 0x30))
            CurFile.write(struct.pack('<i', StringTableSize))
            CurFile.write(struct.pack('<i', OffsetTableSize))
            CurFile.write(struct.pack('<i', 0x18))
            CurFile.write(Null.to_bytes(24, 'little'))
            CurFile.write(Content)
            
        return {'FINISHED'}
    
def menu_func_export(self, context):
    self.layout.operator(HedgeEngineSkelExport.bl_idname, text="Hedgehog Engine Skeleton Export (.pxd)")
        
def register():
    bpy.utils.register_class(HedgeEngineSkelExport)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)
    
def unregister():
    bpy.utils.unregister_class(HedgeEngineSkelExport)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
        
if __name__ == "__main__":
    register()
