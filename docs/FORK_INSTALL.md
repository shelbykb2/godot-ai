# Installing a godot-ai fork (Grok Build + project override)

This fork ([shelbykb2/godot-ai](https://github.com/shelbykb2/godot-ai)) tracks
[hi-godot/godot-ai](https://github.com/hi-godot/godot-ai) and adds:

1. **Grok Build** client descriptor (dock **Configure** → `~/.grok/config.toml`)
2. **`grok_manage`** workflow tools (modeling, asset pipeline, screenshot/visual QA, install hints)
3. **Junction-aware** server discovery (`DirAccess.read_link` → fork `.venv`)

## Status: fork-only (no upstream PR)

**Do not open a PR to hi-godot from this branch tip.** A review found that
`grok_manage` content and fork branding are not trunk-ready for all users.
Keep changes on **shelbykb2**. Optional later: tiny infra-only PRs (junction
realpath, nil-lifecycle guard) without Grok tools or `+grok` versions.

| Piece | Upstream? |
|-------|-----------|
| Grok client descriptor | Maybe later (alone + tests) |
| `grok_manage` domain | No (fork / agent skills) |
| Version `3.0.2+grok.1` | No (local only) |
| Junction `read_link` + venv walk | Maybe later (generalized) |

## Local fork version

| Field | Value |
|-------|--------|
| Plugin / package version | **`3.0.2+grok.1`** |
| Description | Godot AI *(shelbykb2 fork + Grok)* |

## Paths (Lumina machine)

| Role | Path |
|------|------|
| Fork checkout | `C:\Users\bellf\OneDrive\Documents\godot-ai` |
| Plugin source | `...\godot-ai\plugin\addons\godot_ai` |
| Game project | `C:\Users\bellf\OneDrive\Documents\lumina` |
| Plugin in game | `...\lumina\addons\godot_ai` (**junction preferred**) |
| Backups only | `C:\Users\bellf\OneDrive\Documents\lumina-plugin-backups\` (**outside** `res://`) |

## Override the stock plugin

### Option A — Directory junction (recommended)

Live edits to the fork appear in Lumina. Self-update cannot clobber the junction.

```powershell
$FORK   = "C:\Users\bellf\OneDrive\Documents\godot-ai\plugin\addons\godot_ai"
$LUMINA = "C:\Users\bellf\OneDrive\Documents\lumina\addons\godot_ai"
$BAK    = "C:\Users\bellf\OneDrive\Documents\lumina-plugin-backups"

New-Item -ItemType Directory -Force -Path $BAK | Out-Null

# If godot_ai is a real folder (not a junction), back it up OUTSIDE the project
$item = Get-Item $LUMINA -Force -ErrorAction SilentlyContinue
if ($item -and -not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
  Copy-Item -Recurse -Force $LUMINA "$BAK\godot_ai.bak-$(Get-Date -Format yyyyMMddHHmmss)"
  Remove-Item -Recurse -Force $LUMINA
} elseif ($item) {
  # Already a junction/symlink: remove link only
  cmd /c rmdir "$LUMINA"
}

cmd /c mklink /J "$LUMINA" "$FORK"
```

**Check:** `dir ...\lumina\addons` shows `<JUNCTION> godot_ai`; `plugin.cfg` has `version="3.0.2+grok.1"`.

### Option B — Physical copy

```powershell
$FORK   = "C:\Users\bellf\OneDrive\Documents\godot-ai\plugin\addons\godot_ai"
$LUMINA = "C:\Users\bellf\OneDrive\Documents\lumina\addons\godot_ai"
$BAK    = "C:\Users\bellf\OneDrive\Documents\lumina-plugin-backups"
New-Item -ItemType Directory -Force -Path $BAK | Out-Null
Copy-Item -Recurse -Force $LUMINA "$BAK\godot_ai.bak-$(Get-Date -Format yyyyMMddHHmmss)"
Remove-Item -Recurse -Force $LUMINA
Copy-Item -Recurse -Force $FORK $LUMINA
```

Physical copy does **not** auto-find the fork `.venv`. Set:

```powershell
[System.Environment]::SetEnvironmentVariable(
  "GODOT_AI_VENV_PYTHON",
  "C:\Users\bellf\OneDrive\Documents\godot-ai\.venv\Scripts\python.exe",
  "User"
)
```

…or start the server manually (Option C).

### Option C — External Python server

```powershell
cd C:\Users\bellf\OneDrive\Documents\godot-ai
.\script\setup-dev.ps1   # once
.venv\Scripts\python.exe -m godot_ai --transport streamable-http --port 8000 --reload
```

Open Lumina with the plugin enabled; it adopts port **8000**.

## Never do this

- Backup under `addons/godot_ai.bak*` or `res://_plugin_backups` (double plugin load / parse spam).
- Leave `tools/_t3d_extract` or kit extract trees without `.gdignore` if they duplicate addons.
- Click dock **Update** to stock GitHub **3.0.2** over the fork.

## Grok MCP entry

```toml
# %USERPROFILE%\.grok\config.toml
[mcp_servers.godot-ai]
url = "http://127.0.0.1:8000/mcp"
enabled = true
```

Or: Godot AI dock → **Grok Build** → **Configure**.

## Expected Output log (success)

```
MCP | using dev venv: C:\Users\bellf\OneDrive\Documents\godot-ai\.venv\Scripts\python.exe
```

**Not** `using uvx (godot-ai==3.0.2+grok.1)`.

If uvx still wins: run `setup-dev.ps1`, confirm junction, set `GODOT_AI_VENV_PYTHON`, reload plugin.

## Verify

1. Plugins: one **Godot AI** at `3.0.2+grok.1`.
2. Dock: session connected.
3. Client list includes **Grok Build**.
4. Grok Build tools: `grok_manage` ops  
   `modeling_guidance` · `asset_pipeline` · `screenshot_verify` · `visual_qa` · `install_hints`
5. Lumina example: `modeling_guidance` with `style=stylized_ethereal`; `asset_pipeline` with `path=res://`.

## Dev setup (fork contributors)

```powershell
git clone https://github.com/shelbykb2/godot-ai.git
cd godot-ai
git checkout feature/grok-client-and-tools
.\script\setup-dev.ps1
.venv\Scripts\Activate.ps1
pytest -v tests/unit/test_grok_handlers.py
```
