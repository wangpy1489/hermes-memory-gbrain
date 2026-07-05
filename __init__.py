"""GBrain memory provider plugin entry point.

Hermes discovers this file at ~/.hermes/plugins/gbrain/__init__.py.
"""

import os
import sys

_plugin_dir = os.path.dirname(os.path.abspath(__file__))
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)

from hermes_memory_gbrain import GbrainMemoryProvider

__all__ = ["GbrainMemoryProvider"]
