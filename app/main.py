from __future__ import annotations

import csv
import asyncio
import html
import os
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .terminal_manager import TerminalManager


APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
WORKSPACE_ROOT = Path(os.environ.get("TERMINAL_ROOT", os.getcwd())).resolve()
TEXT_EXTENSIONS = {
    ".bash",
    ".bat",
    ".c",
    ".cfg",
    ".conf",
    ".cpp",
    ".css",
    ".csv",
    ".env",
    ".go",
    ".h",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".log",
    ".md",
    ".php",
    ".properties",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
PDF_EXTENSION = ".pdf"
terminal_manager = TerminalManager()

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(application: FastAPI):
    cleanup_task = asyncio.create_task(_cleanup_loop())
    yield
    cleanup_task.cancel()


async def _cleanup_loop() -> None:
    while True:
        terminal_manager.cleanup_idle()
        await asyncio.sleep(60)


app = FastAPI(title="BlackSpider Terminal", lifespan=lifespan)

CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def resolve_workspace_path(raw_path: str | None = None) -> Path:
    requested = raw_path or "."
    candidate = (WORKSPACE_ROOT / requested.lstrip("/")).resolve()
    if candidate != WORKSPACE_ROOT and WORKSPACE_ROOT not in candidate.parents:
        raise ValueError("Path is outside the configured workspace root")
    return candidate


def can_open_in_browser(path: Path) -> bool:
    if not path.is_file():
        return False
    suffix = path.suffix.lower()
    if suffix == PDF_EXTENSION or suffix in TEXT_EXTENSIONS:
        return True
    if suffix:
        return False
    try:
        sample = path.read_bytes()[:2048]
    except OSError:
        return False
    return b"\x00" not in sample


def render_reader_page(title: str, body: str, is_pdf: bool = False) -> str:
    safe_title = html.escape(title)
    content = (
        f'<iframe class="pdf-viewer" src="{body}" title="{safe_title}"></iframe>'
        if is_pdf
        else body
    )
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{safe_title}</title>
    <style>
      :root {{
        color-scheme: dark;
        --bg: #101113;
        --panel: #17191d;
        --text: #e8eaed;
        --muted: #9aa3af;
        --line: #2e333d;
        --accent: #5cc8a7;
      }}
      body {{
        margin: 0;
        min-height: 100vh;
        background: var(--bg);
        color: var(--text);
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }}
      header {{
        display: flex;
        align-items: center;
        gap: 12px;
        min-height: 48px;
        border-bottom: 1px solid var(--line);
        background: var(--panel);
        padding: 8px 14px;
      }}
      h1 {{
        margin: 0;
        overflow: hidden;
        font-size: 14px;
        text-overflow: ellipsis;
        white-space: nowrap;
      }}
      main {{
        height: calc(100vh - 49px);
        overflow: auto;
      }}
      pre {{
        margin: 0;
        padding: 16px;
        color: var(--text);
        font: 13px/1.5 Menlo, Monaco, Consolas, "Liberation Mono", monospace;
        white-space: pre-wrap;
        word-break: break-word;
      }}
      table {{
        border-collapse: collapse;
        min-width: 100%;
        font-size: 13px;
      }}
      td {{
        border: 1px solid var(--line);
        padding: 7px 9px;
        vertical-align: top;
        white-space: pre-wrap;
      }}
      tr:first-child td {{
        color: var(--accent);
        font-weight: 700;
      }}
      .pdf-viewer {{
        width: 100%;
        height: 100%;
        border: 0;
      }}
    </style>
  </head>
  <body>
    <header><h1>{safe_title}</h1></header>
    <main>{content}</main>
  </body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/api/files")
async def list_files(path: str = Query(default=".")) -> dict:
    try:
        target = resolve_workspace_path(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not target.exists():
        return {"error": "Path does not exist", "path": path, "items": []}
    if not target.is_dir():
        target = target.parent

    items = []
    for child in sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        try:
            stat = child.stat()
        except OSError:
            continue
        rel_path = child.relative_to(WORKSPACE_ROOT).as_posix()
        items.append(
            {
                "name": child.name,
                "path": rel_path,
                "is_dir": child.is_dir(),
                "size": stat.st_size,
                "modified": stat.st_mtime,
                "can_open": can_open_in_browser(child),
            }
        )

    rel_target = "." if target == WORKSPACE_ROOT else target.relative_to(WORKSPACE_ROOT).as_posix()
    parent = None
    if target != WORKSPACE_ROOT:
        parent_path = target.parent
        parent = "." if parent_path == WORKSPACE_ROOT else parent_path.relative_to(WORKSPACE_ROOT).as_posix()

    return {
        "root": WORKSPACE_ROOT.as_posix(),
        "path": rel_target,
        "parent": parent,
        "items": items,
    }


@app.get("/api/download")
async def download_file(path: str = Query(...)) -> FileResponse:
    try:
        target = resolve_workspace_path(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Download target must be a file")
    return FileResponse(target, filename=target.name)


@app.post("/api/terminals")
async def create_terminal(cwd: str = Query(default=".")) -> dict:
    try:
        target = resolve_workspace_path(cwd)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not target.is_dir():
        target = WORKSPACE_ROOT
    session = terminal_manager.create(target)
    return {"id": session.id, "cwd": target.relative_to(WORKSPACE_ROOT).as_posix() if target != WORKSPACE_ROOT else "."}


@app.delete("/api/terminals/{session_id}")
async def close_terminal(session_id: str) -> dict:
    closed = terminal_manager.close(session_id)
    return {"closed": closed}


@app.get("/api/raw")
async def raw_file(path: str = Query(...)) -> FileResponse:
    try:
        target = resolve_workspace_path(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not can_open_in_browser(target):
        raise HTTPException(status_code=404, detail="File cannot be opened in browser")

    media_type = "application/pdf" if target.suffix.lower() == PDF_EXTENSION else "text/plain; charset=utf-8"
    return FileResponse(target, media_type=media_type)


@app.get("/view", response_class=HTMLResponse)
async def view_file(path: str = Query(...)) -> str:
    try:
        target = resolve_workspace_path(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not can_open_in_browser(target):
        raise HTTPException(status_code=404, detail="File cannot be opened in browser")

    if target.suffix.lower() == PDF_EXTENSION:
        raw_url = f"/api/raw?path={quote(target.relative_to(WORKSPACE_ROOT).as_posix())}"
        return render_reader_page(target.name, raw_url, is_pdf=True)

    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = target.read_text(encoding="utf-8", errors="replace")

    if target.suffix.lower() == ".csv":
        rows = csv.reader(text.splitlines())
        cells = []
        for row in rows:
            cell_html = "".join(f"<td>{html.escape(cell)}</td>" for cell in row)
            cells.append(f"<tr>{cell_html}</tr>")
        body = f"<table>{''.join(cells)}</table>"
    else:
        body = f"<pre>{html.escape(text)}</pre>"
    return render_reader_page(target.name, body)


@app.websocket("/ws/terminal")
async def terminal_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    cwd_query = websocket.query_params.get("cwd", ".")
    session_id = websocket.query_params.get("id")
    try:
        cwd = resolve_workspace_path(cwd_query)
    except ValueError:
        cwd = WORKSPACE_ROOT
    if not cwd.is_dir():
        cwd = WORKSPACE_ROOT

    session = terminal_manager.get(session_id) if session_id else None
    if session_id and session is None:
        await websocket.send_json({"type": "stale", "id": session_id})
        await websocket.close()
        return
    if session is None:
        session = terminal_manager.create(cwd)
        await websocket.send_json({"type": "session", "id": session.id})
    subscriber = session.subscribe()

    async def send_output() -> None:
        while True:
            chunk = await subscriber.queue.get()
            if chunk is None:
                break
            await websocket.send_bytes(chunk)

    output_task = asyncio.create_task(send_output())
    try:
        while True:
            message = await websocket.receive_json()
            message_type = message.get("type")
            if message_type == "input":
                session.write(message.get("data", ""))
            elif message_type == "resize":
                session.resize(int(message.get("cols", 80)), int(message.get("rows", 24)))
    except WebSocketDisconnect:
        pass
    finally:
        session.unsubscribe(subscriber)
        output_task.cancel()


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    workers = int(os.environ.get("WORKERS", "1"))
    log_level = os.environ.get("LOG_LEVEL", "info")
    reload = os.environ.get("RELOAD", "false").lower() == "true"

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        workers=workers,
        log_level=log_level,
        reload=reload,
    )
