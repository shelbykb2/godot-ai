"""Shared handlers for editor tools and resources."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastmcp.tools.base import Image as McpImage
from mcp.types import TextContent

from godot_ai import runtime_info
from godot_ai.godot_client.client import GodotCommandError
from godot_ai.godot_client.session_diagnostics import (
    NO_ACTIVE_SESSION_MESSAGE,
    no_active_session_data,
)
from godot_ai.handlers._readiness import require_writable_async, sync_readiness_from_snapshot
from godot_ai.protocol.errors import ErrorCode
from godot_ai.runtime.direct import DirectRuntime
from godot_ai.tools._pagination import paginate

logger = logging.getLogger(__name__)

SCREENSHOT_TIMEOUT_SEC = 15.0
GAME_SCREENSHOT_TIMEOUT_SEC = 35.0
## Default max longest-edge for MCP ImageContent (avoids Grok/agent payload truncation).
DEFAULT_INLINE_MAX_RESOLUTION = 400
## Fork default: always write PNG to disk so agents can read_file without base64.
DEFAULT_AUTO_SAVE = True

## Brief delay between handing the structured pre-flight ack back to
## FastMCP and firing `reload_plugin` over the WebSocket on the
## plugin-managed path. Gives the HTTP/SSE response a chance to flush
## before the plugin tears down our own process. Tests override this
## to 0 so they don't wait. See `editor_reload_plugin` below.
PLUGIN_MANAGED_RELOAD_DELAY_SEC = 0.5

## Strong references to in-flight `_dispatch_reload_async` tasks. The
## event loop only holds weak references to tasks created via
## `create_task`, so without this set a GC cycle landing during the
## post-ack delay could collect the task and silently skip the WS
## reload command — leaving the caller with a "reload_initiated" ack
## but no actual reload. A done-callback removes the task on exit.
_pending_reload_tasks: set[asyncio.Task] = set()


async def editor_state(runtime: DirectRuntime) -> dict:
    """Read live editor state and self-heal the session readiness cache.

    The plugin emits ``readiness_changed`` events when ``_check_state_changes``
    notices a transition, but ``_process`` is paused around save/play frames
    (see ``McpConnection.pause_processing``), so the event can lag actual state
    by one or more ticks. During that window the server's ``session.readiness``
    cache stays at the previous value and a write call gated by
    ``require_writable`` is rejected even though the editor is already
    writeable. Issue #262 reproduced exactly that with an ``editor_state ->
    scene_save`` sequence: editor_state returned ``is_playing: false`` while
    the cache still said ``playing``, blocking the save.

    The plugin's ``get_editor_state`` reads ``EditorInterface.is_playing_scene``
    and ``McpConnection.get_readiness`` directly, so its ``readiness`` field is
    authoritative. Copy it onto the session so a subsequent ``require_writable``
    can't disagree with the value the agent just observed.
    """
    result = await runtime.send_command("get_editor_state")
    sync_readiness_from_snapshot(runtime, result.get("readiness"))
    return result


async def editor_selection_get(runtime: DirectRuntime) -> dict:
    return await runtime.send_command("get_selection")


def _project_root_from_runtime(runtime: DirectRuntime) -> Path | None:
    try:
        session = runtime.get_active_session()
    except Exception:  # noqa: BLE001
        session = None
    if session is None or not getattr(session, "project_path", None):
        return None
    path = Path(session.project_path)
    return path if path.is_dir() else path.parent if path.exists() else None


def _resolve_save_path(
    runtime: DirectRuntime,
    save_path: str,
    source: str,
    *,
    label: str = "",
) -> tuple[Path | None, str | None, str | None]:
    """Return (absolute_path, res_path_or_none, error_or_none)."""
    root = _project_root_from_runtime(runtime)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    safe_src = re.sub(r"[^a-z0-9_]+", "_", (source or "shot").lower()).strip("_") or "shot"
    safe_label = re.sub(r"[^a-z0-9_]+", "_", (label or "").lower()).strip("_")
    default_name = f"{safe_src}_{safe_label + '_' if safe_label else ''}{stamp}.png"

    if not save_path:
        if root is None:
            # Fall back to temp under cwd
            out = Path.cwd() / "mcp_captures" / default_name
            return out, None, None
        out = root / "docs" / "mcp_captures" / default_name
        res = f"res://docs/mcp_captures/{default_name}"
        return out, res, None

    raw = save_path.strip()
    if raw.startswith("res://"):
        if root is None:
            return None, None, "Cannot resolve res:// path: no active project_path on session"
        rel = raw[len("res://") :].lstrip("/\\")
        out = (root / rel).resolve()
        try:
            out.relative_to(root.resolve())
        except ValueError:
            return None, None, "save_path escapes project root"
        return out, raw if raw.endswith(".png") else raw + ("" if raw.endswith(".png") else ""), None

    out = Path(raw).expanduser()
    if not out.is_absolute():
        if root is not None:
            out = (root / out).resolve()
        else:
            out = out.resolve()
    else:
        out = out.resolve()
    if root is not None:
        try:
            out.relative_to(root.resolve())
        except ValueError:
            # Allow absolute paths outside project only if explicitly absolute user path
            # still ok for agent temp dirs
            pass
    res: str | None = None
    if root is not None:
        try:
            rel = out.relative_to(root.resolve())
            res = "res://" + str(rel).replace("\\", "/")
        except ValueError:
            res = None
    return out, res, None


def _write_png(path: Path, image_bytes: bytes) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(image_bytes)
    return {
        "saved_path": str(path),
        "byte_size": len(image_bytes),
    }


async def editor_screenshot(
    runtime: DirectRuntime,
    source: str = "viewport",
    max_resolution: int = 640,
    include_image: bool = True,
    view_target: str = "",
    coverage: bool = False,
    elevation: float | None = None,
    azimuth: float | None = None,
    fov: float | None = None,
    save_path: str = "",
    auto_save: bool = DEFAULT_AUTO_SAVE,
    inline_max_resolution: int = DEFAULT_INLINE_MAX_RESOLUTION,
) -> dict | list:
    """Capture screenshot; optionally save PNG to disk (agent-safe, no truncation).

    When ``auto_save`` is true (fork default) or ``save_path`` is set, writes a
    full-quality PNG and returns ``saved_path`` in metadata so agents can
    ``read_file`` the image. MCP ImageContent is only attached when
    ``include_image`` is true *and* resolution is within ``inline_max_resolution``
    (or a smaller inline recapture is performed).
    """
    capture_res = max_resolution if max_resolution > 0 else 0
    params: dict = {"source": source}
    if capture_res > 0:
        params["max_resolution"] = capture_res
    if view_target:
        params["view_target"] = view_target
    if coverage:
        params["coverage"] = True
    if elevation is not None:
        params["elevation"] = elevation
    if azimuth is not None:
        params["azimuth"] = azimuth
    if fov is not None:
        params["fov"] = fov

    timeout = GAME_SCREENSHOT_TIMEOUT_SEC if source == "game" else SCREENSHOT_TIMEOUT_SEC
    result = await runtime.send_command(
        "take_screenshot",
        params,
        timeout=timeout,
    )

    should_save = bool(save_path.strip()) or auto_save

    # --- Coverage response: multiple images ---
    if result.get("coverage") and "images" in result:
        images_meta = []
        saved_paths: list[str] = []
        for i, img in enumerate(result["images"]):
            meta_entry = {
                "label": img["label"],
                "elevation": img["elevation"],
                "azimuth": img["azimuth"],
                "fov": img["fov"],
                "width": img["width"],
                "height": img["height"],
            }
            if img.get("ortho"):
                meta_entry["ortho"] = True
            if should_save:
                image_bytes = base64.b64decode(img.get("image_base64", ""))
                path, res_p, err = _resolve_save_path(
                    runtime,
                    save_path if i == 0 and save_path.strip() else "",
                    source,
                    label=str(img.get("label", i)),
                )
                if err:
                    meta_entry["save_error"] = err
                elif path is not None:
                    written = _write_png(path, image_bytes)
                    meta_entry.update(written)
                    if res_p:
                        meta_entry["saved_path_res"] = res_p if res_p.endswith(".png") else res_p
                    saved_paths.append(written["saved_path"])
            images_meta.append(meta_entry)
        metadata: dict[str, Any] = {
            "source": result["source"],
            "view_target": view_target,
            "coverage": True,
            "image_count": len(result["images"]),
            "images": images_meta,
            "saved_paths": saved_paths,
            "agent_hint": (
                "Use read_file on saved_path entries for full-quality visual review "
                "(avoids MCP image truncation)."
            ),
        }
        if saved_paths:
            metadata["saved_path"] = saved_paths[0]
        if "view_target_count" in result:
            metadata["view_target_count"] = result["view_target_count"]
        if "view_target_not_found" in result:
            metadata["view_target_not_found"] = result["view_target_not_found"]
        for aabb_key in ("aabb_center", "aabb_size", "aabb_longest_ground_axis"):
            if aabb_key in result:
                metadata[aabb_key] = result[aabb_key]

        attach_inline = include_image and (
            capture_res <= 0 or capture_res <= inline_max_resolution
        )
        metadata["inline_included"] = attach_inline
        if not attach_inline:
            return metadata

        blocks: list = [TextContent(type="text", text=json.dumps(metadata))]
        for img in result["images"]:
            image_bytes = base64.b64decode(img.get("image_base64", ""))
            blocks.append(McpImage(data=image_bytes, format=img.get("format", "png")))
        return blocks

    # --- Single-image response ---
    metadata = {
        "source": result["source"],
        "width": result["width"],
        "height": result["height"],
        "original_width": result["original_width"],
        "original_height": result["original_height"],
        "format": result["format"],
    }
    if view_target:
        metadata["view_target"] = view_target
        if "view_target_count" in result:
            metadata["view_target_count"] = result["view_target_count"]
        if "view_target_not_found" in result:
            metadata["view_target_not_found"] = result["view_target_not_found"]
    for key in (
        "elevation",
        "azimuth",
        "fov",
        "aabb_center",
        "aabb_size",
        "aabb_longest_ground_axis",
        "camera_path",
    ):
        if key in result:
            metadata[key] = result[key]

    image_b64 = result.get("image_base64", "")
    image_bytes = base64.b64decode(image_b64) if image_b64 else b""
    fmt = result.get("format", "png")

    if should_save and image_bytes:
        path, res_p, err = _resolve_save_path(runtime, save_path, source)
        if err:
            metadata["save_error"] = err
        elif path is not None:
            written = _write_png(path, image_bytes)
            metadata.update(written)
            root = _project_root_from_runtime(runtime)
            if root is not None:
                try:
                    metadata["saved_path_res"] = "res://" + str(
                        path.relative_to(root.resolve())
                    ).replace("\\", "/")
                except ValueError:
                    if res_p:
                        metadata["saved_path_res"] = res_p
            elif res_p:
                metadata["saved_path_res"] = res_p
            metadata["agent_hint"] = (
                "Use read_file on saved_path for full-quality visual review "
                "(avoids MCP image truncation)."
            )

    attach_inline = include_image and image_bytes and (
        capture_res <= 0 or capture_res <= inline_max_resolution
    )
    # If user asked for a large include_image, save is enough; skip huge inline
    if include_image and not attach_inline and capture_res > inline_max_resolution:
        metadata["inline_skipped"] = True
        metadata["inline_skip_reason"] = (
            f"max_resolution {capture_res} > inline_max_resolution "
            f"{inline_max_resolution}; use saved_path + read_file"
        )
    metadata["inline_included"] = bool(attach_inline)

    if not attach_inline:
        return metadata

    return [
        TextContent(type="text", text=json.dumps(metadata)),
        McpImage(data=image_bytes, format=fmt),
    ]


async def performance_monitors_get(
    runtime: DirectRuntime, monitors: list[str] | None = None
) -> dict:
    params: dict = {}
    if monitors:
        params["monitors"] = monitors
    return await runtime.send_command("get_performance_monitors", params)


async def logs_clear(runtime: DirectRuntime, clear_debugger_errors: bool = False) -> dict:
    params: dict = {}
    if clear_debugger_errors:
        params["clear_debugger_errors"] = True
    return await runtime.send_command("clear_logs", params)


_VALID_LOG_SOURCES = ("plugin", "game", "editor", "all")


async def logs_read(
    runtime: DirectRuntime,
    count: int = 50,
    offset: int = 0,
    source: str = "plugin",
    since_run_id: str = "",
    since_cursor: int | None = None,
    include_details: bool = False,
) -> dict:
    if source not in _VALID_LOG_SOURCES:
        raise ValueError(f"Invalid source '{source}' — use 'plugin', 'game', 'editor', or 'all'")

    if source == "plugin":
        ## Backward-compatible shape: callers asking for the default
        ## source still receive the historical {lines: [str], ...}
        ## payload, so existing dashboards and tests don't break.
        result = await runtime.send_command("get_logs", {"count": 500, "source": "plugin"})
        ## The plugin response can be either the legacy `{lines: [str]}`
        ## (older plugin versions) or the new structured shape
        ## `{lines: [{source, level, text}], ...}`. Normalize to legacy
        ## strings here so the public Python API doesn't shift under
        ## existing callers.
        raw_lines = result.get("lines", [])
        flat: list[str] = []
        for entry in raw_lines:
            if isinstance(entry, dict):
                flat.append(str(entry.get("text", "")))
            else:
                flat.append(str(entry))
        response = paginate(flat, offset, count, key="lines")
        _forward_error_watermark_stamp(result, response)
        return response

    ## game / editor / all: ask the plugin to apply offset+count itself so the
    ## ring buffer's run_id, dropped_count, and is_running stay
    ## authoritative on the editor side.
    params = {"count": count, "offset": offset, "source": source}
    if source == "game" and since_run_id:
        ## The plugin resolves since_run_id against its retained ring
        ## (get_run_page), returning the prior run's lines with
        ## stale_run_id=true when the id is no longer current.
        params["since_run_id"] = since_run_id
    if source == "editor" and since_cursor is not None:
        params["since_cursor"] = since_cursor
    if include_details:
        params["include_details"] = True
    result = await runtime.send_command(
        "get_logs",
        params,
    )
    run_id = result.get("run_id", "")
    if since_run_id and run_id and run_id != since_run_id:
        ## The plugin echoes the requested run id back as `run_id` when it
        ## honors since_run_id, so a mismatch means an older plugin ignored
        ## the param and served the current run. Return the empty stale
        ## shape rather than mislabeling current-run lines as the old run.
        stale = {
            "source": source,
            "lines": [],
            "total_count": 0,
            "returned_count": 0,
            "offset": 0,
            "limit": count,
            "has_more": False,
            "run_id": run_id,
            "is_running": result.get("is_running", False),
            "dropped_count": result.get("dropped_count", 0),
            "stale_run_id": True,
        }
        if "current_run_id" in result:
            stale["current_run_id"] = result["current_run_id"]
        _forward_error_watermark_stamp(result, stale)
        return stale
    lines = result.get("lines", [])
    total = int(result.get("total_count", len(lines)))
    response = {
        "source": source,
        "lines": lines,
        "total_count": total,
        "returned_count": len(lines),
        "offset": int(result.get("offset", offset)),
        "limit": count,
        "has_more": bool(result.get("has_more", offset + count < total)),
        "run_id": run_id,
        "is_running": result.get("is_running", False),
        "dropped_count": result.get("dropped_count", 0),
        "stale_run_id": bool(result.get("stale_run_id", False)),
    }
    for key in (
        "current_run_id",
        "cursor",
        "oldest_cursor",
        "next_cursor",
        "appended_total",
        "truncated",
        "helper_live",
        "session_active",
        "game_status",
        "editor_errors_count",
        "editor_errors_hint",
    ):
        if key in result:
            response[key] = result[key]
    _forward_error_watermark_stamp(result, response)
    return response


def _forward_error_watermark_stamp(result: dict, response: dict) -> None:
    """Carry the client-injected error/warning-watermark hints through a rebuild.

    ``GodotClient.send`` consumes ``Session.pending_new_errors`` and
    ``Session.pending_new_warnings`` into the raw command result exactly
    once. A handler that rebuilds its response instead of passing the result
    through must re-attach the stamps, or the one delivery is silently
    destroyed — the #641 failure mode (an agent whose first call after a
    broken launch is ``logs_read`` would never learn errors or warnings
    happened).
    """
    for key in (
        "new_errors_since_last_call",
        "new_errors_hint",
        "new_warnings_since_last_call",
        "new_warnings_hint",
    ):
        if key in result:
            response[key] = result[key]


async def editor_reload_plugin(runtime: DirectRuntime) -> dict:
    active = runtime.get_active_session()
    if active is None:
        raise GodotCommandError(
            code=ErrorCode.PLUGIN_DISCONNECTED,
            message=NO_ACTIVE_SESSION_MESSAGE,
            data=no_active_session_data(circuit_open=False),
        )
    old_id = active.session_id

    if runtime_info.is_plugin_managed():
        ## Plugin-managed server: the reload will kill our own process
        ## before any sync `wait_for_session` result can reach the
        ## caller (issue #393). Hand the structured ack back to FastMCP
        ## now so the HTTP response flushes, then dispatch the reload
        ## command from a background task. `new_session_id` is dropped
        ## from this shape because it lives in the *next* server's
        ## registry, which this process can never see.
        task = asyncio.create_task(_dispatch_reload_async(runtime, old_id))
        _pending_reload_tasks.add(task)
        task.add_done_callback(_pending_reload_tasks.discard)
        return {
            "status": "reload_initiated",
            "transport_will_drop": True,
            "old_session_id": old_id,
            "guidance": (
                "Server is plugin-managed; the WebSocket transport will drop "
                "as part of the reload. Reconnect, then call "
                "session_manage(op='list') to find the new session_id."
            ),
        }

    known_ids = {session.session_id for session in runtime.list_sessions()}

    try:
        ## Pin to old_id explicitly so the reload command can't race
        ## active-session changes (e.g. another editor disconnecting mid-call).
        await runtime.send_command("reload_plugin", session_id=old_id, timeout=2.0)
    except (ConnectionError, TimeoutError) as exc:
        logger.debug("Expected disconnect during reload: %s", exc)

    new_session = await runtime.wait_for_session(
        exclude_id=old_id,
        timeout=15.0,
        known_ids=known_ids,
        project_path=active.project_path,
    )

    runtime.set_active_session(new_session.session_id)
    return {
        "status": "reloaded",
        "old_session_id": old_id,
        "new_session_id": new_session.session_id,
    }


async def _dispatch_reload_async(runtime: DirectRuntime, old_id: str) -> None:
    if PLUGIN_MANAGED_RELOAD_DELAY_SEC > 0:
        await asyncio.sleep(PLUGIN_MANAGED_RELOAD_DELAY_SEC)
    try:
        await runtime.send_command("reload_plugin", session_id=old_id, timeout=2.0)
    except (ConnectionError, TimeoutError) as exc:
        logger.debug("Expected disconnect during plugin-managed reload: %s", exc)
    except Exception:
        logger.exception("Unexpected error dispatching plugin-managed reload")


async def editor_quit(runtime: DirectRuntime) -> dict:
    return await runtime.send_command("quit_editor")


async def editor_selection_set(runtime: DirectRuntime, paths: list[str]) -> dict:
    await require_writable_async(runtime)
    return await runtime.send_command("set_selection", {"paths": paths})


async def selection_resource_data(runtime: DirectRuntime) -> dict:
    return await editor_selection_get(runtime)


async def logs_resource_data(runtime: DirectRuntime) -> dict:
    return await runtime.send_command("get_logs", {"count": 100})


async def game_eval(runtime: DirectRuntime, code: str) -> dict:
    """Execute GDScript in the running game. Use 'return' for values.

    Errors come back fast and actionable (#490): a syntax/parse error returns
    ``EVAL_COMPILE_ERROR`` and a runtime error returns ``EVAL_RUNTIME_ERROR``
    with the real message and resolved line, instead of a generic timeout.
    ``EVAL_GAME_NOT_READY`` (#518) means the game can't service evals right
    now: the play session is up but the game-side capture hasn't registered
    yet (let the game finish launching and retry, or check the
    ``_mcp_game_helper`` autoload is enabled), or the game is parked in a
    debugger break / stopped mid-eval (stop and relaunch it). ``EVAL_HUNG``
    (#518) means the eval code itself never finished: a genuine infinite loop
    or never-firing await, aborted by the game's 8s deadline or the editor's
    10s backstop. ``EVAL_RESULT_TOO_LARGE`` (#518) means the eval finished but
    its serialized result exceeds what the debugger channel can carry (~6 MiB)
    — return a smaller slice. Note that ``await`` (timers, signals, frames)
    only progresses while the game window is focused; a backgrounded
    play-in-editor game has a frozen idle loop, so an awaiting eval reads as
    ``EVAL_HUNG`` until the game is focused.
    """
    return await runtime.send_command("game_eval", {"code": code}, timeout=15.0)
