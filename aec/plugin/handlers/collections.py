"""
Collection handlers — create, delete, move objects, visibility, list.
"""

import bpy


def register(server):
    """Register collection handlers."""
    s = server

    def create_collection(name: str, parent: str = None, **_):
        col = bpy.data.collections.new(name)
        if parent:
            parent_col = s.get_collection_or_raise(parent)
            parent_col.children.link(col)
        else:
            bpy.context.scene.collection.children.link(col)
        return {"name": col.name, "parent": parent}

    def delete_collection(name: str, **_):
        col = s.get_collection_or_raise(name)
        bpy.data.collections.remove(col)
        return {"deleted": name}

    def move_to_collection(object_names: list, collection_name: str, **_):
        col = s.get_collection_or_raise(collection_name)
        moved = []
        for name in object_names:
            obj = bpy.data.objects.get(name)
            if obj:
                # Remove from all current collections
                for old_col in list(obj.users_collection):
                    old_col.objects.unlink(obj)
                col.objects.link(obj)
                moved.append(name)
        return {"collection": collection_name, "moved": moved}

    def set_collection_visibility(name: str, visible: bool = True,
                                  viewport: bool = True, render: bool = True, **_):
        col = s.get_collection_or_raise(name)
        # Find the layer collection
        def find_layer_col(layer_col, target_name):
            if layer_col.collection.name == target_name:
                return layer_col
            for child in layer_col.children:
                result = find_layer_col(child, target_name)
                if result:
                    return result
            return None

        lc = find_layer_col(bpy.context.view_layer.layer_collection, name)
        if lc:
            lc.exclude = not visible
        col.hide_viewport = not viewport
        col.hide_render = not render
        return {"name": name, "visible": visible, "viewport": viewport, "render": render}

    def list_collections(**_):
        def collect_tree(col, depth=0):
            result = [{
                "name": col.name,
                "depth": depth,
                "object_count": len(col.objects),
                "children_count": len(col.children),
            }]
            for child in col.children:
                result.extend(collect_tree(child, depth + 1))
            return result

        tree = collect_tree(bpy.context.scene.collection)
        return {"collections": tree, "count": len(bpy.data.collections)}

    s._HANDLERS.update({
        "create_collection": create_collection,
        "delete_collection": delete_collection,
        "move_to_collection": move_to_collection,
        "set_collection_visibility": set_collection_visibility,
        "list_collections": list_collections,
    })
