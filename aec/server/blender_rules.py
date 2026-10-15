"""Field-tested rules for driving the live aec-web Blender through this
server. Same shape and purpose as qgis-mcp's qgis_rules.py: something that
crashed, hung, lost data or silently misbehaved in a real session, written
down so the next agent does not rediscover it the hard way.

Served as MCP resources (blender://rules/<slug>) and through the
search_rules tool. Keep them generic: this repository is public.

A rule has: slug, title, severity, keywords (extra search words) and text
(Markdown). Severity extends qgis's crash|hang|silent|api with two landmine
shapes that are the actual risk on THIS deployment: "destructive" (data is
gone, not just the call) and "resource" (the shared GPU/CPU box, not Blender
itself, is what suffers).
"""

RULES = [
    {
        "slug": "no-factory-startup",
        "title": "Never --factory-startup or read_factory_settings() in aec-web",
        "severity": "destructive",
        "keywords": "factory startup read_factory_settings bonsai wheels addon "
                     "preferences reset reinstall",
        "text": """\
aec-web's Blender has the Bonsai BIM extension installed from custom-built
wheels baked into the container image at build time, not through Blender's
extension marketplace. Starting Blender with `--factory-startup`, or calling
`bpy.ops.wm.read_factory_settings()` from `execute_code`, resets the user
preferences and add-on registration state that points at those wheels — which
deletes Bonsai's registered presence with no error message. Every `bim_*`
tool then fails (often with an unrelated-looking AttributeError) until the
container is rebuilt from the image.

Never pass `--factory-startup` when restarting the aec-web Blender process,
and never run `read_factory_settings` (or `wm.read_homefile` with
`load_ui=False` combined with factory flags) from `execute_code`. `new_file`
(plain `wm.read_homefile(use_empty=True)`) is safe — it resets the scene, not
the add-on registration.""",
    },
    {
        "slug": "ifc-save-without-copy",
        "title": "Never let bim_save_project overwrite a source IFC without a copy first",
        "severity": "destructive",
        "keywords": "bim_save_project overwrite ifc source backup copy filepath",
        "text": """\
`bim_save_project()` with no `filepath` writes back to the path the IFC was
loaded from (Bonsai's `tool.Ifc.get_path()`). Once that write lands, Blender's
undo stack does not cover it — undo reverts `bpy.data` in memory, never the
file already overwritten on disk. A save that drops psets, downgrades the
schema, or otherwise corrupts the model has no "undo the file" path; only a
copy made before the first save in the session does.

Before the first `bim_save_project` call against real project data, either
pass an explicit new `filepath` (never the source path) or make sure a
filesystem copy of the source IFC already exists outside the session.""",
    },
    {
        "slug": "cycles-render-serialize",
        "title": "Serialize heavy Cycles renders — one at a time, the GPU is shared with the LLM stack",
        "severity": "resource",
        "keywords": "render_image render_animation cycles gpu vram concurrent llm "
                     "qwen reranker embedding oom",
        "text": """\
GEX44 has one GPU (RTX 4000 SFF Ada, 20GB) shared between this Blender
container and the llama-swap LLM stack (`qwen3.6-27b` pinned ~17GB,
`bge-reranker-v2-m3`, the embedding model). A concurrent Cycles GPU render on
top of that has caused VRAM contention and OOM on this exact box before.

Run at most one heavy `render_image`/`render_animation` call at a time — do
not fire a second render while one is still in flight (nothing below wave 3's
background-jobs work enforces a queue or semaphore here). Prefer `WORKBENCH`
or CPU-only Cycles for anything that is not the final output, and check
`get_render_settings` for the configured engine and sample count before a
render that might be larger than intended.""",
    },
    {
        "slug": "execute-code-hazards",
        "title": "execute_code traps: sys.executable, threads, and bpy's single-thread rule",
        "severity": "crash",
        "keywords": "execute_code sys.executable subprocess pip thread bpy main "
                     "thread not thread safe",
        "text": """\
- `subprocess.run([sys.executable, ...])` inside `execute_code` does not run
  a bare Python interpreter — inside Blender, `sys.executable` IS the Blender
  binary, so this relaunches Blender with whatever arguments you gave it
  (the same class of trap qgis-mcp documents for `pip` inside QGIS). Install
  packages from outside Blender, never from `execute_code`.
- Most of the `bpy` API is not thread-safe. Spawning a background
  `threading.Thread` from `execute_code` that touches `bpy.data` or `bpy.ops`
  concurrently with the Blender main thread (which this server's own next
  tool call will also use) risks silent data corruption, not a clean
  exception. Do heavy work synchronously, in the main thread, one call at a
  time.
- Batch related `execute_code` changes into one call where practical — each
  call is a full round trip through the socket, and a half-applied script
  (crashed partway through a multi-step edit) can leave the scene in a state
  no single tool call cleans up.""",
    },
    {
        "slug": "apply-and-boolean-consume-their-target",
        "title": "apply_modifier and boolean_operation permanently consume their input",
        "severity": "destructive",
        "keywords": "apply_modifier boolean_operation irreversible collapse target_name duplicate",
        "text": """\
`apply_modifier` bakes the modifier into the mesh's base data — after it
runs, the modifier is gone and the pre-apply shape is recoverable only from
the in-session undo stack, not after a reload. `boolean_operation`'s
`target_name` object is consumed into the result in the same way; running the
same boolean again with the same names either errors (object already gone)
or silently operates on the wrong geometry.

Before either call on a mesh you may need in its pre-modifier/pre-boolean
state later, `duplicate_object` it first and keep the duplicate hidden/unused
as a reference, rather than relying on undo surviving the rest of the
session.""",
    },
    {
        "slug": "new-file-open-file-no-confirm",
        "title": "new_file and open_file discard unsaved work with no confirmation",
        "severity": "destructive",
        "keywords": "new_file open_file unsaved discard confirm save_file scene replace",
        "text": """\
Unlike a GUI "unsaved changes" dialog, `new_file()` (`wm.read_homefile`) and
`open_file()` (`wm.open_mainfile`) replace the entire scene immediately —
there is no prompt, and the socket protocol has no way to ask one. Anything
not already saved via `save_file`/`bim_save_project` is gone the moment
either call returns.

Before calling either on a session that might hold unsaved work, call
`get_scene_info` to see what is currently loaded, and `save_file`/
`bim_save_project` first if it looks like it matters.""",
    },
]


def by_slug(slug):
    for r in RULES:
        if r["slug"] == slug:
            return r
    return None
