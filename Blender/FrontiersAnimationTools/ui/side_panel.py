import bpy
from bpy.props import (BoolProperty,
                       FloatProperty,
                       IntProperty,
                       StringProperty,
                       EnumProperty,
                       CollectionProperty,
                       PointerProperty)
from ..animation.batch_export import FrontiersAnimBatchExport
from .func_ops import (MakeFrontiersActionActive,
                       ClearFrontiersFakeUser,
                       MakeFrontiersActionPersistent,
                       SetTransformModes,
                       filter_actions)


class FrontiersAnimationPanel(bpy.types.Panel):
    bl_label = "Frontiers Animation"
    bl_idname = "OBJECT_PT_frontiers_tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Animation'

    def draw_header(self, context):
        self.layout.label(icon='ARMATURE_DATA')

    def draw(self, context):
        layout = self.layout

        export_box = layout.box()
        export_box.label(text="Export Settings", icon='EXPORT')
        export_box.label(text=f"Export {len(filter_actions(bpy.data.actions, context))} animations")

        export_box.operator(
            FrontiersAnimBatchExport.bl_idname,
            text="Batch Export",
            icon='EXPORT',
        )

        skel_box = layout.box()
        skel_box.label(text="Skeleton Settings", icon='OUTLINER_OB_ARMATURE')

        skel_box.operator(
            SetTransformModes.bl_idname,
            text="Fix Transform Modes",
            icon='BONE_DATA',
        )

        action_box = layout.box()
        action_box.label(text="Action Settings", icon='ACTION')

        action_box.operator(
            MakeFrontiersActionPersistent.bl_idname,
            text="Make Actions Persistent",
            icon='FAKE_USER_ON',
        )
        action_box.operator(
            ClearFrontiersFakeUser.bl_idname,
            text="Remove Persistence",
            icon='FAKE_USER_OFF',
        )

        filter_label_row = action_box.row()
        filter_label_row.label(text="Filter actions by name:")

        name_prefix_row = action_box.row()
        name_prefix_row.column().label(text="Starts with:")
        name_prefix_row.column().prop(context.scene, 'frontiers_anim_prefix', text="")

        name_filter_row = action_box.row()
        name_filter_row.column().label(text="Contains:")
        name_filter_row.column().prop(context.scene, 'frontiers_anim_contains', text="")

        action_list_box = action_box.box()

        action_grid = action_list_box.grid_flow(row_major=True, columns=3, align=False)

        action_grid.label(text="Action Name", icon='ACTION_TWEAK')
        action_grid.label(icon='EXPORT')
        act_col = action_grid.column()
        act_col.label(icon='SCENE_DATA')

        if bpy.data.actions:
            # Slows down with lots of actions. Seems like Blender in general just does that?
            for action in bpy.data.actions:
                if action.name.startswith(context.scene.frontiers_anim_prefix):
                    if context.scene.frontiers_anim_contains in action.name:
                        action_grid.prop(action, 'name', text="")
                        action_grid.prop(action, 'pxd_export', text="")
                        ma = action_grid.operator(
                                    MakeFrontiersActionActive.bl_idname,
                                    text="",
                                    icon='CON_ACTION'
                        )

                        ma.anim_name = action.name

        else:
            action_list_box.label(text="No actions in scene...")


def register():
    bpy.utils.register_class(FrontiersAnimationPanel)
    bpy.utils.register_class(MakeFrontiersActionActive)
    bpy.utils.register_class(ClearFrontiersFakeUser)
    bpy.utils.register_class(MakeFrontiersActionPersistent)
    bpy.utils.register_class(SetTransformModes)

    bpy.types.Scene.frontiers_anim_prefix = StringProperty(
        name="Action Prefix",
        default="",
        description="Filter by action names that start with this text (ex: \"chr_sonic@\")",
        options={'TEXTEDIT_UPDATE'}
    )

    bpy.types.Scene.frontiers_anim_contains = StringProperty(
        name="Action Contains",
        default="",
        description="Filter by action names that contain this text anywhere (ex: \"combo\")",
        options={'TEXTEDIT_UPDATE'}
    )


def unregister():
    bpy.utils.unregister_class(FrontiersAnimationPanel)
    bpy.utils.unregister_class(MakeFrontiersActionActive)
    bpy.utils.unregister_class(ClearFrontiersFakeUser)
    bpy.utils.unregister_class(MakeFrontiersActionPersistent)
    bpy.utils.unregister_class(SetTransformModes)

    del bpy.types.Scene.frontiers_anim_prefix
    del bpy.types.Scene.frontiers_anim_contains
