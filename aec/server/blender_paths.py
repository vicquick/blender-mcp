"""Server-side path jail for every blender-mcp tool that takes a filesystem
path (screenshot, texture/HDRI, render output, save/open/export/import,
every bim_*(filepath=...)).

Pure string math on posixpath, deliberately NOT os.path.realpath or
os.path.exists: the paths a tool call carries are resolved and opened inside
the aec-web container by the Blender addon, not by this server's own
container — checking them against THIS filesystem would answer the wrong
question (and silently pass through on a jail server that happens to have no
file at that path at all).

BLENDER_ALLOWED_ROOTS (colon-separated, env) sets the allowed roots. Default
is derived from what aec-web's handlers actually use today: `/tmp` (the
`get_viewport_screenshot` default filepath) and `/root` (where the container
runs as root and its own demo/working data already lives — `demo-ifc/`,
`demo-fach/`, `workspace/`, confirmed by inspecting the running container,
not guessed).

Known limitation, not silently assumed away: a symlink inside `/root` or
`/tmp` that points outside the allowed roots would still normalise to an
in-jail path here, because this jail has no filesystem to stat — only
aec-web does. Closing that is an addon-side concern (resolve and check
symlinks where the path is actually opened), out of scope for this
server-side string check.
"""

import os
import posixpath

DEFAULT_ROOTS = "/root:/tmp"


class PathJailError(ValueError):
    """A tool's filepath/output_dir argument failed the jail check."""


def allowed_roots():
    raw = os.environ.get("BLENDER_ALLOWED_ROOTS", DEFAULT_ROOTS)
    # normpath on each root too: a root configured with a trailing slash or
    # a redundant "/root/." must not accidentally widen or narrow the match
    # below (which compares against the normalised root exactly).
    return [posixpath.normpath(r) for r in raw.split(":") if r]


def jail_path(path, param_name="filepath"):
    """Normalise and validate one path argument.

    Returns the normalised path on success. Raises PathJailError (a
    ValueError subclass) with a message naming the parameter, the path and
    the allowed roots on any violation:
      - not a string, or empty
      - not absolute (relative is ambiguous: relative to Blender's cwd
        inside aec-web, not to anything this server knows)
      - normalises (after collapsing any ".."/"." segments) to a path that
        does not fall under one of the allowed roots

    Checking the NORMALISED path against the roots, rather than a string
    prefix on the original, is load-bearing: "/root/../etc/passwd" contains
    the substring "/root" but normalises to "/etc/passwd", outside every
    default root. A prefix check on the raw string would have let it through.
    """
    if not isinstance(path, str) or not path:
        raise PathJailError(f"{param_name} must be a non-empty string")
    if not posixpath.isabs(path):
        raise PathJailError(
            f"{param_name}={path!r} must be an absolute path inside the "
            "Blender container (aec-web) — a relative path is ambiguous, "
            "there is no single cwd to resolve it against from here"
        )
    normalised = posixpath.normpath(path)
    for root in allowed_roots():
        if normalised == root or normalised.startswith(root + "/"):
            return normalised
    raise PathJailError(
        f"{param_name}={path!r} normalises to {normalised!r}, which is "
        f"outside the allowed roots ({':'.join(allowed_roots())}); set "
        "BLENDER_ALLOWED_ROOTS to widen this if the path is legitimate"
    )


def jail_or_error(path, param_name="filepath"):
    """Tool-call-site convenience: returns (normalised_path, None) on success
    or (None, json_error_string) on failure, so a tool body can do

        filepath, err = jail_or_error(filepath)
        if err:
            return err

    without importing json or PathJailError itself. Matches the error shape
    (`{"error": ...}`) every other validation failure in this server already
    returns, so a client sees one consistent error contract regardless of
    which check rejected its call.
    """
    import json
    try:
        return jail_path(path, param_name), None
    except PathJailError as e:
        return None, json.dumps({"error": str(e)})
