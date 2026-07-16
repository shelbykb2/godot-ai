"""Unit tests for editor_screenshot disk save helpers."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest

from godot_ai.handlers import editor as editor_handlers


class _Session:
    def __init__(self, project_path: str) -> None:
        self.project_path = project_path


class _Runtime:
    def __init__(self, project_path: str, png_bytes: bytes) -> None:
        self._session = _Session(project_path)
        self._png = png_bytes
        self.commands: list[str] = []

    def get_active_session(self) -> _Session:
        return self._session

    async def send_command(
        self, command: str, params: dict[str, Any] | None = None, **_k: Any
    ) -> dict[str, Any]:
        self.commands.append(command)
        assert command == "take_screenshot"
        b64 = base64.b64encode(self._png).decode("ascii")
        return {
            "source": (params or {}).get("source", "viewport"),
            "width": 64,
            "height": 36,
            "original_width": 128,
            "original_height": 72,
            "format": "png",
            "image_base64": b64,
        }


# Minimal 1x1 PNG
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.mark.asyncio
async def test_auto_save_writes_under_docs_mcp_captures(tmp_path: Path) -> None:
    rt = _Runtime(str(tmp_path), _PNG)
    out = await editor_handlers.editor_screenshot(
        rt,  # type: ignore[arg-type]
        source="viewport",
        max_resolution=640,
        include_image=False,
        auto_save=True,
    )
    assert isinstance(out, dict)
    assert out.get("saved_path")
    path = Path(out["saved_path"])
    assert path.is_file()
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert "mcp_captures" in str(path)
    assert out.get("saved_path_res", "").startswith("res://docs/mcp_captures/")
    assert out.get("inline_included") is False


@pytest.mark.asyncio
async def test_large_include_image_skips_inline_when_over_cap(tmp_path: Path) -> None:
    rt = _Runtime(str(tmp_path), _PNG)
    out = await editor_handlers.editor_screenshot(
        rt,  # type: ignore[arg-type]
        source="game",
        max_resolution=800,
        include_image=True,
        auto_save=True,
        inline_max_resolution=400,
    )
    assert isinstance(out, dict)
    assert out.get("saved_path")
    assert out.get("inline_included") is False
    assert out.get("inline_skipped") is True


@pytest.mark.asyncio
async def test_explicit_save_path(tmp_path: Path) -> None:
    target = tmp_path / "custom" / "shot.png"
    rt = _Runtime(str(tmp_path), _PNG)
    out = await editor_handlers.editor_screenshot(
        rt,  # type: ignore[arg-type]
        source="viewport",
        include_image=False,
        auto_save=False,
        save_path=str(target),
    )
    assert isinstance(out, dict)
    assert Path(out["saved_path"]) == target.resolve()
    assert target.is_file()
