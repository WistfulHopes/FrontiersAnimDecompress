# FrontiersAnimDecompress
 Decompresses Sonic Frontiers animations. Utilizes https://github.com/nfrechette/acl for decompressing. Modified version of https://github.com/Turk645/Hedgehog-Engine-2-Mesh-Blender-Importer for importing.


## Options
### Animation Settings:

### Skeleton Settings:
- YX Bone Orientation
  - Determines the orientation of your basis skeleton. If your original skeleton was set to import with YX orientation, then all animation imports and exports should have this option checked. 
  - ![XZ](https://github.com/AdelQue/FrontiersAnimDecompress/assets/10789282/4c278d71-a853-41cf-8525-3d9b17e1778b "XZ (Frontiers Default)")
  - ![YX](https://github.com/AdelQue/FrontiersAnimDecompress/assets/10789282/6e4393e5-b66d-4ae9-a452-4de960ab1229 "YX (Blender Preferred Bone Orientation")
- Scale Mode
  - Accurate
    - Slower animation import, but will correct the scale types and positions of all bones to be as identical as possible to how it would appear ingame. Should be used wherever possible.
    - ![Accurate](https://github.com/AdelQue/FrontiersAnimDecompress/assets/10789282/8df0052a-ae32-41ef-8a81-c6fac299b2b3 "Accurate")
  - Legacy
    - Method from older versions of the addon that would only import raw data. Though fast, it should only ever be used to reimport scaled animations that were exported with the old version of the addon. 
    - ![Legacy](https://github.com/AdelQue/FrontiersAnimDecompress/assets/10789282/c5da9318-95d0-4265-8107-7617fd526f76 "Legacy")


