import time
from starlette.requests import Request
from starlette.responses import HTMLResponse
from app import mcp

START_TIME = time.time()


def _uptime() -> str:
    seconds = int(time.time() - START_TIME)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


def _check_salesforce() -> tuple[bool, str]:
    try:
        from app.client import get_sf_client
        sf = get_sf_client()
        sf.query("SELECT Id FROM Organization LIMIT 1")
        return True, "Connected"
    except Exception as e:
        return False, str(e)[:120]


async def status_page(request: Request) -> HTMLResponse:
    sf_ok, sf_msg = _check_salesforce()
    tools = sorted(mcp._tool_manager._tools.keys())
    tool_count = len(tools)
    uptime = _uptime()

    tool_rows = ""
    for name in tools:
        tool = mcp._tool_manager._tools[name]
        desc = (tool.description or "").split("\n")[0][:80]
        tool_rows += f"<tr><td><code>{name}</code></td><td>{desc}</td></tr>\n"

    sf_dot = "🟢" if sf_ok else "🔴"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Armitage Salesforce MCP</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               background: #0f1117; color: #e1e4e8; padding: 2rem; }}
        .container {{ max-width: 720px; margin: 0 auto; }}
        h1 {{ font-size: 1.5rem; margin-bottom: 0.25rem; color: #fff; }}
        .subtitle {{ color: #8b949e; margin-bottom: 2rem; font-size: 0.9rem; }}
        .cards {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin-bottom: 2rem; }}
        .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1.25rem; }}
        .card .label {{ font-size: 0.75rem; color: #8b949e; text-transform: uppercase;
                       letter-spacing: 0.05em; margin-bottom: 0.5rem; }}
        .card .value {{ font-size: 1.5rem; font-weight: 600; }}
        .card .detail {{ font-size: 0.8rem; color: #8b949e; margin-top: 0.25rem; }}
        table {{ width: 100%; border-collapse: collapse; background: #161b22;
                border: 1px solid #30363d; border-radius: 8px; overflow: hidden; }}
        th {{ text-align: left; padding: 0.75rem 1rem; background: #1c2129;
             font-size: 0.75rem; color: #8b949e; text-transform: uppercase;
             letter-spacing: 0.05em; border-bottom: 1px solid #30363d; }}
        td {{ padding: 0.5rem 1rem; border-bottom: 1px solid #21262d; font-size: 0.85rem; }}
        tr:last-child td {{ border-bottom: none; }}
        code {{ background: #1c2129; padding: 0.15rem 0.4rem; border-radius: 4px;
               font-size: 0.8rem; color: #79c0ff; }}
        .section-title {{ font-size: 0.9rem; color: #8b949e; margin-bottom: 0.75rem;
                         text-transform: uppercase; letter-spacing: 0.05em; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Armitage Salesforce MCP</h1>
        <p class="subtitle">Remote MCP server for Salesforce CRUD access</p>

        <div class="cards">
            <div class="card">
                <div class="label">Server</div>
                <div class="value">🟢</div>
                <div class="detail">Running</div>
            </div>
            <div class="card">
                <div class="label">Salesforce</div>
                <div class="value">{sf_dot}</div>
                <div class="detail">{sf_msg}</div>
            </div>
            <div class="card">
                <div class="label">Uptime</div>
                <div class="value">{uptime}</div>
                <div class="detail">{tool_count} tools</div>
            </div>
        </div>

        <p class="section-title">Registered Tools</p>
        <table>
            <tr><th>Tool</th><th>Description</th></tr>
            {tool_rows}
        </table>
    </div>
</body>
</html>"""
    return HTMLResponse(html)
