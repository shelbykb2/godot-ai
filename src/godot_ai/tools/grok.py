"""MCP tools for Grok Build workflow helpers (modeling, assets, visual QA)."""

from __future__ import annotations

from fastmcp import FastMCP

from godot_ai.handlers import grok as grok_handlers
from godot_ai.tools._meta_tool import register_manage_tool

_DESCRIPTION = """\
Grok Build workflow helpers for Godot: modeling guidance, asset pipeline
scans, screenshot verification, multi-shot visual QA, and fork install hints.

Ops:
  • modeling_guidance(style="general_pbr", topic="props")
        Structured 3D modeling guidance (silhouette, naming, materials,
        poly budget, export). Styles: general_pbr | low_poly | stylized_ethereal.
  • asset_pipeline(path="res://", limit=80)
        Scan the project for glTF/glb, Blender tooling paths, PBR maps,
        Terrain3D; return found/missing/recommendations.
  • screenshot_verify(source="viewport", max_resolution=800,
                      include_image=false, checklist=null, view_target="",
                      elevation=null, azimuth=null, fov=null)
        Capture a screenshot (metadata by default) plus a visual checklist
        for agent review. Prefer source=game when the project is playing.
  • visual_qa(sources=null, run_if_needed=false, max_resolution=640,
              include_image=false)
        Optional project_run, then multi-source screenshot_verify shots.
  • install_hints()
        How to override addons/godot_ai with a fork and wire Grok MCP.
"""


def register_grok_tools(mcp: FastMCP) -> None:
    register_manage_tool(
        mcp,
        tool_name="grok_manage",
        description=_DESCRIPTION,
        ops={
            "modeling_guidance": grok_handlers.grok_modeling_guidance,
            "asset_pipeline": grok_handlers.grok_asset_pipeline,
            "screenshot_verify": grok_handlers.grok_screenshot_verify,
            "visual_qa": grok_handlers.grok_visual_qa,
            "install_hints": grok_handlers.grok_install_hints,
        },
        read_resource_forms={
            # Workflow helpers — no godot:// resource counterparts.
            "modeling_guidance": None,
            "asset_pipeline": None,
            "screenshot_verify": None,
            "visual_qa": None,
            "install_hints": None,
        },
    )
