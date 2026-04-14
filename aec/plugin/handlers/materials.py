"""
Material handlers — create, assign, edit, list, remove, texture nodes, node materials.
"""

import bpy


def register(server):
    """Register material handlers."""
    s = server

    def create_material(name: str, color: list = None, metallic: float = None,
                        roughness: float = None, **_):
        mat = bpy.data.materials.new(name=name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            if color:
                c = list(color) + [1.0] if len(color) == 3 else list(color)
                bsdf.inputs["Base Color"].default_value = c
            if metallic is not None:
                bsdf.inputs["Metallic"].default_value = metallic
            if roughness is not None:
                bsdf.inputs["Roughness"].default_value = roughness
        return {"name": mat.name, "users": mat.users}

    def assign_material(object_name: str, material_name: str, slot_index: int = 0, **_):
        obj = s.get_object_or_raise(object_name)
        mat = s.get_material_or_raise(material_name)
        if slot_index < len(obj.material_slots):
            obj.material_slots[slot_index].material = mat
        else:
            obj.data.materials.append(mat)
        return {"object": object_name, "material": material_name}

    def edit_material(material_name: str, color: list = None, metallic: float = None,
                      roughness: float = None, emission_color: list = None,
                      emission_strength: float = None, alpha: float = None, **_):
        mat = s.get_material_or_raise(material_name)
        if not mat.use_nodes:
            mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if not bsdf:
            raise RuntimeError(f"Material '{material_name}' has no Principled BSDF node")
        if color:
            c = list(color) + [1.0] if len(color) == 3 else list(color)
            bsdf.inputs["Base Color"].default_value = c
        if metallic is not None:
            bsdf.inputs["Metallic"].default_value = metallic
        if roughness is not None:
            bsdf.inputs["Roughness"].default_value = roughness
        if emission_color:
            ec = list(emission_color) + [1.0] if len(emission_color) == 3 else list(emission_color)
            bsdf.inputs["Emission Color"].default_value = ec
        if emission_strength is not None:
            bsdf.inputs["Emission Strength"].default_value = emission_strength
        if alpha is not None:
            bsdf.inputs["Alpha"].default_value = alpha
            mat.blend_method = 'BLEND' if alpha < 1.0 else 'OPAQUE'
        return {"material": material_name, "updated": True}

    def list_materials(**_):
        mats = []
        for mat in bpy.data.materials:
            info = {"name": mat.name, "users": mat.users, "use_nodes": mat.use_nodes}
            if mat.use_nodes:
                bsdf = mat.node_tree.nodes.get("Principled BSDF")
                if bsdf:
                    info["base_color"] = list(bsdf.inputs["Base Color"].default_value)
                    info["metallic"] = bsdf.inputs["Metallic"].default_value
                    info["roughness"] = bsdf.inputs["Roughness"].default_value
            mats.append(info)
        return {"materials": mats, "count": len(mats)}

    def remove_material(material_name: str, **_):
        mat = s.get_material_or_raise(material_name)
        bpy.data.materials.remove(mat)
        return {"removed": material_name}

    def add_texture_node(material_name: str, texture_path: str,
                         node_type: str = "base_color", **_):
        mat = s.get_material_or_raise(material_name)
        if not mat.use_nodes:
            mat.use_nodes = True
        tree = mat.node_tree
        bsdf = tree.nodes.get("Principled BSDF")
        if not bsdf:
            raise RuntimeError(f"Material '{material_name}' has no Principled BSDF node")

        img_node = tree.nodes.new('ShaderNodeTexImage')
        img = bpy.data.images.load(texture_path)
        img_node.image = img

        _INPUT_MAP = {
            "base_color": "Base Color",
            "metallic": "Metallic",
            "roughness": "Roughness",
            "normal": "Normal",
            "emission": "Emission Color",
        }
        input_name = _INPUT_MAP.get(node_type.lower())
        if not input_name:
            raise RuntimeError(f"Unknown node_type: {node_type}. Use: {', '.join(_INPUT_MAP.keys())}")

        if node_type.lower() == "normal":
            # Insert normal map node
            normal_node = tree.nodes.new('ShaderNodeNormalMap')
            tree.links.new(img_node.outputs["Color"], normal_node.inputs["Color"])
            tree.links.new(normal_node.outputs["Normal"], bsdf.inputs["Normal"])
            img.colorspace_settings.name = 'Non-Color'
        else:
            tree.links.new(img_node.outputs["Color"], bsdf.inputs[input_name])
            if node_type.lower() in ("metallic", "roughness"):
                img.colorspace_settings.name = 'Non-Color'

        return {"material": material_name, "texture": texture_path, "connected_to": input_name}

    def create_node_material(material_name: str, node_setup: dict = None, **_):
        mat = bpy.data.materials.new(name=material_name)
        mat.use_nodes = True
        if not node_setup:
            return {"name": mat.name, "note": "Empty node material created with Principled BSDF"}
        # node_setup is a dict like {"base_color": [r,g,b], "metallic": 0.5, ...}
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            for key, val in node_setup.items():
                if key in bsdf.inputs:
                    if isinstance(val, list):
                        v = list(val) + [1.0] if len(val) == 3 else list(val)
                        bsdf.inputs[key].default_value = v
                    else:
                        bsdf.inputs[key].default_value = val
        return {"name": mat.name, "configured": list(node_setup.keys()) if node_setup else []}

    s._HANDLERS.update({
        "create_material": create_material,
        "assign_material": assign_material,
        "edit_material": edit_material,
        "list_materials": list_materials,
        "remove_material": remove_material,
        "add_texture_node": add_texture_node,
        "create_node_material": create_node_material,
    })
