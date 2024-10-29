"""
Pass raw byte-streams to and from DLL for ACL compression and decompression
DLL Source: https://github.com/WistfulHopes/FrontiersAnimDecompress/

See bottom of file for struct of different byte streams
"""


import bpy
import io
import ctypes


class ACLCompressor:
    class MemoryBuffer(ctypes.Structure):
        _fields_ = [("offset", ctypes.POINTER(ctypes.c_ubyte)),
                    ("size", ctypes.c_size_t)]

    path = bpy.utils.user_resource('SCRIPTS', path='Addons\\FrontiersAnimationTools\\FrontiersAnimDecompress')
    name = "FrontiersAnimDecompress.dll"

    def __init__(self):
        self.dll = ctypes.CDLL(f"{self.path}\\{self.name}")
        self.dll.decompress.restype = self.MemoryBuffer
        self.dll.compress.restype = self.MemoryBuffer


def decompress(compressed_buffer):
    comp = ACLCompressor()
    if len(compressed_buffer):
        decompressed_buffer_ptr = comp.dll.decompress(compressed_buffer)
        if not decompressed_buffer_ptr.size:
            return io.BytesIO()
        decompressed_stream = bytes(decompressed_buffer_ptr.offset[:decompressed_buffer_ptr.size])
        return io.BytesIO(decompressed_stream)
    else:
        return io.BytesIO()


def compress(uncompressed_buffer):
    comp = ACLCompressor()
    if len(uncompressed_buffer):
        compressed_buffer_ptr = comp.dll.compress(uncompressed_buffer)
        if not compressed_buffer_ptr.size:
            return io.BytesIO()
        compressed_stream = bytes(compressed_buffer_ptr.offset[:compressed_buffer_ptr.size])
        return io.BytesIO(compressed_stream)
    else:
        return io.BytesIO()


"""
# ------------------------------------
# ----- Compressed buffer struct -----
# ------------------------------------

acl_chunk_size  # uint32, total size of buffer including this section
acl_hash        # int32

acl_tag         # int32, Enum, should be 0xAC11AC11 (compressed_tracks)
https://github.com/nfrechette/acl/blob/976ff051048477f2281c7d3609fddf0b3cba2c2d/includes/acl/core/buffer_tag.h#L49

acl_version     # uint16, Enum, should be 7 (v02_00_00)
https://github.com/nfrechette/acl/blob/976ff051048477f2281c7d3609fddf0b3cba2c2d/includes/acl/core/compressed_tracks_version.h#L71

acl_unknown1    # byte, Always 0, Padding?

acl_track_type  # byte, Enum, should be 12 (qvvf)
https://github.com/nfrechette/acl/blob/976ff051048477f2281c7d3609fddf0b3cba2c2d/includes/acl/core/track_types.h#L68

track_count # uint32, Bone count if skeletal, otherwise always 1
frame_count # uint32
frame_rate  # float32

for acl_data in range(acl_chunk_size - 0x1C): # string of acl compressed data
    acl_data    # byte
"""


"""
# ------------------------------------
# ---- Decompressed buffer struct ----
# ------------------------------------

anim_duration   # float32
frame_rate      # float32
frame_count     # uint32
track_count     # uint32, Bone count if skeletal, otherwise always 1

for frame in range(frame_count):
    for bone in range(track_count):
        # Quaternion Rotation
        quat_x  # float32, Rotation X
        quat_y  # float32, Rotation Y
        quat_z  # float32, Rotation Z
        quat_w  # float32, Rotation W

        # Location
        loc_x   # float32, Location X
        loc_y   # float32, Location Y
        loc_z   # float32, Location Z
        loc_w   # float32, Bone Length After Scale

        # Scale
        scale_x # float32, Scale X
        scale_y # float32, Scale Y
        scale_z # float32, Scale Z
        scale_w # float32, Unknown/Unneeded, Always 1.0
"""
