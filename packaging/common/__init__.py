"""Common packaging utilities and path resolution."""
from packaging.common.paths import JarvisPaths
from packaging.common.version import JARVIS_NAME, JARVIS_VERSION, get_build_metadata

__all__ = ["JarvisPaths", "JARVIS_NAME", "JARVIS_VERSION", "get_build_metadata"]
