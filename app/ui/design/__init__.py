"""Unified's design system: tokens, palettes, theme management, stylesheet.

Import order matters here only in one direction - `tokens` and `palette`
know nothing about Qt widgets or about each other's consumers, `theme`
composes them into the live application state, and `stylesheet` renders
that state into QSS. Nothing in this package imports from app.ui.*
widgets, which is what keeps the system a system rather than a second
place widgets live.
"""

from app.ui.design import palette, theme, tokens

__all__ = ["tokens", "palette", "theme"]
