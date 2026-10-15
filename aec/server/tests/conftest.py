import os
import sys

# Tests run from the repo but the server modules live flat in aec/server/ —
# add that directory to sys.path so `import blender_paths` etc. work without
# installing the package or copying files around.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
