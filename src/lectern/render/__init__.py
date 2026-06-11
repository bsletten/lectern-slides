"""Renderer adapters. Adapters are discovered through the registry in
``lectern.render.base`` — never hard-wired — so new frameworks slot in without
changes downstream.
"""

# Import adapters for their registration side effects.
from . import marp as _marp  # noqa: F401
from . import quarto as _quarto  # noqa: F401
from . import remark as _remark  # noqa: F401
from . import reveal as _reveal  # noqa: F401
from .base import (
    FORMATS,
    Caps,
    Renderer,
    RenderResult,
    get_renderer,
    register,
    renderers,
    renderers_supporting,
    supports_format,
)

__all__ = [
    "FORMATS",
    "Caps",
    "RenderResult",
    "Renderer",
    "get_renderer",
    "register",
    "renderers",
    "renderers_supporting",
    "supports_format",
]
