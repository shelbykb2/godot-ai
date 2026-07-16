"""MCP tools for agent workflow helpers (modeling, assets, visual QA)."""

from __future__ import annotations

from fastmcp import FastMCP

from godot_ai.handlers import workflow as workflow_handlers
from godot_ai.tools._meta_tool import register_manage_tool

_DESCRIPTION = """\
Agent workflow helpers for Godot: modeling guidance, asset pipeline scans,
screenshot verification (disk save — agent-safe), multi-shot visual QA, and
client install hints (including Grok Build MCP config).

Ops:
  • modeling_guidance(style="general_pbr", topic="props")
        Structured 3D modeling guidance (silhouette, naming, materials,
        poly budget, export). Styles: general_pbr | low_poly | stylized_ethereal.
  • asset_pipeline(path="res://", limit=80)
        Scan the project for glTF/glb, Blender tooling paths, PBR maps,
        Terrain3D; return found/missing/recommendations.
  • screenshot_to_file(source="game", max_resolution=800, save_path="")
        Capture PNG to disk only; returns saved_path for read_file.
        Preferred for Grok Build (avoids MCP image truncation).
  • screenshot_verify(source="viewport", max_resolution=800,
                      include_image=false, auto_save=true, checklist=null, …)
        Capture + checklist; auto_save writes saved_path for agent review.
  • visual_qa(sources=null, run_if_needed=false, max_resolution=640,
              include_image=false, auto_save=true)
        Optional project_run, then multi-source shots with saved_paths.
  • visual_capture_set(shots=null, max_resolution=720, run_if_needed=false)
        Batch labeled captures to disk; returns saved_paths list.
  • install_hints()
        How to wire Godot AI into Grok Build and related clients.
"""


def register_workflow_tools(mcp: FastMCP) -> None:
    register_manage_tool(
        mcp,
        tool_name="workflow_manage",
        description=_DESCRIPTION,
        ops={
            "modeling_guidance": workflow_handlers.workflow_modeling_guidance,
            "asset_pipeline": workflow_handlers.workflow_asset_pipeline,
            "screenshot_to_file": workflow_handlers.workflow_screenshot_to_file,
            "screenshot_verify": workflow_handlers.workflow_screenshot_verify,
            "visual_qa": workflow_handlers.workflow_visual_qa,
            "visual_capture_set": workflow_handlers.workflow_visual_capture_set,
            "install_hints": workflow_handlers.workflow_install_hints,
        },
        read_resource_forms={
            "modeling_guidance": None,
            "asset_pipeline": None,
            "screenshot_to_file": None,
            "screenshot_verify": None,
            "visual_qa": None,
            "visual_capture_set": None,
            "install_hints": None,
        },
    )
