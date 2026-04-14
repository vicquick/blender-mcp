"""
Code execution handler — execute arbitrary Python in Blender's context.
"""

import bpy
import sys
import io


def register(server):
    """Register code execution handler."""

    def execute_code(code: str, **_):
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        namespace = {
            "bpy": bpy,
            "__builtins__": __builtins__,
        }
        # Add optional imports if available
        try:
            import mathutils
            namespace["mathutils"] = mathutils
        except ImportError:
            pass
        try:
            import bmesh
            namespace["bmesh"] = bmesh
        except ImportError:
            pass
        try:
            import ifcopenshell
            namespace["ifcopenshell"] = ifcopenshell
        except ImportError:
            pass
        try:
            import bonsai.tool as tool
            namespace["tool"] = tool
        except ImportError:
            pass

        old_stdout = sys.stdout
        old_stderr = sys.stderr
        try:
            sys.stdout = stdout_capture
            sys.stderr = stderr_capture
            exec(code, namespace)
            return {
                "executed": True,
                "stdout": stdout_capture.getvalue(),
                "stderr": stderr_capture.getvalue(),
            }
        except Exception as e:
            import traceback
            return {
                "executed": False,
                "error": str(e),
                "traceback": traceback.format_exc(),
                "stdout": stdout_capture.getvalue(),
                "stderr": stderr_capture.getvalue(),
            }
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

    server._HANDLERS.update({
        "execute_code": execute_code,
    })
