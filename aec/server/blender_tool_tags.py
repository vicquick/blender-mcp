"""Tag taxonomy for blender-mcp, derived from the server's own section headers
(same convention as qgis-mcp's qgis_tool_tags.py).

Single source of truth for the fastmcp Visibility API. 'escape' carries the
escape hatches (execute_code, discovery, toolset switching, rules search), so
every preset must include it or an agent is stranded with no way back.
"""

TOOL_TAGS = {
    # ── Escape hatches — every preset below MUST include this tag ──────
    'ping': 'escape',
    'get_blender_info': 'escape',
    'execute_code': 'escape',
    'search_tools': 'escape',
    'describe_tool': 'escape',
    'run_tool': 'escape',
    'set_toolset': 'escape',
    'search_rules': 'escape',

    # ── Scene & System ──────────────────────────────────────────────────
    'get_scene_info': 'scene',
    'get_object_info': 'scene',
    'get_viewport_screenshot': 'scene',

    # ── Objects ───────────────────────────────────────────────────────
    'create_object': 'objects',
    'delete_objects': 'objects',
    'duplicate_object': 'objects',
    'select_objects': 'objects',
    'set_active_object': 'objects',
    'transform_object': 'objects',
    'set_parent': 'objects',
    'clear_parent': 'objects',
    'rename_object': 'objects',
    'list_objects': 'objects',

    # ── Mesh & Modifiers ─────────────────────────────────────────────
    'add_modifier': 'mesh',
    'remove_modifier': 'mesh',
    'apply_modifier': 'mesh',
    'list_modifiers': 'mesh',
    'set_modifier_property': 'mesh',
    'boolean_operation': 'mesh',
    'get_mesh_data': 'mesh',
    'set_smooth_shading': 'mesh',

    # ── Materials ─────────────────────────────────────────────────────
    'create_material': 'materials',
    'assign_material': 'materials',
    'edit_material': 'materials',
    'list_materials': 'materials',
    'remove_material': 'materials',
    'add_texture_node': 'materials',
    'create_node_material': 'materials',

    # ── Lighting ──────────────────────────────────────────────────────
    'create_light': 'lighting',
    'edit_light': 'lighting',
    'set_world_hdri': 'lighting',
    'set_world_color': 'lighting',
    'list_lights': 'lighting',

    # ── Camera ────────────────────────────────────────────────────────
    'create_camera': 'camera',
    'set_active_camera': 'camera',
    'edit_camera': 'camera',
    'set_camera_dof': 'camera',
    'look_at': 'camera',

    # ── Rendering ─────────────────────────────────────────────────────
    'set_render_engine': 'rendering',
    'set_render_settings': 'rendering',
    'render_image': 'rendering',
    'render_animation': 'rendering',
    'get_render_settings': 'rendering',

    # ── Animation ─────────────────────────────────────────────────────
    'insert_keyframe': 'animation',
    'delete_keyframe': 'animation',
    'set_frame': 'animation',
    'set_frame_range': 'animation',
    'get_keyframes': 'animation',
    'set_interpolation': 'animation',

    # ── Collections ───────────────────────────────────────────────────
    'create_collection': 'collections',
    'delete_collection': 'collections',
    'move_to_collection': 'collections',
    'set_collection_visibility': 'collections',
    'list_collections': 'collections',

    # ── File Operations ───────────────────────────────────────────────
    'save_file': 'file_io',
    'open_file': 'file_io',
    'export_file': 'file_io',
    'import_file': 'file_io',
    'new_file': 'file_io',

    # ── UV ────────────────────────────────────────────────────────────
    'smart_uv_project': 'uv',
    'uv_unwrap': 'uv',
    'list_uv_maps': 'uv',

    # ── BIM: Project ──────────────────────────────────────────────────
    'bim_create_project': 'bim_authoring',
    'bim_load_project': 'bim_authoring',
    'bim_save_project': 'bim_authoring',
    'bim_get_project_info': 'bim_authoring',
    'bim_set_units': 'bim_authoring',

    # ── BIM: Spatial Structure ────────────────────────────────────────
    'bim_create_spatial_element': 'bim_authoring',
    'bim_get_spatial_tree': 'bim_authoring',
    'bim_assign_container': 'bim_authoring',
    'bim_remove_container': 'bim_authoring',
    'bim_set_default_container': 'bim_authoring',
    'bim_get_container_elements': 'bim_authoring',

    # ── BIM: Elements ─────────────────────────────────────────────────
    'bim_add_wall': 'bim_authoring',
    'bim_add_slab': 'bim_authoring',
    'bim_add_column': 'bim_authoring',
    'bim_add_beam': 'bim_authoring',
    'bim_add_door': 'bim_authoring',
    'bim_add_window': 'bim_authoring',
    'bim_add_stair': 'bim_authoring',
    'bim_remove_element': 'bim_authoring',

    # ── BIM: Geometry ─────────────────────────────────────────────────
    'bim_add_opening': 'bim_authoring',
    'bim_add_filling': 'bim_authoring',
    'bim_join_walls': 'bim_authoring',
    'bim_align_element': 'bim_authoring',
    'bim_edit_placement': 'bim_authoring',

    # ── BIM: Materials ────────────────────────────────────────────────
    'bim_add_material': 'bim_authoring',
    'bim_assign_material': 'bim_authoring',
    'bim_add_material_layer_set': 'bim_authoring',
    'bim_add_material_profile_set': 'bim_authoring',
    'bim_list_materials': 'bim_authoring',

    # ── BIM: Types ────────────────────────────────────────────────────
    'bim_create_type': 'bim_authoring',
    'bim_assign_type': 'bim_authoring',
    'bim_list_types': 'bim_authoring',
    'bim_get_type_info': 'bim_authoring',

    # ── BIM: Georeference ─────────────────────────────────────────────
    'bim_set_georeferencing': 'bim_authoring',
    'bim_set_true_north': 'bim_authoring',
    'bim_get_georeferencing': 'bim_authoring',

    # ── BIM: Properties ───────────────────────────────────────────────
    'bim_add_pset': 'bim_properties',
    'bim_get_psets': 'bim_properties',
    'bim_add_qto': 'bim_properties',
    'bim_get_attributes': 'bim_properties',
    'bim_edit_attribute': 'bim_properties',
    'bim_query_elements': 'bim_properties',

    # ── BIM: Classification ───────────────────────────────────────────
    'bim_add_classification': 'bim_classification',
    'bim_classify_element': 'bim_classification',
    'bim_list_classifications': 'bim_classification',
    'bim_get_element_classifications': 'bim_classification',

    # ── BIM: Cost (5D) ────────────────────────────────────────────────
    'bim_add_cost_schedule': 'bim_costing',
    'bim_add_cost_item': 'bim_costing',
    'bim_assign_cost_to_element': 'bim_costing',
    'bim_calculate_costs': 'bim_costing',
    'bim_export_cost_schedule': 'bim_costing',

    # ── BIM: Schedule (4D) ────────────────────────────────────────────
    'bim_add_work_schedule': 'bim_scheduling',
    'bim_add_task': 'bim_scheduling',
    'bim_assign_task_to_element': 'bim_scheduling',
    'bim_add_task_sequence': 'bim_scheduling',
    'bim_calculate_schedule': 'bim_scheduling',
    'bim_get_schedule_info': 'bim_scheduling',

    # ── BIM: Clash Detection ──────────────────────────────────────────
    'bim_create_clash_set': 'bim_clash',
    'bim_run_clash_detection': 'bim_clash',
    'bim_get_clash_results': 'bim_clash',
    'bim_select_clashing_elements': 'bim_clash',

    # ── BIM: Drawing ──────────────────────────────────────────────────
    'bim_add_drawing': 'bim_drawings',
    'bim_add_sheet': 'bim_drawings',
    'bim_add_drawing_to_sheet': 'bim_drawings',
    'bim_add_annotation': 'bim_drawings',
    'bim_export_drawing': 'bim_drawings',

    # ── BIM: Systems (MEP) ────────────────────────────────────────────
    'bim_add_system': 'bim_systems',
    'bim_assign_to_system': 'bim_systems',
    'bim_connect_ports': 'bim_systems',
    'bim_list_systems': 'bim_systems',

    # ── BIM: BCF Collaboration ────────────────────────────────────────
    'bim_create_bcf_project': 'bim_bcf',
    'bim_add_bcf_topic': 'bim_bcf',
    'bim_add_bcf_viewpoint': 'bim_bcf',
    'bim_list_bcf_topics': 'bim_bcf',
    'bim_export_bcf': 'bim_bcf',

    # ── BIM: Structural ───────────────────────────────────────────────
    'bim_add_structural_model': 'bim_structural',
    'bim_add_structural_load': 'bim_structural',
    'bim_add_load_case': 'bim_structural',
    'bim_add_boundary_condition': 'bim_structural',

    # ── BIM: Validation ───────────────────────────────────────────────
    'bim_validate_ifc': 'bim_validation',
    'bim_run_ids_check': 'bim_validation',
    'bim_purge_unused': 'bim_validation',
}

# Every tag actually used above, so 'full' and a preset built from "all tags"
# never drift apart even if a new tag is added here without a tool using it
# yet.
_ALL_TAGS = set(TOOL_TAGS.values())

# qgis's own documented trap: an untagged tool, or a tag missing from every
# preset, is stranded the moment enable(only=True) applies — there is no way
# back to it short of restarting the server. ESCAPE must ride in every preset.
ESCAPE = {'escape'}

PRESETS = {
    'full': None,  # sentinel: everything
    # Everything except the Bonsai BIM surface — modeling, materials,
    # lighting/camera/render, animation, file I/O.
    'generic_blender': {'scene', 'objects', 'mesh', 'materials', 'lighting',
                        'camera', 'rendering', 'animation', 'collections',
                        'file_io', 'uv'} | ESCAPE,
    # IFC authoring: project/spatial/elements/materials/types/georeference,
    # plus properties and classification (every authored element needs both)
    # and enough generic surface (scene context, file I/O) to work the model.
    'bim_authoring': {'bim_authoring', 'bim_properties', 'bim_classification',
                      'scene', 'objects', 'file_io'} | ESCAPE,
    # 5D/4D: cost schedules and work schedules, plus bim_properties
    # (pset_filter queries are how cost/schedule items find their elements)
    # and enough context to report on what's loaded.
    'bim_costing': {'bim_costing', 'bim_scheduling', 'bim_properties',
                    'scene', 'file_io'} | ESCAPE,
    # Camera, lighting, render settings/execution, scene context, file I/O
    # for the rendered output.
    'rendering': {'rendering', 'lighting', 'camera', 'scene', 'file_io'} | ESCAPE,
    # Smallest useful surface: the escape hatches alone. search_tools and
    # run_tool reach everything else from here.
    'minimal': set(ESCAPE),
}


def preset_tags(preset):
    return PRESETS.get(preset)
