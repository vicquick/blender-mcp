FROM python:3.13-slim-trixie

# ============================================================
# Blender MCP Server — socket proxy to Blender plugin
# Connects to the Blender MCP plugin running inside the desktop
# container (aec-web) on port 9876
# 147 tools: Blender core (65) + Bonsai BIM (69) + scene/render (13)
# ============================================================

WORKDIR /app

# The server imports standalone fastmcp (see requirements.txt). This used to
# install only "mcp[cli]>=1.3.0" with no requirements file, so a clean build
# pulled whatever floated newest and a bundled-vs-standalone drift broke the
# next rebuild with no warning.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# The server imports its sibling modules (tool tags, rules), not just itself.
COPY *.py ./

ENV DESKTOP_HOST=aec-web
ENV BLENDER_PORT=9876

# Streamable HTTP transport — accessible from any VPN machine
ENV MCP_TRANSPORT=streamable-http
ENV FASTMCP_HOST=0.0.0.0
ENV FASTMCP_PORT=8082

EXPOSE 8082

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD python3 -c "import socket; s=socket.socket(); s.settimeout(5); s.connect(('localhost',8082)); s.close()"

CMD ["python3", "/app/blender_mcp_server.py"]
