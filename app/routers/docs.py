from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(include_in_schema=False)

SPEC_URL = "/api/v1/docs/openapi.json"


def render_swagger_ui_html(spec_url: str = SPEC_URL) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Dairy Management System - API Documentation</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
  <link rel="icon" type="image/png" href="https://unpkg.com/swagger-ui-dist@5/favicon-32x32.png" sizes="32x32" />
  <style>
    html {{ box-sizing: border-box; overflow: -moz-scrollbars-vertical; overflow-y: scroll; }}
    *, *:before, *:after {{ box-sizing: inherit; }}
    body {{ margin: 0; background: #fafafa; }}
    .topbar {{ background-color: #1e3a8a !important; }}
    .topbar .download-url-wrapper {{ display: none !important; }}
  </style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js" charset="UTF-8"></script>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-standalone-preset.js" charset="UTF-8"></script>
  <script>
    window.onload = function() {{
      window.ui = SwaggerUIBundle({{
        url: "{spec_url}",
        dom_id: '#swagger-ui',
        deepLinking: true,
        presets: [
          SwaggerUIBundle.presets.apis,
          SwaggerUIStandalonePreset
        ],
        plugins: [
          SwaggerUIBundle.plugins.DownloadUrl
        ],
        layout: "StandaloneLayout"
      }});
    }};
  </script>
</body>
</html>"""


@router.get("/docs", response_class=HTMLResponse)
async def docs_at_root() -> HTMLResponse:
    return HTMLResponse(content=render_swagger_ui_html())


@router.get("/api/v1/docs", response_class=HTMLResponse)
async def docs_at_api() -> HTMLResponse:
    return HTMLResponse(content=render_swagger_ui_html())
