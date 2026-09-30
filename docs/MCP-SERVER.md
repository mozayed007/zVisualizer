# MCP access server

The visualizer agent is exposed over [MCP](https://modelcontextprotocol.io) so other agents (coding agents such as OpenCode, Claude Code, Codex) can request illustrations and interactive visuals and receive ordinary files they can embed, open, or commit.

The server is a standalone process (`visualizer-mcp`) that imports the backend services directly. It does not need the FastAPI server or the web app running, and it reuses the same rate limiting, widget validation, repair, and visual recovery as the chat app.

```
visualizer-mcp  ──uses──>  ChatService (Gemini)  ──validates──>  widget contract
      │
      ├─ writes .svg / .png / .html artifacts to disk (+ manifest.json)
      └─ returns paths, widget code, and the PNG as an inline image
```

## Install

From the repository root, in the backend virtualenv:

```bash
cd apps/backend
pip install -e ".[mcp]"                       # MCP server only
pip install -e ".[mcp,render]"                # + Playwright for PNG screenshots
playwright install chromium                   # one-time browser download (recommended)
```

PNG rendering degrades gracefully:

| Backend | Coverage | Install |
|---------|----------|---------|
| Playwright (Chromium) | SVG and HTML widgets, exact colors/fonts | `pip install -e ".[mcp,render]"` + `playwright install chromium` |
| ImageMagick / Inkscape / rsvg-convert | SVG only, via a theme-flattened copy | system package manager |

Without either, `visualize` still returns `.svg` and `.html` files with a warning. `.svg` and `.html` never need a renderer.

Environment: `GOOGLE_API_KEY` (required, same `.env` as the backend), `VISUALIZER_MCP_ARTIFACT_DIR` (optional, defaults to `~/.visualizer-agent/artifacts`), `CHAT_API_KEY` (HTTP transport auth).

## Run

```bash
# stdio (what local coding agents spawn)
apps/backend/.venv/Scripts/python.exe -m app.mcp --transport stdio

# streamable HTTP (remote or multi-client; binds 127.0.0.1 by default)
apps/backend/.venv/Scripts/python.exe -m app.mcp --transport http --host 127.0.0.1 --port 8765
```

The console script `visualizer-mcp` behaves the same once the backend package is installed.

## Client configuration

OpenCode (`opencode.json`):

```json
{
  "mcp": {
    "visualizer": {
      "type": "local",
      "command": ["C:\\projects\\visualizer-agent\\apps\\backend\\.venv\\Scripts\\python.exe", "-m", "app.mcp", "--transport", "stdio"],
      "enabled": true
    }
  }
}
```

Claude Code:

```bash
claude mcp add visualizer -- C:\projects\visualizer-agent\apps\backend\.venv\Scripts\python.exe -m app.mcp --transport stdio
```

Generic MCP clients (`.mcp.json` style):

```json
{
  "mcpServers": {
    "visualizer": {
      "type": "stdio",
      "command": "C:\\projects\\visualizer-agent\\apps\\backend\\.venv\\Scripts\\python.exe",
      "args": ["-m", "app.mcp", "--transport", "stdio"]
    }
  }
}
```

Remote clients: point them at `http://<host>:8765/mcp` (streamable HTTP). When `CHAT_API_KEY` is set, the server enforces `Authorization: Bearer <CHAT_API_KEY>` on every request; without it, bind to `127.0.0.1` or a private network (Tailscale) only and do not expose the port.

## Tools

| Tool | Model call | Purpose |
|------|-----------|---------|
| `visualize` | yes | Generate a visual from a prompt; writes `svg`/`png`/`html` artifacts |
| `render_visual` | no | Validate + render widget code you already have |
| `validate_visual` | no | Contract check with violations (cheap preflight when authoring SVG yourself) |
| `list_svg_templates` | no | List SVG template ids for the `svg` agent (optional `query`, `limit`) |
| `get_svg_template` | no | Fetch one template's source and metadata |
| `get_capabilities` | no | Agents, renderers on this machine, artifact root |

### `visualize`

Parameters: `prompt`, `agent_id` (`visualizer` default, `svg` for brand templates), `model`, `subject`, `conversation_id` (pass back for follow-ups), `theme` (`light`/`dark`), `formats` (default `["svg","png"]` for SVG widgets, `["html","png"]` for HTML widgets), `scale` (PNG pixel factor, default 2), `output_dir` (write into your project, e.g. `./docs/assets`), `include_code`, `inline_image`, `timeout_s` (default 240), `settle_ms`.

Returns JSON text with `status`, `conversation_id`, `title`, `kind`, `assistant_text`, `follow_up_chips`, `widget_code` (unless `include_code` is false), `files[]`, `warnings[]`, `manifest_path`, plus the PNG as an inline image when available.

Behavior notes:

- `status: "no_visual"` means the agent answered without producing a visual (the answer text and warnings explain why). Hard failures (rate limit, model error, timeout) come back as tool errors.
- Progress is reported through MCP log/progress notifications: "Request received", "Rendering visual", "Visual ready: <title>", and so on.
- Files are written idempotently; re-running the same title/theme/format overwrites.

### `render_visual`

Parameters: `widget_code`, `title`, `template_id` (svg-agent template path), `agent_id`, `theme`, `formats`, `scale`, `output_dir`, `settle_ms`.

Validation matches the platform contract exactly (same validator the chat app uses); invalid code fails with the first violation message.

### `validate_visual`

Parameters: `widget_code`, `title`, `template_id`, `agent_id`. Returns `valid`, `kind`, `errors[]`, `violations[]`. Useful when a coding agent wants to author contract-compliant SVG itself: iterate with `validate_visual` until clean, then `render_visual` to get files.

### SVG template library (`svg` agent)

`list_svg_templates` (optional `query`, `limit`) enumerates template ids like `sequence/sequence-4.svg`; `get_svg_template` returns one template's raw SVG so a caller (or the `svg` agent) can populate it. Render populated copies with `render_visual(template_id=...)`, which runs the template-instance validator against the source.

## Artifacts on disk

```
<root>/<conversation_id | manual>/<widget_title>/
    manifest.json
    <widget_title>.<theme>.svg
    <widget_title>.<theme>.png
    <widget_title>.<theme>.html
```

`manifest.json` records the prompt, conversation, agent, model, theme, scale, files, and warnings, so a repository can trace where an image came from. When `output_dir` is passed, files land directly in that directory instead.

Renderer notes:

- `.svg` embeds the full theme stylesheet and pins the theme with a root class, so it renders correctly in browsers and image viewers.
- `.png` is a headless-Chromium screenshot at `680 * scale` px wide; dark mode paints its own surface color.
- `.html` is a complete standalone document that keeps widget interactivity (CDN scripts from the allowlisted hosts) and a bridge shim: `window.sendPrompt` dispatches a `visualizer:prompt` CustomEvent, `window.openLink` opens the URL. Most widgets work from `file://`; if a specific CDN combination misbehaves, serve the directory over HTTP.

## Security and operational notes

- stdio transport is local-only. HTTP binds `127.0.0.1` by default and enforces `Authorization: Bearer <CHAT_API_KEY>` on every request when the key is set. If you bind to a non-local host without a key, the server logs a prominent warning.
- Artifacts are as trustworthy as the model that produced them; HTML widgets execute their own CDN scripts. Keep the artifact root out of sensitive locations.
- Rate limiting is per process: running the MCP server alongside the backend means two independent limiters. The SQLite conversation store is shared; avoid heavy concurrent writes from both processes.
- Config, skill docs, and generated theme assets are loaded at process start. After editing `config/`, `skills/`, or regenerating theme assets, restart the MCP server.
- Available models are discovered dynamically by the backend agent config; `get_capabilities` reports each agent's configured default model.

## Maintaining the theme contract

The widget theme stylesheet is owned by the frontend (`apps/frontend/src/lib/designTokens.ts`). After changing it:

```bash
cd apps/frontend
bun run export:theme
```

This regenerates `apps/backend/app/mcp/render/assets/widget-theme.{css,json}`. Both sides are guarded: the frontend bun test (`src/lib/__tests__/themeAssetSync.test.ts`) fails when the generated files drift from the TypeScript source, and the backend pytest suite asserts the same contract surfaces in the generated assets.
