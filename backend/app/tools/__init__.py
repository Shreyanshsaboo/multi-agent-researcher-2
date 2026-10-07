"""Tools the worker agents call. Each factory binds its tools to one task's ToolContext."""

from app.tools.articles import make_article_tools
from app.tools.base import Finding, SimulatedFault, SourceMeta, ToolContext
from app.tools.hackernews import make_hn_tools
from app.tools.web import make_web_tools

__all__ = [
    "Finding",
    "SimulatedFault",
    "SourceMeta",
    "ToolContext",
    "make_article_tools",
    "make_hn_tools",
    "make_web_tools",
]
