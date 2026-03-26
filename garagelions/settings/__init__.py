from .base import *

# Try to load local settings first
try:
    from .local import *
    print("Loaded local settings.")
except ImportError:
    from .production import *
    print("Loaded production settings.")