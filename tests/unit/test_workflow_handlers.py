"""Unit tests for workflow helpers (no live Godot required)."""

from __future__ import annotations

from typing import Any

import pytest

from godot_ai.handlers import workflow as workflow_handlers
from godot_ai.server import create_server
from godot_ai.tools.domains import DOMAINS, EXCLUDABLE_DOMAINS


class _FakeRuntime:
    """Minimal runtime stub for pure guidance ops."""


@pytest.mark.asyncio
async def test_modeling_guidance_styles() -> None:
    rt = _FakeRuntime()
    for style in ("general_pbr", "low_poly", "stylized_ethereal"):
        out = await workflow_handlers.workflow_modeling_guidance(rt, style=style)  # type: ignore[arg-type]
        assert out["style"] == style
        assert "silhouette" in out
        assert "materials" in out
        assert out["checklist"]


@pytest.mark.asyncio
async def test_modeling_guidance_unknown_style_falls_back() -> None:
    out = await workflow_handlers.workflow_modeling_guidance(_FakeRuntime(), style="nope")  # type: ignore[arg-type]
    assert out["style"] == "general_pbr"


@pytest.mark.asyncio
async def test_install_hints_has_options() -> None:
    out = await workflow_handlers.workflow_install_hints(_FakeRuntime())  # type: ignore[arg-type]
    assert out["mcp_url"].startswith("http://127.0.0.1:8000")
    assert len(out["options"]) >= 2
    names = {o["name"] for o in out["options"]}
    assert "dock_configure" in names
    assert "manual_toml" in names
    assert "dev_checkout_junction" in names
    # Upstream-safe: no hard dependency on a personal fork URL in title
    assert "shelbykb2" not in out["title"].lower()


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
    out = await workflow_handlers.workflow_asset_pipeline(_FakeRuntime())  # type: ignore[arg-type]
    assert out["found"]["glb_count"] == 2
    assert out["found"]["terrain3d_hits"] == 1
    assert any("Terrain3D present" in r for r in out["recommendations"])
    assert len(calls) >= 4


@pytest.mark.asyncio
async def test_asset_pipeline_normalizes_path(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_search(*_a: Any, **kwargs: Any) -> dict:
        return {"files": []}

    monkeypatch.setattr("godot_ai.handlers.filesystem.filesystem_search", fake_search)
    out = await workflow_handlers.workflow_asset_pipeline(
        _FakeRuntime(),  # type: ignore[arg-type]
        path="assets/props",
    )
    assert out["root"] == "res://assets/props"


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
            "saved_path": "C:/tmp/shot.png",
            "byte_size": 12,
        }

    monkeypatch.setattr(
        "godot_ai.handlers.editor.editor_screenshot",
        fake_shot,
    )
    out = await workflow_handlers.workflow_screenshot_verify(
        _FakeRuntime(),  # type: ignore[arg-type]
        source="viewport",
        checklist=["Item A", "Item B"],
    )
    assert out["capture"]["width"] == 640
    assert out["saved_path"] == "C:/tmp/shot.png"
    assert "saved_path=" in out["agent_instructions"]
    assert len(out["checklist_results"]) == 2
    assert out["checklist_results"][0]["status"] == "pending_agent_review"


@pytest.mark.asyncio
async def test_screenshot_to_file(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_shot(*_a: Any, **kwargs: Any) -> dict:
        assert kwargs.get("include_image") is False
        assert kwargs.get("auto_save") is True
        return {
            "source": "game",
            "width": 800,
            "height": 450,
            "saved_path": "C:/proj/docs/mcp_captures/game.png",
            "saved_path_res": "res://docs/mcp_captures/game.png",
            "byte_size": 99,
        }

    monkeypatch.setattr("godot_ai.handlers.editor.editor_screenshot", fake_shot)
    out = await workflow_handlers.workflow_screenshot_to_file(
        _FakeRuntime(),  # type: ignore[arg-type]
        source="game",
    )
    assert out["ok"] is True
    assert out["saved_path"].endswith("game.png")


@pytest.mark.asyncio
async def test_visual_capture_set(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_state(_runtime: Any) -> dict:
        return {"is_playing": True, "helper_live": True, "game_status": {"helper_live": True}}

    async def fake_to_file(_runtime: Any, **kwargs: Any) -> dict:
        return {
            "ok": True,
            "saved_path": f"C:/shots/{kwargs.get('source', 'x')}.png",
            "source": kwargs.get("source"),
        }

    monkeypatch.setattr("godot_ai.handlers.editor.editor_state", fake_state)
    monkeypatch.setattr(
        "godot_ai.handlers.workflow.workflow_screenshot_to_file",
        fake_to_file,
    )
    out = await workflow_handlers.workflow_visual_capture_set(
        _FakeRuntime(),  # type: ignore[arg-type]
        shots=[{"source": "game", "label": "a"}, {"source": "viewport", "label": "b"}],
    )
    assert out["count"] == 2
    assert len(out["saved_paths"]) == 2


@pytest.mark.asyncio
async def test_screenshot_verify_content_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Block:
        def __init__(self, text: str) -> None:
            self.text = text

    async def fake_shot(*_a: Any, **_k: Any) -> list:
        return [_Block('{"width": 320, "height": 180}')]

    monkeypatch.setattr("godot_ai.handlers.editor.editor_screenshot", fake_shot)
    out = await workflow_handlers.workflow_screenshot_verify(_FakeRuntime())  # type: ignore[arg-type]
    assert out["capture"]["content_blocks"] is True
    assert out["capture"]["width"] == 320


@pytest.mark.asyncio
async def test_visual_qa_skips_game_when_not_live(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_state(_runtime: Any) -> dict:
        return {"is_playing": False, "helper_live": False, "game_status": {"helper_live": False}}

    monkeypatch.setattr("godot_ai.handlers.editor.editor_state", fake_state)

    out = await workflow_handlers.workflow_visual_qa(
        _FakeRuntime(),  # type: ignore[arg-type]
        sources=["game"],
        run_if_needed=False,
    )
    assert out["shots"][0]["skipped"] is True
    assert out["ran_project"] is False


@pytest.mark.asyncio
async def test_visual_qa_run_if_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    states = iter(
        [
            {"is_playing": False, "helper_live": False, "game_status": {"helper_live": False}},
            {"is_playing": True, "helper_live": True, "game_status": {"helper_live": True}},
            {"is_playing": True, "helper_live": True, "game_status": {"helper_live": True}},
        ]
    )
    ran: list[bool] = []

    async def fake_state(_runtime: Any) -> dict:
        return next(states)

    async def fake_run(_runtime: Any, **_k: Any) -> dict:
        ran.append(True)
        return {"ok": True}

    async def fake_shot(*_a: Any, **_k: Any) -> dict:
        return {"source": "viewport", "width": 64, "height": 36}

    monkeypatch.setattr("godot_ai.handlers.editor.editor_state", fake_state)
    monkeypatch.setattr("godot_ai.handlers.project.project_run", fake_run)
    monkeypatch.setattr("godot_ai.handlers.editor.editor_screenshot", fake_shot)
    monkeypatch.setattr("godot_ai.handlers.workflow.asyncio.sleep", _async_noop)

    out = await workflow_handlers.workflow_visual_qa(
        _FakeRuntime(),  # type: ignore[arg-type]
        sources=["viewport"],
        run_if_needed=True,
    )
    assert ran == [True]
    assert out["ran_project"] is True
    assert out["shots"][0]["skipped"] is False


async def _async_noop(_seconds: float) -> None:
    return None


def test_workflow_domain_registered_and_excludable() -> None:
    assert "workflow" in DOMAINS
    assert "workflow" in EXCLUDABLE_DOMAINS
    assert "grok" not in DOMAINS
    server = create_server()
    import asyncio

    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert "workflow_manage" in names
    assert "grok_manage" not in names

    server_ex = create_server(exclude_domains={"workflow"})
    tools_ex = asyncio.run(server_ex.list_tools())
    names_ex = {t.name for t in tools_ex}
    assert "workflow_manage" not in names_ex
