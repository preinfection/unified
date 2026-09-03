"""Application stylesheet entry point.

The stylesheet itself lives in `app.ui.design.stylesheet`, rendered from
semantic tokens for whichever palette is active. This module exists so
callers keep a stable name to import, and so there is one obvious place
to look for "where does the app's QSS come from".
"""

from __future__ import annotations

from app.ui.design.stylesheet import build_variables, render
from app.ui.design.theme import theme_manager

__all__ = ["get_stylesheet", "build_variables", "render"]


def get_stylesheet(palette=None) -> str:
    """The full application stylesheet for `palette` (default: active).

    Built lazily rather than as a module constant: rendering it needs a
    live QApplication, because the combo-box chevron and checkbox tick are
    rasterized SVG assets written to disk at render time.
    """
    return render(palette or theme_manager.palette)
