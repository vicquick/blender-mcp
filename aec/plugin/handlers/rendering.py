"""
Rendering handlers — engine, settings, render image/animation.
"""

import bpy


def register(server):
    """Register rendering handlers."""
    s = server

    def set_render_engine(engine: str = "CYCLES", **_):
        eng = engine.upper()
        engine_map = {
            "CYCLES": "CYCLES",
            "EEVEE": "BLENDER_EEVEE_NEXT",
            "EEVEE_NEXT": "BLENDER_EEVEE_NEXT",
            "WORKBENCH": "BLENDER_WORKBENCH",
        }
        if eng not in engine_map:
            raise RuntimeError(f"Unknown engine: {engine}. Use: {', '.join(engine_map.keys())}")
        bpy.context.scene.render.engine = engine_map[eng]
        return {"engine": bpy.context.scene.render.engine}

    def set_render_settings(resolution_x: int = None, resolution_y: int = None,
                            samples: int = None, film_transparent: bool = None,
                            use_denoising: bool = None, resolution_percentage: int = None,
                            output_format: str = None, **_):
        render = bpy.context.scene.render
        if resolution_x is not None:
            render.resolution_x = resolution_x
        if resolution_y is not None:
            render.resolution_y = resolution_y
        if resolution_percentage is not None:
            render.resolution_percentage = resolution_percentage
        if film_transparent is not None:
            render.film_transparent = film_transparent
        if output_format is not None:
            render.image_settings.file_format = output_format.upper()
        # Engine-specific settings
        scene = bpy.context.scene
        if samples is not None:
            if scene.render.engine == 'CYCLES':
                scene.cycles.samples = samples
            elif hasattr(scene, 'eevee'):
                scene.eevee.taa_render_samples = samples
        if use_denoising is not None and scene.render.engine == 'CYCLES':
            scene.cycles.use_denoising = use_denoising
        return {
            "resolution": [render.resolution_x, render.resolution_y],
            "resolution_percentage": render.resolution_percentage,
            "engine": render.engine,
        }

    def render_image(filepath: str, format: str = "PNG", **_):
        render = bpy.context.scene.render
        render.filepath = filepath
        render.image_settings.file_format = format.upper()
        bpy.ops.render.render(write_still=True)
        import os
        size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
        return {"filepath": filepath, "format": format, "file_size": size}

    def render_animation(output_dir: str, format: str = "PNG",
                         frame_start: int = None, frame_end: int = None, **_):
        scene = bpy.context.scene
        render = scene.render
        render.filepath = output_dir
        render.image_settings.file_format = format.upper()
        if frame_start is not None:
            scene.frame_start = frame_start
        if frame_end is not None:
            scene.frame_end = frame_end
        bpy.ops.render.render(animation=True)
        return {
            "output_dir": output_dir,
            "format": format,
            "frame_start": scene.frame_start,
            "frame_end": scene.frame_end,
        }

    def get_render_settings(**_):
        scene = bpy.context.scene
        render = scene.render
        result = {
            "engine": render.engine,
            "resolution_x": render.resolution_x,
            "resolution_y": render.resolution_y,
            "resolution_percentage": render.resolution_percentage,
            "film_transparent": render.film_transparent,
            "output_format": render.image_settings.file_format,
            "fps": render.fps,
            "frame_start": scene.frame_start,
            "frame_end": scene.frame_end,
        }
        if render.engine == 'CYCLES':
            result["samples"] = scene.cycles.samples
            result["use_denoising"] = scene.cycles.use_denoising
            result["device"] = scene.cycles.device
        return result

    s._HANDLERS.update({
        "set_render_engine": set_render_engine,
        "set_render_settings": set_render_settings,
        "render_image": render_image,
        "render_animation": render_animation,
        "get_render_settings": get_render_settings,
    })
