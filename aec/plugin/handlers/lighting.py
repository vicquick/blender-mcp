"""
Lighting handlers — create/edit lights, HDRI/world environment.
"""

import bpy


def register(server):
    """Register lighting handlers."""
    s = server

    def create_light(type: str = "POINT", name: str = None, location: list = None,
                     energy: float = 1000, color: list = None, **_):
        lt = type.upper()
        if lt not in ("POINT", "SUN", "SPOT", "AREA"):
            raise RuntimeError(f"Unknown light type: {type}. Use: POINT, SUN, SPOT, AREA")
        light_data = bpy.data.lights.new(name=name or f"{lt.title()}Light", type=lt)
        light_data.energy = energy
        if color:
            light_data.color = color[:3]
        obj = bpy.data.objects.new(light_data.name, light_data)
        bpy.context.collection.objects.link(obj)
        if location:
            obj.location = location
        return s.object_to_dict(obj)

    def edit_light(name: str, energy: float = None, color: list = None,
                   shadow: bool = None, size: float = None,
                   spot_size: float = None, spot_blend: float = None, **_):
        obj = s.get_object_or_raise(name)
        if obj.type != 'LIGHT':
            raise RuntimeError(f"Object '{name}' is not a light (type: {obj.type})")
        light = obj.data
        if energy is not None:
            light.energy = energy
        if color:
            light.color = color[:3]
        if shadow is not None:
            light.use_shadow = shadow
        if size is not None and hasattr(light, 'shadow_soft_size'):
            light.shadow_soft_size = size
        if spot_size is not None and light.type == 'SPOT':
            import math
            light.spot_size = math.radians(spot_size)
        if spot_blend is not None and light.type == 'SPOT':
            light.spot_blend = spot_blend
        return {"name": name, "type": light.type, "energy": light.energy}

    def set_world_hdri(filepath: str, strength: float = 1.0, rotation: float = 0.0, **_):
        world = bpy.context.scene.world
        if not world:
            world = bpy.data.worlds.new("World")
            bpy.context.scene.world = world
        world.use_nodes = True
        tree = world.node_tree
        tree.nodes.clear()

        # Create nodes
        bg = tree.nodes.new('ShaderNodeBackground')
        env = tree.nodes.new('ShaderNodeTexEnvironment')
        mapping = tree.nodes.new('ShaderNodeMapping')
        tex_coord = tree.nodes.new('ShaderNodeTexCoord')
        output = tree.nodes.new('ShaderNodeOutputWorld')

        # Load image
        img = bpy.data.images.load(filepath)
        env.image = img
        bg.inputs["Strength"].default_value = strength

        # Rotation
        import math
        mapping.inputs["Rotation"].default_value[2] = math.radians(rotation)

        # Link nodes
        tree.links.new(tex_coord.outputs["Generated"], mapping.inputs["Vector"])
        tree.links.new(mapping.outputs["Vector"], env.inputs["Vector"])
        tree.links.new(env.outputs["Color"], bg.inputs["Color"])
        tree.links.new(bg.outputs["Background"], output.inputs["Surface"])

        return {"hdri": filepath, "strength": strength, "rotation": rotation}

    def set_world_color(color: list = None, **_):
        world = bpy.context.scene.world
        if not world:
            world = bpy.data.worlds.new("World")
            bpy.context.scene.world = world
        world.use_nodes = True
        tree = world.node_tree
        tree.nodes.clear()

        bg = tree.nodes.new('ShaderNodeBackground')
        output = tree.nodes.new('ShaderNodeOutputWorld')
        if color:
            c = list(color[:3]) + [1.0] if len(color) == 3 else list(color)
            bg.inputs["Color"].default_value = c
        tree.links.new(bg.outputs["Background"], output.inputs["Surface"])
        return {"color": color}

    def list_lights(**_):
        lights = []
        for obj in bpy.data.objects:
            if obj.type == 'LIGHT':
                light = obj.data
                lights.append({
                    "name": obj.name,
                    "type": light.type,
                    "energy": light.energy,
                    "color": list(light.color),
                    "location": [round(v, 4) for v in obj.location],
                    "visible": obj.visible_get(),
                })
        return {"lights": lights, "count": len(lights)}

    s._HANDLERS.update({
        "create_light": create_light,
        "edit_light": edit_light,
        "set_world_hdri": set_world_hdri,
        "set_world_color": set_world_color,
        "list_lights": list_lights,
    })
