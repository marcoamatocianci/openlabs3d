"""Parametric laboratory rack engine. See docs/features/PARAMETRIC_RACK_CONFIGURATOR.md.

Web process: schema, profiles, layout, structure, labels, planner, estimate (pure Python, numpy, shapely, Pillow).
Worker only: geometry (CadQuery) and build. The web process never imports CadQuery.
"""
