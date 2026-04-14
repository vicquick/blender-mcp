# Blender MCP — aec-web edition

Modular Blender MCP plugin + Docker-ready MCP server for AEC / BIM workflows.

**Fork of** [ahujasid/blender-mcp](https://github.com/ahujasid/blender-mcp) — original single-file addon preserved at repo root. This directory (`aec/`) contains additions by [@vicquick](https://github.com/vicquick), built for the [aec-web](https://github.com/vicquick/aec-web) browser-accessible AEC desktop.

## What's different from upstream

| Feature | Upstream | This fork (`aec/`) |
|---|---|---|
| Plugin structure | Single `addon.py` | Modular package, 30 handler modules |
| Tools | ~15 core Blender | **147** (65 Blender + 69 Bonsai BIM + 13 scene/render) |
| Bonsai BIM support | No | Yes (IFC classification, clash, cost, drawings, spatial, structural, materials, psets, schedules, systems, types, validation) |
| MCP transport | stdio (local) | streamable-HTTP (Docker + Traefik reverse proxy) |
| Deployment | Manual local | Docker + Coolify |

## Quick install

### 1. Install the Blender addon

Copy `aec/plugin/` into Blender's addons folder, rename to `blender_mcp_plugin`:

```bash
# Linux / WSL
cp -r aec/plugin ~/.config/blender/5.1/scripts/addons/blender_mcp_plugin

# macOS
cp -r aec/plugin ~/Library/Application\ Support/Blender/5.1/scripts/addons/blender_mcp_plugin

# Windows
# Copy to %APPDATA%\Blender Foundation\Blender\5.1\scripts\addons\blender_mcp_plugin
```

In Blender:
1. Edit → Preferences → Add-ons
2. Enable "Interface: Blender MCP"
3. Sidebar (N key) → MCP → **Start Server** (default port 9876)

### 2. Run the MCP server (Docker)

```bash
cd aec/server
docker build -t blender-mcp .
docker run -d --name blender-mcp \
  -p 8082:8082 \
  -e DESKTOP_HOST=host.docker.internal \
  -e BLENDER_PORT=9876 \
  blender-mcp
```

MCP endpoint: `http://localhost:8082/mcp` (streamable-HTTP)

### 3. Connect Claude

Add to your `~/.claude.json` or MCP client config:

```json
{
  "mcpServers": {
    "blender-mcp": {
      "type": "streamable-http",
      "url": "http://localhost:8082/mcp"
    }
  }
}
```

## Architecture

```
Claude (MCP client)
    │
    │ streamable-HTTP :8082
    ▼
Docker container: blender-mcp
    │
    │ TCP socket :9876 (JSON framing)
    ▼
Blender (running blender_mcp_plugin)
    │
    │ bpy.app.timers polling
    ▼
Main thread: bpy + Bonsai BIM API calls
```

Non-blocking socket server polled by `bpy.app.timers` (main thread) — no background threads touch Blender data.

## Requirements

- Blender 5.1+ (Python 3.13)
- Bonsai BIM (bundled as Blender extension) for BIM tools
- Docker + Docker Compose for MCP server deployment

## Development

Plugin handlers live in `aec/plugin/handlers/`. Each handler registers tools via the `@handler` decorator in a module. Adding a new handler:

1. Create `aec/plugin/handlers/my_handler.py`
2. Register in `aec/plugin/handlers/__init__.py`
3. Restart Blender

MCP server proxy is in `aec/server/blender_mcp_server.py` — regenerate tool list from plugin's registered handlers and expose via `FastMCP`.

## Credits

- **Upstream concept**: [ahujasid/blender-mcp](https://github.com/ahujasid/blender-mcp) (MIT)
- **Additions**: [@vicquick](https://github.com/vicquick), AI-assisted with Claude Sonnet 4.6 / Opus 4.6 (Anthropic)
- **Bonsai BIM**: [BonsaiBIM](https://bonsaibim.org/) — IFC operations via IfcOpenShell

See [`NOTICE`](../NOTICE) at repo root for full attribution.
