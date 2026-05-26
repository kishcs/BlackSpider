from __future__ import annotations

import asyncio
import html
import mimetypes
import os
from pathlib import Path
from urllib.parse import quote

from fastapi import Body, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
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
    ".gradle",
    ".h",
    ".hpp",
    ".htm",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".kt",
    ".log",
    ".md",
    ".mk",
    ".php",
    ".properties",
    ".py",
    ".rb",
    ".rs",
    ".scala",
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
IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".ico",
    ".svg",
}
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
    if suffix == PDF_EXTENSION or suffix in TEXT_EXTENSIONS or suffix in IMAGE_EXTENSIONS:
        return True
    if suffix:
        return False
    try:
        sample = path.read_bytes()[:2048]
    except OSError:
        return False
    return b"\x00" not in sample


def is_editable_text(path: Path) -> bool:
    """Restrict the save endpoint to text files only (never images/PDFs)."""
    if not path.exists():
        return False
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS or suffix == PDF_EXTENSION:
        return False
    return can_open_in_browser(path)


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


def render_image_page(title: str, src_url: str) -> str:
    safe_title = html.escape(title)
    safe_src = html.escape(src_url)
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
        flex: 1;
        overflow: hidden;
        font-size: 14px;
        text-overflow: ellipsis;
        white-space: nowrap;
      }}
      .meta {{
        color: var(--muted);
        font-size: 12px;
      }}
      main {{
        height: calc(100vh - 49px);
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: auto;
        background-image: linear-gradient(45deg, #1a1c20 25%, transparent 25%),
                          linear-gradient(-45deg, #1a1c20 25%, transparent 25%),
                          linear-gradient(45deg, transparent 75%, #1a1c20 75%),
                          linear-gradient(-45deg, transparent 75%, #1a1c20 75%);
        background-size: 24px 24px;
        background-position: 0 0, 0 12px, 12px -12px, 12px 0;
      }}
      img {{
        max-width: 100%;
        max-height: 100%;
        object-fit: contain;
        box-shadow: 0 6px 20px rgba(0, 0, 0, 0.45);
      }}
    </style>
  </head>
  <body>
    <header>
      <h1>{safe_title}</h1>
      <span id="meta" class="meta"></span>
    </header>
    <main><img id="image" src="{safe_src}" alt="{safe_title}" /></main>
    <script>
      const img = document.getElementById("image");
      const meta = document.getElementById("meta");
      img.addEventListener("load", () => {{
        meta.textContent = img.naturalWidth + " × " + img.naturalHeight;
      }});
      img.addEventListener("error", () => {{
        meta.textContent = "Failed to load image";
      }});
    </script>
  </body>
</html>"""


def render_editor_page(title: str, path: str, text: str, preview_kind: str | None = None) -> str:
    safe_title = html.escape(title)
    safe_path = html.escape(path)
    safe_text = html.escape(text)
    preview_kind_attr = html.escape(preview_kind or "")
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
        --danger: #fb7185;
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
        flex: 1;
        overflow: hidden;
        font-size: 14px;
        text-overflow: ellipsis;
        white-space: nowrap;
      }}
      .toolbar {{
        display: flex;
        align-items: center;
        gap: 8px;
      }}
      .status {{
        color: var(--muted);
        font-size: 12px;
        min-width: 120px;
        text-align: right;
      }}
      .status.error {{
        color: var(--danger);
      }}
      .status.success {{
        color: var(--accent);
      }}
      button {{
        background: var(--accent);
        color: #0c0d0f;
        border: 0;
        border-radius: 6px;
        padding: 6px 14px;
        font-size: 13px;
        font-weight: 600;
        cursor: pointer;
      }}
      button:disabled {{
        opacity: 0.5;
        cursor: not-allowed;
      }}
      main {{
        position: relative;
        height: calc(100vh - 49px);
      }}
      .pane {{
        position: absolute;
        inset: 0;
      }}
      .pane.hidden {{
        display: none;
      }}
      textarea {{
        width: 100%;
        height: 100%;
        margin: 0;
        padding: 16px;
        box-sizing: border-box;
        background: var(--bg);
        color: var(--text);
        border: 0;
        outline: none;
        resize: none;
        font: 13px/1.5 Menlo, Monaco, Consolas, "Liberation Mono", monospace;
        white-space: pre;
        tab-size: 4;
      }}
      .preview-frame {{
        width: 100%;
        height: 100%;
        border: 0;
        background: #ffffff;
      }}
      .markdown-body {{
        height: 100%;
        overflow: auto;
        padding: 24px 32px;
        box-sizing: border-box;
        font-size: 14px;
        line-height: 1.6;
      }}
      .markdown-body h1, .markdown-body h2, .markdown-body h3,
      .markdown-body h4, .markdown-body h5, .markdown-body h6 {{
        margin-top: 1.5em;
        margin-bottom: 0.5em;
        line-height: 1.25;
      }}
      .markdown-body h1 {{ font-size: 1.8em; border-bottom: 1px solid var(--line); padding-bottom: 0.3em; }}
      .markdown-body h2 {{ font-size: 1.45em; border-bottom: 1px solid var(--line); padding-bottom: 0.3em; }}
      .markdown-body h3 {{ font-size: 1.2em; }}
      .markdown-body p {{ margin: 0.6em 0; }}
      .markdown-body a {{ color: var(--accent); }}
      .markdown-body code {{
        background: var(--panel);
        border-radius: 4px;
        padding: 2px 5px;
        font: 12.5px/1 Menlo, Monaco, Consolas, monospace;
      }}
      .markdown-body pre {{
        background: var(--panel);
        border-radius: 6px;
        padding: 12px 14px;
        overflow: auto;
      }}
      .markdown-body pre code {{
        background: transparent;
        padding: 0;
      }}
      .markdown-body blockquote {{
        margin: 0.8em 0;
        padding: 0.2em 0.9em;
        border-left: 3px solid var(--line);
        color: var(--muted);
      }}
      .markdown-body ul, .markdown-body ol {{ padding-left: 1.6em; }}
      .markdown-body table {{
        border-collapse: collapse;
        margin: 0.8em 0;
      }}
      .markdown-body th, .markdown-body td {{
        border: 1px solid var(--line);
        padding: 6px 10px;
      }}
      .markdown-body img {{ max-width: 100%; }}
      .markdown-body hr {{ border: 0; border-top: 1px solid var(--line); margin: 1.2em 0; }}
      .csv-wrap {{
        height: 100%;
        overflow: auto;
        padding: 12px;
        box-sizing: border-box;
      }}
      .csv-table {{
        border-collapse: collapse;
        font-size: 13px;
      }}
      .csv-table td {{
        border: 1px solid var(--line);
        padding: 6px 10px;
        vertical-align: top;
        white-space: pre-wrap;
        max-width: 480px;
        word-break: break-word;
      }}
      .csv-table tr:first-child td {{
        color: var(--accent);
        font-weight: 700;
        position: sticky;
        top: 0;
        background: var(--panel);
        z-index: 1;
      }}
      .csv-error {{
        color: var(--danger);
        padding: 16px;
      }}
      .toggle-btn {{
        background: transparent;
        color: var(--text);
        border: 1px solid var(--line);
      }}
      .toggle-btn.active {{
        background: var(--accent);
        color: #0c0d0f;
        border-color: var(--accent);
      }}
    </style>
  </head>
  <body data-preview-kind="{preview_kind_attr}">
    <header>
      <h1>{safe_title}</h1>
      <div class="toolbar">
        <span id="status" class="status"></span>
        <button id="editToggle" class="toggle-btn active" type="button" hidden>Edit</button>
        <button id="previewToggle" class="toggle-btn" type="button" hidden>Preview</button>
        <button id="saveBtn" type="button">Save</button>
      </div>
    </header>
    <main>
      <div id="editorPane" class="pane">
        <textarea id="editor" spellcheck="false" autocomplete="off">{safe_text}</textarea>
      </div>
      <div id="previewPane" class="pane hidden"></div>
    </main>
    <script src="/static/assets/js/marked.min.js"></script>
    <script>
      (function () {{
        const filePath = "{safe_path}";
        const previewKind = document.body.dataset.previewKind || "";
        const editor = document.getElementById("editor");
        const saveBtn = document.getElementById("saveBtn");
        const statusEl = document.getElementById("status");
        const editToggle = document.getElementById("editToggle");
        const previewToggle = document.getElementById("previewToggle");
        const editorPane = document.getElementById("editorPane");
        const previewPane = document.getElementById("previewPane");
        let originalText = editor.value;
        let saving = false;
        let mode = "edit";

        function setStatus(text, kind) {{
          statusEl.textContent = text;
          statusEl.className = "status" + (kind ? " " + kind : "");
        }}

        function updateDirty() {{
          if (saving) return;
          if (editor.value !== originalText) {{
            setStatus("Unsaved changes");
          }} else {{
            setStatus("");
          }}
        }}

        editor.addEventListener("input", updateDirty);

        editor.addEventListener("keydown", function (event) {{
          if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {{
            event.preventDefault();
            save();
          }} else if (event.key === "Tab") {{
            event.preventDefault();
            const start = editor.selectionStart;
            const end = editor.selectionEnd;
            editor.value = editor.value.slice(0, start) + "\\t" + editor.value.slice(end);
            editor.selectionStart = editor.selectionEnd = start + 1;
            updateDirty();
          }}
        }});

        async function save() {{
          if (saving) return;
          saving = true;
          saveBtn.disabled = true;
          setStatus("Saving…");
          try {{
            const response = await fetch("/api/save", {{
              method: "POST",
              headers: {{ "Content-Type": "application/json" }},
              body: JSON.stringify({{ path: filePath, content: editor.value }}),
            }});
            if (!response.ok) {{
              const detail = await response.json().catch(() => ({{}}));
              throw new Error(detail.detail || ("HTTP " + response.status));
            }}
            originalText = editor.value;
            setStatus("Saved", "success");
            setTimeout(function () {{
              if (editor.value === originalText) setStatus("");
            }}, 2000);
            if (mode === "preview") renderPreview();
          }} catch (err) {{
            setStatus("Error: " + err.message, "error");
          }} finally {{
            saving = false;
            saveBtn.disabled = false;
          }}
        }}

        saveBtn.addEventListener("click", save);

        function parseCSV(text) {{
          const rows = [];
          let field = "";
          let row = [];
          let inQuotes = false;
          for (let i = 0; i < text.length; i++) {{
            const c = text[i];
            if (inQuotes) {{
              if (c === '"') {{
                if (text[i + 1] === '"') {{ field += '"'; i++; }}
                else {{ inQuotes = false; }}
              }} else {{
                field += c;
              }}
            }} else {{
              if (c === '"') {{
                inQuotes = true;
              }} else if (c === ",") {{
                row.push(field); field = "";
              }} else if (c === "\\n") {{
                row.push(field); rows.push(row); row = []; field = "";
              }} else if (c === "\\r") {{
                // skip
              }} else {{
                field += c;
              }}
            }}
          }}
          if (field.length > 0 || row.length > 0) {{
            row.push(field);
            rows.push(row);
          }}
          return rows;
        }}

        function renderPreview() {{
          previewPane.innerHTML = "";
          if (previewKind === "html") {{
            const frame = document.createElement("iframe");
            frame.className = "preview-frame";
            frame.setAttribute("sandbox", "allow-same-origin");
            frame.srcdoc = editor.value;
            previewPane.appendChild(frame);
          }} else if (previewKind === "markdown") {{
            const body = document.createElement("div");
            body.className = "markdown-body";
            try {{
              body.innerHTML = window.marked.parse(editor.value, {{ gfm: true, breaks: false }});
            }} catch (err) {{
              body.textContent = "Markdown render error: " + err.message;
            }}
            previewPane.appendChild(body);
          }} else if (previewKind === "csv") {{
            const wrap = document.createElement("div");
            wrap.className = "csv-wrap";
            try {{
              const rows = parseCSV(editor.value);
              if (rows.length === 0) {{
                wrap.innerHTML = '<div class="csv-error">No rows to display.</div>';
              }} else {{
                const table = document.createElement("table");
                table.className = "csv-table";
                for (const r of rows) {{
                  const tr = document.createElement("tr");
                  for (const cell of r) {{
                    const td = document.createElement("td");
                    td.textContent = cell;
                    tr.appendChild(td);
                  }}
                  table.appendChild(tr);
                }}
                wrap.appendChild(table);
              }}
            }} catch (err) {{
              wrap.innerHTML = '<div class="csv-error">CSV parse error: ' + err.message + '</div>';
            }}
            previewPane.appendChild(wrap);
          }}
        }}

        function setMode(next) {{
          mode = next;
          const showPreview = next === "preview";
          editorPane.classList.toggle("hidden", showPreview);
          previewPane.classList.toggle("hidden", !showPreview);
          editToggle.classList.toggle("active", !showPreview);
          previewToggle.classList.toggle("active", showPreview);
          if (showPreview) renderPreview();
        }}

        if (previewKind) {{
          editToggle.hidden = false;
          previewToggle.hidden = false;
          editToggle.addEventListener("click", () => setMode("edit"));
          previewToggle.addEventListener("click", () => setMode("preview"));
        }}
      }})();
    </script>
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

    suffix = target.suffix.lower()
    if suffix == PDF_EXTENSION:
        media_type = "application/pdf"
    elif suffix in IMAGE_EXTENSIONS:
        media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    else:
        media_type = "text/plain; charset=utf-8"
    return FileResponse(target, media_type=media_type)


@app.get("/view", response_class=HTMLResponse)
async def view_file(path: str = Query(...)) -> str:
    try:
        target = resolve_workspace_path(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not can_open_in_browser(target):
        raise HTTPException(status_code=404, detail="File cannot be opened in browser")

    suffix = target.suffix.lower()
    rel_url_path = quote(target.relative_to(WORKSPACE_ROOT).as_posix())

    if suffix == PDF_EXTENSION:
        return render_reader_page(target.name, f"/api/raw?path={rel_url_path}", is_pdf=True)

    if suffix in IMAGE_EXTENSIONS:
        return render_image_page(target.name, f"/api/raw?path={rel_url_path}")

    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = target.read_text(encoding="utf-8", errors="replace")

    if suffix in {".html", ".htm"}:
        preview_kind = "html"
    elif suffix == ".md":
        preview_kind = "markdown"
    elif suffix == ".csv":
        preview_kind = "csv"
    else:
        preview_kind = None

    rel_path = target.relative_to(WORKSPACE_ROOT).as_posix()
    return render_editor_page(target.name, rel_path, text, preview_kind=preview_kind)


@app.post("/api/save")
async def save_file(payload: dict = Body(...)) -> dict:
    raw_path = payload.get("path")
    content = payload.get("content")
    if not isinstance(raw_path, str) or not isinstance(content, str):
        raise HTTPException(status_code=400, detail="path and content are required")
    try:
        target = resolve_workspace_path(raw_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if target.exists() and not target.is_file():
        raise HTTPException(status_code=400, detail="Target is not a file")
    if not is_editable_text(target):
        raise HTTPException(status_code=400, detail="File type is not editable")
    target.write_text(content, encoding="utf-8")
    return {"saved": True, "path": target.relative_to(WORKSPACE_ROOT).as_posix(), "bytes": len(content.encode("utf-8"))}


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
