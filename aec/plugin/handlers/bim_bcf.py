"""
BIM BCF handlers — collaboration projects, issues/topics, viewpoints, export.
"""

import bpy


def register(server):
    """Register BIM BCF handlers."""
    s = server

    def bim_create_bcf_project(name: str, **_):
        try:
            bpy.ops.bim.new_bcf_project()
            bpy.context.scene.BCFProperties.name = name
            return {"name": name, "created": True}
        except Exception as e:
            return {"error": str(e), "note": "BCF requires Bonsai BCF module"}

    def bim_add_bcf_topic(title: str, description: str = None, type: str = "Issue",
                           priority: str = "Normal", assigned_to: str = None, **_):
        try:
            bpy.ops.bim.add_bcf_topic()
            props = bpy.context.scene.BCFProperties
            if hasattr(props, 'topic_title'):
                props.topic_title = title
            if description and hasattr(props, 'topic_description'):
                props.topic_description = description
            if hasattr(props, 'topic_type'):
                props.topic_type = type
            if hasattr(props, 'topic_priority'):
                props.topic_priority = priority
            if assigned_to and hasattr(props, 'topic_assigned_to'):
                props.topic_assigned_to = assigned_to
            return {"title": title, "type": type, "priority": priority}
        except Exception as e:
            return {"error": str(e), "title": title}

    def bim_add_bcf_viewpoint(topic_id: int = 0, **_):
        try:
            bpy.ops.bim.add_bcf_viewpoint()
            return {"viewpoint_added": True, "topic_id": topic_id}
        except Exception as e:
            return {"error": str(e)}

    def bim_list_bcf_topics(**_):
        try:
            bpy.ops.bim.load_bcf_topics()
            props = bpy.context.scene.BCFProperties
            topics = []
            if hasattr(props, 'topics'):
                for topic in props.topics:
                    topics.append({
                        "title": topic.title if hasattr(topic, 'title') else str(topic),
                    })
            return {"topics": topics, "count": len(topics)}
        except Exception as e:
            return {"topics": [], "error": str(e)}

    def bim_export_bcf(filepath: str, **_):
        try:
            bpy.ops.bim.save_bcf_project(filepath=filepath)
            return {"exported": filepath}
        except Exception as e:
            return {"error": str(e), "filepath": filepath}

    s._HANDLERS.update({
        "bim_create_bcf_project": bim_create_bcf_project,
        "bim_add_bcf_topic": bim_add_bcf_topic,
        "bim_add_bcf_viewpoint": bim_add_bcf_viewpoint,
        "bim_list_bcf_topics": bim_list_bcf_topics,
        "bim_export_bcf": bim_export_bcf,
    })
