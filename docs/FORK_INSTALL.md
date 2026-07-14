# Installing a godot-ai fork (Grok Build + project override)

This fork (`shelbykb2/godot-ai`) tracks [hi-godot/godot-ai](https://github.com/hi-godot/godot-ai) and adds:

1. **Grok Build** client descriptor (dock **Configure** writes `~/.grok/config.toml`)
2. **`grok_manage`** workflow tools (modeling guidance, asset pipeline scan, screenshot verification, visual QA, install hints)

## Local fork version (pre-upstream PR)

| Field | Value |
|-------|--------|
| Plugin / package version | **`3.0.2+grok.1`** |
| Description | Godot AI *(shelbykb2 fork + Grok)* |

Use this while running the fork **before** any PR to hi-godot is merged. Do **not** treat it as an official 3.0.3 release.

- **Self-update:** with a directory junction / symlink install, Update is blocked. Do not install stock GitHub 3.0.2 over the fork.
- **Python server:** with a **junctioned** plugin, the plugin must
  `DirAccess.read_link` the junction, then walk up to this repo’s `.venv`
  (`MCP | using dev venv: ...\godot-ai\.venv\Scripts\python.exe`).
  Logical `res://addons/godot_ai` alone only walks the *game* project and
  never finds the fork. Required for `grok_manage`.
- If you still see `uvx ...` or Target `3.0.2+grok.1`: run `.\script\setup-dev.ps1`
  here, confirm the junction, Reload Plugin. Optional override:
  `GODOT_AI_VENV_PYTHON=C:\...\godot-ai\.venv\Scripts\python.exe`.

Manual server (optional, `--reload`):

```powershell
cd C:\Users\bellf\OneDrive\Documents\godot-ai
.venv\Scripts\Activate.ps1
python -m godot_ai --transport streamable-http --port 8000 --reload
```

## Grok MCP entry

```toml
# ~/.grok/config.toml  (Windows: %USERPROFILE%\.grok\config.toml)
[mcp_servers.godot-ai]
url = "http://127.0.0.1:8000/mcp"
enabled = true
```

Or use the Godot AI dock → **Grok Build** → **Configure**.

## Override a project’s plugin (e.g. Lumina)

Assume:

- Fork checkout: `C:\Users\bellf\OneDrive\Documents\godot-ai`
- Game project: `C:\Users\bellf\OneDrive\Documents\lumina`

### Option A — Physical copy (release-like)

```powershell
$FORK = "C:\Users\bellf\OneDrive\Documents\godot-ai\plugin\addons\godot_ai"
$LUMINA = "C:\Users\bellf\OneDrive\Documents\lumina\addons\godot_ai"
# IMPORTANT: keep backups *outside the Godot project entirely*.
# - Under addons/: Godot double-enables the plugin (get_version_check on Nil).
# - Under res:// anywhere (e.g. _plugin_backups/): Godot still parses .gd files
#   and floods parse errors. Use a sibling folder outside the project.
$BAK_ROOT = "C:\Users\bellf\OneDrive\Documents\lumina-plugin-backups"
New-Item -ItemType Directory -Force -Path $BAK_ROOT | Out-Null
Copy-Item -Recurse -Force $LUMINA "$BAK_ROOT\godot_ai.bak-$(Get-Date -Format yyyyMMddHHmmss)"
Remove-Item -Recurse -Force $LUMINA
Copy-Item -Recurse -Force $FORK $LUMINA
```

Then in Godot: **Project → Project Settings → Plugins** → disable/enable **Godot AI**, or restart the editor.

### Option B — Directory junction (live fork edits)

```powershell
$FORK = "C:\Users\bellf\OneDrive\Documents\godot-ai\plugin\addons\godot_ai"
$LUMINA = "C:\Users\bellf\OneDrive\Documents\lumina\addons\godot_ai"
# If $LUMINA is a real directory, back it up first.
Remove-Item -Recurse -Force $LUMINA
cmd /c mklink /J "$LUMINA" "$FORK"
```

Self-update will **not** overwrite a junction (plugin guards symlink/junction installs). Prefer this while developing the fork.

### Option C — External Python server (hot reload)

```powershell
cd C:\Users\bellf\OneDrive\Documents\godot-ai
.\script\setup-dev.ps1   # once
.venv\Scripts\Activate.ps1
python -m godot_ai --transport streamable-http --port 8000 --reload
```

Open the game project with the plugin enabled; it adopts the server already listening on port **8000**. Grok keeps the same MCP URL.

## Verify

1. Godot AI dock shows session connected.
2. Client list includes **Grok Build**.
3. From Grok Build: `grok_manage` ops `modeling_guidance`, `asset_pipeline`, `install_hints`.
4. With the game running: `screenshot_verify` with `source=game` (or `visual_qa` with `run_if_needed=true`).

## Upstream PR policy

Open a PR to **hi-godot/godot-ai** only when:

- `ruff check` + `pytest` are green
- GDScript `test_run` is green on `test_project`
- `tool_catalog.gd` matches Python registration
- Features are **generic** (Grok client + workflow helpers), not game-specific hard-coding

Otherwise keep changes on this fork.

## Dev setup (contributors)

```powershell
git clone https://github.com/shelbykb2/godot-ai.git
cd godot-ai
.\script\setup-dev.ps1
.venv\Scripts\Activate.ps1
pytest -v tests/unit/test_grok_handlers.py
ruff check src/godot_ai/handlers/grok.py src/godot_ai/tools/grok.py
```
