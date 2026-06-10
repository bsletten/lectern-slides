"""Renderer adapters. Adapters are discovered through the registry in
``lectern.render.base`` — never hard-wired — so new frameworks slot in without
changes downstream.
"""

# Import adapters for their registration side effects.
from . import reveal as _reveal  # noqa: F401
from .base import Caps, Renderer, RenderResult, get_renderer, register, renderers

__all__ = [
    "Caps",
    "RenderResult",
    "Renderer",
    "get_renderer",
    "register",
    "renderers",
]
