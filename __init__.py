"""GBrain memory provider plugin entry point.

This file lives at ~/.hermes/plugins/gbrain/__init__.py so Hermes can
discover the provider. It re-exports GbrainMemoryProvider from the
hermes_memory_gbrain package.
"""

import os
import sys

# Ensure the plugin directory is on sys.path so that
# `from hermes_memory_gbrain import ...` resolves correctly
# when loaded by Hermes' plugin discovery.
_plugin_dir = os.path.dirname(os.path.abspath(__file__))
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)

from hermes_memory_gbrain import GbrainMemoryProvider

__all__ = ["GbrainMemoryProvider"]
