"""PDF export — one vector master, many cheap derivations.

See ``PDF-EXPORT.md`` for the strategy. The 1-up vector master is produced by
printing the reveal deck in headless Chromium (:mod:`lectern.pdf.master`); every
delivered layout (2-up, handouts with notes, N-up) is then *imposed* onto sheets
from that master with pypdf + a reportlab chrome overlay (:mod:`lectern.pdf.impose`),
and B&W / ink-saver are either a render-time token swap or a Ghostscript pass.

The heavy engines (Playwright/Chromium, pypdf, reportlab, Ghostscript) live behind
the ``lectern-slides[pdf]`` extra and are imported lazily, so importing
``lectern`` never requires them. :func:`lectern.pdf.pipeline.build_pdf` is the
entry point the reveal adapter calls for ``-f pdf``.
"""
