# Pass raw byte-streams to DLL for ACL compression and decompression
# DLL Source: https://github.com/AdelQue/FrontiersAnimDecompress/

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
