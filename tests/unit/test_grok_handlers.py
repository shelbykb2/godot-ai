"""Unit tests for Grok workflow handlers (no live Godot required)."""

from __future__ import annotations

from typing import Any

import pytest

from godot_ai.handlers import grok as grok_handlers
from godot_ai.server import create_server
from godot_ai.tools.domains import DOMAINS, EXCLUDABLE_DOMAINS


class _FakeRuntime:
    """Minimal runtime stub for pure guidance ops."""


@pytest.mark.asyncio
async def test_modeling_guidance_styles() -> None:
    rt = _FakeRuntime()
    for style in ("general_pbr", "low_poly", "stylized_ethereal"):
        out = await grok_handlers.grok_modeling_guidance(rt, style=style)  # type: ignore[arg-type]
        assert out["style"] == style
        assert "silhouette" in out
        assert "materials" in out
        assert out["checklist"]


@pytest.mark.asyncio
async def test_modeling_guidance_unknown_style_falls_back() -> None:
    out = await grok_handlers.grok_modeling_guidance(_FakeRuntime(), style="nope")  # type: ignore[arg-type]
    assert out["style"] == "general_pbr"


@pytest.mark.asyncio
async def test_install_hints_has_options() -> None:
    out = await grok_handlers.grok_install_hints(_FakeRuntime())  # type: ignore[arg-type]
    assert out["mcp_url"].startswith("http://127.0.0.1:8000")
    assert len(out["options"]) >= 2
    names = {o["name"] for o in out["options"]}
    assert "physical_copy" in names
    assert "directory_junction_dev" in names


@pytest.mark.asyncio
async def test_asset_pipeline_aggregates_searches(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_search(
        runtime: Any,
        name: str = "",
        type: str = "",
        path: str = "",
        offset: int = 0,
        limit: int = 100,
    ) -> dict:
        calls.append({"name": name, "path": path, "limit": limit})
        if name == ".glb":
            return {"files": ["res://assets/a.glb", "res://assets/b.glb"]}
        if name == "terrain_3d":
            return {"files": ["res://addons/terrain_3d/plugin.cfg"]}
        return {"files": []}

    monkeypatch.setattr(
        "godot_ai.handlers.filesystem.filesystem_search",
        fake_search,
    )
    out = await grok_handlers.grok_asset_pipeline(_FakeRuntime())  # type: ignore[arg-type]
    assert out["found"]["glb_count"] == 2
    assert out["found"]["terrain3d_hits"] == 1
    assert any("Terrain3D present" in r for r in out["recommendations"])
    assert len(calls) >= 4


@pytest.mark.asyncio
async def test_screenshot_verify_checklist(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_shot(*_a: Any, **_k: Any) -> dict:
        return {
            "source": "viewport",
            "width": 640,
            "height": 360,
            "original_width": 1280,
            "original_height": 720,
            "format": "png",
        }

    monkeypatch.setattr(
        "godot_ai.handlers.editor.editor_screenshot",
        fake_shot,
    )
    out = await grok_handlers.grok_screenshot_verify(
        _FakeRuntime(),  # type: ignore[arg-type]
        source="viewport",
        checklist=["Item A", "Item B"],
    )
    assert out["capture"]["width"] == 640
    assert len(out["checklist_results"]) == 2
    assert out["checklist_results"][0]["status"] == "pending_agent_review"


@pytest.mark.asyncio
async def test_visual_qa_skips_game_when_not_live(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_state(_runtime: Any) -> dict:
        return {"is_playing": False, "helper_live": False, "game_status": {"helper_live": False}}

    monkeypatch.setattr("godot_ai.handlers.editor.editor_state", fake_state)

    out = await grok_handlers.grok_visual_qa(
        _FakeRuntime(),  # type: ignore[arg-type]
        sources=["game"],
        run_if_needed=False,
    )
    assert out["shots"][0]["skipped"] is True
    assert out["ran_project"] is False


def test_grok_domain_registered_and_excludable() -> None:
    assert "grok" in DOMAINS
    assert "grok" in EXCLUDABLE_DOMAINS
    server = create_server()
    import asyncio

    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert "grok_manage" in names

    server_ex = create_server(exclude_domains={"grok"})
    tools_ex = asyncio.run(server_ex.list_tools())
    names_ex = {t.name for t in tools_ex}
    assert "grok_manage" not in names_ex
