"""
Handler registration — imports all handler modules and registers them with the server.
"""

from . import (
    # Blender Core
    scene,
    objects,
    mesh,
    materials,
    lighting,
    camera,
    rendering,
    animation,
    collections,
    file_ops,
    code,
    uv,
    # BIM / Bonsai
    bim_project,
    bim_spatial,
    bim_elements,
    bim_properties,
    bim_materials,
    bim_types,
    bim_geometry,
    bim_classification,
    bim_cost,
    bim_schedule,
    bim_clash,
    bim_drawing,
    bim_systems,
    bim_georeference,
    bim_bcf,
    bim_structural,
    bim_validation,
)

_MODULES = [
    # Blender Core
    scene,
    objects,
    mesh,
    materials,
    lighting,
    camera,
    rendering,
    animation,
    collections,
    file_ops,
    code,
    uv,
    # BIM / Bonsai
    bim_project,
    bim_spatial,
    bim_elements,
    bim_properties,
    bim_materials,
    bim_types,
    bim_geometry,
    bim_classification,
    bim_cost,
    bim_schedule,
    bim_clash,
    bim_drawing,
    bim_systems,
    bim_georeference,
    bim_bcf,
    bim_structural,
    bim_validation,
]


def register_all_handlers(server):
    """Register all handler functions from every module onto the server."""
    for module in _MODULES:
        module.register(server)
