# BlackSpider Terminal

A FastAPI web application with multiple PTY-backed terminal tabs, a workspace file navigator, file downloads, customizable settings, and dark/light themes — all served locally with zero CDN dependencies.

## Quick Start

```bash
./setup.sh    # one-time: creates venv and installs dependencies
./start.sh    # starts the server
```

Open `http://127.0.0.1:8000`.

## Features

### Terminal

- Multiple terminal tabs backed by real pseudo-terminals (PTY)
- "+" tab always visible at the end of the tab bar for quick terminal creation
- WebSocket-based live I/O with xterm.js rendering
- Sessions persist across browser refreshes (stored in `localStorage`, kept alive server-side for 30 minutes by default)
- Configurable default shell prompt (`\u@\h:\W \$` by default)

### File Navigator

- Sidebar file browser rooted at `TERMINAL_ROOT`
- Breadcrumb navigation with an editable path input — click the pencil icon to type or paste a path directly
- In-browser file viewer for text files, CSVs (rendered as tables), and PDFs
- File downloads
- Path sandboxing prevents navigation outside the workspace root

### Settings Panel

Click the gear icon in the topbar to open the settings panel. All changes apply instantly to open terminals and persist across sessions.

- **Accent color** — 8 color presets (teal, blue, purple, rose, amber, green, orange, sky) that update the entire UI and terminal cursor
- **Terminal font size** — adjustable from 10px to 22px via slider
- **Terminal font family** — Menlo/Monaco, Fira Code, JetBrains Mono, Source Code Pro, Cascadia Code, Courier New
- **Cursor style** — block, underline, or bar
- **Cursor blink** — toggle on/off
- **Show file pane** — toggle the sidebar to maximize terminal space

### Theming

- Dark and light themes toggled via the Theme button in the topbar
- Accent color adapts per theme (each swatch has a dark and light variant)

### Other

- Spider favicon (SVG, scales cleanly at all sizes)
- Fully self-contained — xterm.js, xterm.css, and addon-fit.js are served locally under `static/assets/`
- Responsive layout with a mobile breakpoint at 780px

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `TERMINAL_ROOT` | Current working directory | Root directory for terminals and file browsing |
| `TERMINAL_SHELL` | `/bin/bash` | Shell launched in each terminal tab |
| `TERMINAL_PS1` | `\u@\h:\W \$ ` | Default shell prompt for terminal sessions |
| `TERMINAL_IDLE_TTL_SECONDS` | `1800` | Seconds before idle (detached) sessions are cleaned up |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |
| `WORKERS` | `1` | Number of uvicorn workers |
| `LOG_LEVEL` | `info` | Uvicorn log level |
| `RELOAD` | `false` | Set to `true` to enable auto-reload during development |

Example with overrides:

```bash
TERMINAL_ROOT=/home/user/projects PORT=9000 RELOAD=true ./start.sh
```

## Project Structure

```
BlackSpider/
├── setup.sh                 # One-time environment setup
├── start.sh                 # App server launcher
├── requirements.txt         # Python dependencies (FastAPI, uvicorn)
├── README.md
└── app/
    ├── __init__.py
    ├── main.py              # FastAPI routes and file APIs
    ├── terminal.py          # PTY session management
    ├── terminal_manager.py  # Session lifecycle and idle cleanup
    └── static/
        ├── index.html       # Single-page app shell
        ├── favicon.svg      # Spider favicon
        └── assets/
            ├── css/
            │   ├── styles.css   # App styles and settings panel
            │   └── xterm.css    # Terminal styles (local)
            └── js/
                ├── app.js           # App logic, tabs, settings, file nav
                ├── xterm.min.js     # xterm.js (local)
                └── addon-fit.min.js # xterm fit addon (local)
```

## Notes

- Commands run in a real pseudo-terminal using the server host shell, so behavior follows the Linux or macOS environment where it is deployed.
- The file API prevents navigation outside `TERMINAL_ROOT`.
- This app exposes shell access to the host. Put it behind authentication, TLS, and network restrictions before deploying anywhere shared.
