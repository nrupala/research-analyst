"""Report generation — templates, rendering, and visual intelligence.

Each module:
  - templates.py: 7-step report structures for all three report modes
  - renderer.py: Assembles analysis outputs into complete Markdown reports
  - visuals.py: Plotly codegen, Mermaid diagrams, ASCII charts, Markdown tables
"""
# Module: research_analyst/reports/__init__.py | Version: 0.1.0 | Updated: 2026-05-15

from .renderer import ReportRenderer
from .templates import get_template
from .visuals import VisualEngine

__all__ = ["ReportRenderer", "VisualEngine", "get_template"]
