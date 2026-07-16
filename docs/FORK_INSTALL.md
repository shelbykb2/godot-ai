# Installing a godot-ai fork (Grok Build + project override)

This fork ([shelbykb2/godot-ai](https://github.com/shelbykb2/godot-ai)) tracks
[hi-godot/godot-ai](https://github.com/hi-godot/godot-ai) and adds packaging for
local development plus contributions staged as upstream PRs.

## What is on this fork

1. **Grok Build** client descriptor (dock **Configure** → `~/.grok/config.toml`)
2. **`workflow_manage`** agent helpers (modeling, asset pipeline, screenshot/visual QA, install hints)  
   *(formerly experimental `grok_manage` — renamed for upstream generality)*
3. **Junction-aware** server discovery (`DirAccess.read_link` → fork `.venv`)
4. **PEP 440 local tags** stripped for uvx pins (`3.0.2+grok.4` → `3.0.2`)
5. Nil-lifecycle guard during dual-plugin reload races
6. **Screenshot disk save** (`auto_save` / `screenshot_to_file`) so agents `read_file` PNGs without MCP base64 truncation

## Upstream PR policy

Prefer **small, generic PRs** to hi-godot. Do **not** send this whole branch tip:

| Piece | Upstream? |
|-------|-----------|
| Grok client descriptor | Yes (client PR) |
| `workflow_manage` domain | Yes (workflow PR; generic copy) |
| Junction `read_link` + venv walk + `_pypi_pin_version` | Yes (infra PR) |
| Nil lifecycle guard | Yes (safety PR) |
| Version `3.0.2+grok.*` | **No** (local only) |
| This FORK_INSTALL doc | **No** |

Suggested stack (opened against hi-godot/main):

| Order | PR | Branch |
|-------|-----|--------|
| A | https://github.com/hi-godot/godot-ai/pull/751 | `pr/nil-lifecycle-guard` |
| B | https://github.com/hi-godot/godot-ai/pull/752 | `pr/junction-venv-pin` |
| C | https://github.com/hi-godot/godot-ai/pull/753 | `pr/grok-client` |
| D | https://github.com/hi-godot/godot-ai/pull/754 | `pr/workflow-manage` |

### CONTRIBUTING checklist applied before open

See [docs/CONTRIBUTING.md](CONTRIBUTING.md) + [AGENTS.md](../AGENTS.md):

- Branched from `upstream/main` (not a fat fork tip)
- No `+grok` version or `FORK_INSTALL.md` in upstream PR branches
- Tests for new behavior (Python + Godot-side where the boundary is crossed)
- `ruff check src/ tests/` and full `pytest -v` green on the integration branch
- Stage only intentional paths (no drive-by reformat of unrelated files)
- PR bodies include Motivation / Change / Tests

## Local fork version

| Field | Value |
|-------|--------|
| Plugin / package version | **`3.0.2+grok.4`** |
| Description | Godot AI *(shelbykb2 fork + Grok)* |

## Screenshot agent contract (v3.0.2+grok.4)

| Prefer | Avoid |
|--------|--------|
| `workflow_manage` → `screenshot_to_file` then **read_file(saved_path)** | Huge `include_image=true` at 720–1280px (MCP truncates) |
| `screenshot_verify` with `auto_save=true` (default) | Relying only on inline ImageContent |
| `visual_capture_set` for multi-angle disk shots | |

Default auto-save dir: `res://docs/mcp_captures/` (created on demand).  
Push policy: **`git push origin` only** — never `git push upstream`.

## Paths (example machine)

| Role | Path |
|------|------|
| Fork checkout | `…/godot-ai` |
| Plugin source | `…/godot-ai/plugin/addons/godot_ai` |
| Game project | `…/your-game` |
| Plugin in game | `…/your-game/addons/godot_ai` (**junction preferred**) |
| Backups only | **Outside** `res://` (never under the project tree) |

## Override the stock plugin

### Option A — Directory junction (recommended)

```powershell
$FORK   = "C:\path\to\godot-ai\plugin\addons\godot_ai"
$GAME   = "C:\path\to\your-game\addons\godot_ai"
$BAK    = "C:\path\to\plugin-backups"

New-Item -ItemType Directory -Force -Path $BAK | Out-Null

$item = Get-Item $GAME -Force -ErrorAction SilentlyContinue
if ($item -and -not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
  Copy-Item -Recurse -Force $GAME "$BAK\godot_ai.bak-$(Get-Date -Format yyyyMMddHHmmss)"
  Remove-Item -Recurse -Force $GAME
} elseif ($item) {
  cmd /c rmdir "$GAME"
}

cmd /c mklink /J "$GAME" "$FORK"
```

**Check:** `dir …\addons` shows `<JUNCTION> godot_ai`; `plugin.cfg` has `version="3.0.2+grok.4"`.

### Option B — Physical copy

```powershell
Copy-Item -Recurse -Force $FORK $GAME
```

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
MCP | using dev venv: …\godot-ai\.venv\Scripts\python.exe
```

**Not** `using uvx (godot-ai==3.0.2+grok.4)`.

If uvx still wins: run `setup-dev.ps1`, confirm junction, set `GODOT_AI_VENV_PYTHON`, reload plugin.

## Verify

1. Plugins: one **Godot AI** at `3.0.2+grok.4`.
2. Dock: session connected.
3. Client list includes **Grok Build**.
4. Tools: `workflow_manage` ops  
   `modeling_guidance` · `asset_pipeline` · `screenshot_verify` · `visual_qa` · `install_hints`
5. Example: `modeling_guidance` with `style=stylized_ethereal`; `asset_pipeline` with `path=res://`.

## Dev setup (fork contributors)

```powershell
git clone https://github.com/shelbykb2/godot-ai.git
cd godot-ai
git checkout feature/grok-client-and-tools
.\script\setup-dev.ps1
.venv\Scripts\Activate.ps1
pytest -v tests/unit/test_workflow_handlers.py tests/unit/test_tool_domains.py
```
