"""Lectern — assemble Markdown slide sources into a deck and render it.

This package is the Markdown production front-end to a larger resource-oriented
slide system. The ``Source`` seam (``lectern.source``) is kept clean so a future
CMS/graph backend can replace the filesystem source without touching the
preprocess, render, or serve layers.
"""

__version__ = "0.1.0"
