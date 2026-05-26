const TERMINAL_STORAGE_KEY = "blackspider.terminals";
const SETTINGS_STORAGE_KEY = "blackspider.settings";
const FILE_PATH_STORAGE_KEY = "blackspider.filePath";

const state = {
  terminals: new Map(),
  fileTabs: new Map(),
  activeId: null,
  nextId: 1,
  nextFileId: 1,
  filePath: localStorage.getItem(FILE_PATH_STORAGE_KEY) || ".",
  theme: localStorage.getItem("theme") || "dark",
};

const DEFAULT_SETTINGS = {
  accentDark: "#5cc8a7",
  accentLight: "#007a67",
  fontSize: 13,
  fontFamily: 'Menlo, Monaco, Consolas, "Liberation Mono", monospace',
  cursorStyle: "block",
  cursorBlink: true,
  showFilePane: true,
};

function loadSettings() {
  try {
    const raw = localStorage.getItem(SETTINGS_STORAGE_KEY);
    return raw ? { ...DEFAULT_SETTINGS, ...JSON.parse(raw) } : { ...DEFAULT_SETTINGS };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

function saveSettings(settings) {
  localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
}

const settings = loadSettings();

const tabsEl = document.getElementById("tabs");
const hostEl = document.getElementById("terminalHost");
const fileListEl = document.getElementById("fileList");
const breadcrumbsEl = document.getElementById("breadcrumbs");
const rootLabelEl = document.getElementById("rootLabel");
const emptyTerminalStateEl = document.getElementById("emptyTerminalState");

document.documentElement.dataset.theme = state.theme;

function icon(name) {
  const icons = {
    "refresh-cw": "↻",
    plus: "+",
    "sun-moon": "◐",
    x: "×",
    folder: "▸",
    file: "□",
    download: "↓",
    open: "↗",
  };
  return `<span class="app-icon" aria-hidden="true">${icons[name] || "•"}</span>`;
}

function activeTabCount() {
  return state.terminals.size + state.fileTabs.size;
}

function updateEmptyState() {
  emptyTerminalStateEl.classList.toggle("visible", activeTabCount() === 0);
}

function readSavedTerminals() {
  const raw = localStorage.getItem(TERMINAL_STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw);
    return {
      activeId: parsed.activeId || null,
      terminals: Array.isArray(parsed.terminals) ? parsed.terminals : [],
    };
  } catch {
    return null;
  }
}

function saveTerminalState() {
  const terminals = [...state.terminals.values()].map((session) => ({
    id: session.id,
    title: session.title,
  }));
  localStorage.setItem(
    TERMINAL_STORAGE_KEY,
    JSON.stringify({
      activeId: state.terminals.has(state.activeId) ? state.activeId : null,
      terminals,
    }),
  );
}

function refreshIcons() {
  return undefined;
}

function terminalTheme() {
  if (state.theme === "light") {
    return {
      background: "#fbfbfc",
      foreground: "#17202a",
      cursor: settings.accentLight,
      selectionBackground: "#c7efe5",
    };
  }
  return {
    background: "#0c0d0f",
    foreground: "#e8eaed",
    cursor: settings.accentDark,
    selectionBackground: "#244f44",
  };
}

async function createTerminal(options = {}) {
  emptyTerminalStateEl.classList.remove("visible");
  let id = options.id;
  if (!id) {
    const response = await fetch(`/api/terminals?cwd=${encodeURIComponent(state.filePath)}`, { method: "POST" });
    const data = await response.json();
    id = data.id;
  }
  const title = options.title || `Terminal ${state.nextId++}`;
  const titleMatch = title.match(/^Terminal (\d+)$/);
  if (titleMatch) {
    state.nextId = Math.max(state.nextId, Number(titleMatch[1]) + 1);
  }
  const surface = document.createElement("div");
  surface.className = "terminal-surface";
  hostEl.appendChild(surface);

  const hasXterm = Boolean(window.Terminal && window.FitAddon);
  const term = hasXterm
    ? new Terminal({
        cursorBlink: settings.cursorBlink,
        cursorStyle: settings.cursorStyle,
        convertEol: true,
        fontFamily: settings.fontFamily,
        fontSize: settings.fontSize,
        theme: terminalTheme(),
      })
    : createFallbackTerminal(surface);
  const fit = hasXterm ? new FitAddon.FitAddon() : { fit: () => undefined };
  if (hasXterm) {
    term.loadAddon(fit);
    term.open(surface);
  }

  const session = {
    id,
    title,
    term,
    fit,
    socket: null,
    surface,
    closing: false,
    stale: false,
  };
  state.terminals.set(id, session);

  const terminalUrl = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/terminal?id=${encodeURIComponent(id)}&cwd=${encodeURIComponent(state.filePath)}`;
  const socket = new WebSocket(terminalUrl);
  session.socket = socket;
  socket.binaryType = "arraybuffer";
  socket.addEventListener("open", () => {
    fit.fit();
    socket.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
    term.focus();
  });
  socket.addEventListener("message", (event) => {
    if (event.data instanceof ArrayBuffer) {
      term.write(new Uint8Array(event.data));
      return;
    }
    try {
      const message = JSON.parse(event.data);
      if (message.type === "stale") {
        session.stale = true;
        closeTerminal(id, { terminate: false });
        return;
      }
    } catch {
      term.write(event.data);
    }
  });
  socket.addEventListener("close", () => {
    if (!session.closing && !session.stale) {
      term.writeln("\r\n[disconnected]");
    }
  });

  term.onData((data) => {
    if (socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "input", data }));
    }
  });
  term.onResize(({ cols, rows }) => {
    if (socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "resize", cols, rows }));
    }
  });

  setActiveTerminal(id);
  renderTabs();
  saveTerminalState();
}

function createFallbackTerminal(surface) {
  const textarea = document.createElement("textarea");
  textarea.className = "terminal-fallback";
  textarea.spellcheck = false;
  textarea.autocapitalize = "off";
  textarea.autocomplete = "off";
  surface.appendChild(textarea);
  const decoder = new TextDecoder();
  let inputHandler = () => undefined;

  textarea.addEventListener("keydown", (event) => {
    const specialKeys = {
      Enter: "\r",
      Backspace: "\u007f",
      Tab: "\t",
      ArrowUp: "\u001b[A",
      ArrowDown: "\u001b[B",
      ArrowRight: "\u001b[C",
      ArrowLeft: "\u001b[D",
      Escape: "\u001b",
    };
    if (event.ctrlKey && event.key.length === 1) {
      inputHandler(String.fromCharCode(event.key.toUpperCase().charCodeAt(0) - 64));
      event.preventDefault();
      return;
    }
    if (specialKeys[event.key]) {
      inputHandler(specialKeys[event.key]);
      event.preventDefault();
      return;
    }
    if (!event.metaKey && !event.altKey && event.key.length === 1) {
      inputHandler(event.key);
      event.preventDefault();
    }
  });

  textarea.addEventListener("paste", (event) => {
    const text = event.clipboardData?.getData("text");
    if (text) {
      inputHandler(text);
      event.preventDefault();
    }
  });

  return {
    cols: 100,
    rows: 30,
    options: { theme: terminalTheme() },
    focus: () => textarea.focus(),
    dispose: () => textarea.remove(),
    loadAddon: () => undefined,
    open: () => undefined,
    onResize: () => undefined,
    onData: (handler) => {
      inputHandler = handler;
    },
    write: (data) => {
      textarea.value += data instanceof Uint8Array ? decoder.decode(data) : data;
      textarea.scrollTop = textarea.scrollHeight;
    },
    writeln: (data) => {
      textarea.value += `${data}\n`;
      textarea.scrollTop = textarea.scrollHeight;
    },
  };
}

function setActiveTerminal(id) {
  state.activeId = id;
  for (const session of state.terminals.values()) {
    session.surface.classList.toggle("active", session.id === id);
  }
  for (const fileTab of state.fileTabs.values()) {
    fileTab.surface.classList.toggle("active", fileTab.id === id);
  }
  updateEmptyState();
  renderTabs();
  saveTerminalState();
  const session = state.terminals.get(id);
  if (session) {
    requestAnimationFrame(() => {
      session.fit.fit();
      session.term.focus();
    });
  }
}

function setActiveFileTab(id) {
  state.activeId = id;
  for (const session of state.terminals.values()) {
    session.surface.classList.toggle("active", false);
  }
  for (const fileTab of state.fileTabs.values()) {
    fileTab.surface.classList.toggle("active", fileTab.id === id);
  }
  updateEmptyState();
  renderTabs();
}

function openFileTab(item) {
  const existing = [...state.fileTabs.values()].find((fileTab) => fileTab.path === item.path);
  if (existing) {
    setActiveFileTab(existing.id);
    return;
  }

  emptyTerminalStateEl.classList.remove("visible");
  const id = `file-${state.nextFileId++}`;
  const surface = document.createElement("div");
  surface.className = "file-view-surface";
  surface.innerHTML = `
    <iframe
      class="file-view-frame"
      src="/view?path=${encodeURIComponent(item.path)}"
      title="${escapeHtml(item.name)}"
    ></iframe>
  `;
  hostEl.appendChild(surface);

  state.fileTabs.set(id, {
    id,
    path: item.path,
    title: item.name,
    surface,
  });
  setActiveFileTab(id);
}

async function closeTerminal(id, options = { terminate: true }) {
  const session = state.terminals.get(id);
  if (!session) return;
  session.closing = true;
  if (options.terminate) {
    fetch(`/api/terminals/${encodeURIComponent(id)}`, { method: "DELETE", keepalive: true }).catch(() => undefined);
  }
  session.socket.close();
  session.term.dispose();
  session.surface.remove();
  state.terminals.delete(id);

  if (state.activeId === id) {
    const next = state.terminals.keys().next().value;
    if (next) {
      setActiveTerminal(next);
    } else {
      state.activeId = null;
      const nextFile = state.fileTabs.keys().next().value;
      if (nextFile) {
        setActiveFileTab(nextFile);
      } else {
        updateEmptyState();
      }
    }
  }
  renderTabs();
  saveTerminalState();
}

function closeFileTab(id) {
  const fileTab = state.fileTabs.get(id);
  if (!fileTab) return;
  fileTab.surface.remove();
  state.fileTabs.delete(id);

  if (state.activeId === id) {
    const nextTerminal = state.terminals.keys().next().value;
    const nextFile = state.fileTabs.keys().next().value;
    if (nextTerminal) {
      setActiveTerminal(nextTerminal);
    } else if (nextFile) {
      setActiveFileTab(nextFile);
    } else {
      state.activeId = null;
      updateEmptyState();
    }
  }
  renderTabs();
}

function renderTabs() {
  tabsEl.innerHTML = "";
  for (const session of state.terminals.values()) {
    const tab = document.createElement("button");
    tab.className = `tab${session.id === state.activeId ? " active" : ""}`;
    tab.type = "button";
    tab.innerHTML = `<span class="tab-title">${session.title}</span><span class="tab-close" title="Close terminal">${icon("x")}</span>`;
    tab.addEventListener("click", () => setActiveTerminal(session.id));
    tab.querySelector(".tab-close").addEventListener("click", (event) => {
      event.stopPropagation();
      closeTerminal(session.id);
    });
    tabsEl.appendChild(tab);
  }
  for (const fileTab of state.fileTabs.values()) {
    const tab = document.createElement("button");
    tab.className = `tab file-tab${fileTab.id === state.activeId ? " active" : ""}`;
    tab.type = "button";
    tab.innerHTML = `<span class="tab-title">${escapeHtml(fileTab.title)}</span><span class="tab-close" title="Close file">${icon("x")}</span>`;
    tab.addEventListener("click", () => setActiveFileTab(fileTab.id));
    tab.querySelector(".tab-close").addEventListener("click", (event) => {
      event.stopPropagation();
      closeFileTab(fileTab.id);
    });
    tabsEl.appendChild(tab);
  }

  // Always show a "+" tab at the end to create a new terminal
  const addTab = document.createElement("button");
  addTab.className = "tab tab-add";
  addTab.type = "button";
  addTab.title = "New terminal";
  addTab.setAttribute("aria-label", "New terminal");
  addTab.innerHTML = `<span class="tab-title">${icon("plus")}</span>`;
  addTab.addEventListener("click", () => createTerminal());
  tabsEl.appendChild(addTab);

  refreshIcons();
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[index]}`;
}

async function loadFiles(path = state.filePath) {
  const response = await fetch(`/api/files?path=${encodeURIComponent(path)}`);
  const data = await response.json();
  if (data.error && path !== ".") {
    return loadFiles(".");
  }
  state.filePath = data.path || ".";
  localStorage.setItem(FILE_PATH_STORAGE_KEY, state.filePath);
  rootLabelEl.textContent = data.root || "";
  renderBreadcrumbs(state.filePath);
  renderFiles(data);
}

function breadcrumbDisplayPath(path) {
  return path === "." ? "root" : "root / " + path.split("/").join(" / ");
}

function enterBreadcrumbEditMode() {
  breadcrumbsEl.innerHTML = "";
  const input = document.createElement("input");
  input.type = "text";
  input.className = "breadcrumb-input";
  input.value = state.filePath === "." ? "" : state.filePath;
  input.placeholder = "Enter path (e.g. app/static)";
  input.setAttribute("aria-label", "Navigate to path");
  breadcrumbsEl.appendChild(input);
  input.focus();
  input.select();

  let committed = false;
  function commit() {
    if (committed) return;
    committed = true;
    const value = input.value.trim();
    const target = value === "" ? "." : value;
    loadFiles(target);
  }

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      commit();
    } else if (event.key === "Escape") {
      event.preventDefault();
      renderBreadcrumbs(state.filePath);
    }
  });
  input.addEventListener("blur", commit);
}

function renderBreadcrumbs(path) {
  breadcrumbsEl.innerHTML = "";

  const crumbsWrapper = document.createElement("div");
  crumbsWrapper.className = "breadcrumb-crumbs";

  const parts = path === "." ? [] : path.split("/");
  const root = document.createElement("button");
  root.className = "crumb";
  root.type = "button";
  root.textContent = "root";
  root.addEventListener("click", () => loadFiles("."));
  crumbsWrapper.appendChild(root);

  let current = "";
  for (const part of parts) {
    current = current ? `${current}/${part}` : part;
    const targetPath = current;
    const crumb = document.createElement("button");
    crumb.className = "crumb";
    crumb.type = "button";
    crumb.textContent = `/ ${part}`;
    crumb.addEventListener("click", () => loadFiles(targetPath));
    crumbsWrapper.appendChild(crumb);
  }

  breadcrumbsEl.appendChild(crumbsWrapper);

  const editBtn = document.createElement("button");
  editBtn.className = "crumb breadcrumb-edit-btn";
  editBtn.type = "button";
  editBtn.title = "Edit path";
  editBtn.setAttribute("aria-label", "Edit path");
  editBtn.innerHTML = `<span class="app-icon" aria-hidden="true">✎</span>`;
  editBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    enterBreadcrumbEditMode();
  });
  breadcrumbsEl.appendChild(editBtn);
}

function renderFiles(data) {
  fileListEl.innerHTML = "";
  if (data.parent) {
    fileListEl.appendChild(fileRow({ name: "..", path: data.parent, is_dir: true, size: 0 }, true));
  }
  for (const item of data.items || []) {
    fileListEl.appendChild(fileRow(item, false));
  }
}

function fileRow(item, isParent) {
  const row = document.createElement("div");
  row.className = `file-row${item.is_dir ? " file-clickable" : ""}`;
  row.innerHTML = `${icon(item.is_dir ? "folder" : "file")}<span class="file-name"></span><span class="file-actions"></span>`;
  row.querySelector(".file-name").textContent = item.name;

  if (item.is_dir) {
    row.setAttribute("role", "button");
    row.tabIndex = 0;
    row.addEventListener("click", () => loadFiles(item.path));
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        loadFiles(item.path);
      }
    });
  }

  const actions = row.querySelector(".file-actions");
  if (!item.is_dir && !isParent) {
    if (item.can_open) {
      const openButton = document.createElement("button");
      openButton.className = "file-action-button";
      openButton.type = "button";
      openButton.title = "Open file";
      openButton.setAttribute("aria-label", `Open ${item.name}`);
      openButton.innerHTML = `${icon("open")}<span>Open</span>`;
      openButton.addEventListener("click", () => openFileTab(item));
      actions.appendChild(openButton);
    }

    const downloadLink = document.createElement("a");
    downloadLink.className = "file-action-button compact";
    downloadLink.href = `/api/download?path=${encodeURIComponent(item.path)}`;
    downloadLink.title = "Download file";
    downloadLink.setAttribute("aria-label", `Download ${item.name}`);
    downloadLink.innerHTML = icon("download");
    actions.appendChild(downloadLink);
  } else if (!item.is_dir) {
    actions.textContent = formatSize(item.size);
  }
  refreshIcons();
  return row;
}

function applyAccent() {
  const color = state.theme === "light" ? settings.accentLight : settings.accentDark;
  document.documentElement.style.setProperty("--accent", color);
}

function applyTerminalSettings() {
  for (const session of state.terminals.values()) {
    const term = session.term;
    if (term.options) {
      term.options.fontSize = settings.fontSize;
      term.options.fontFamily = settings.fontFamily;
      term.options.cursorStyle = settings.cursorStyle;
      term.options.cursorBlink = settings.cursorBlink;
      term.options.theme = terminalTheme();
    }
    session.fit.fit();
  }
}

function applyFilePane() {
  const pane = document.querySelector(".file-pane");
  const shell = document.querySelector(".app-shell");
  if (settings.showFilePane) {
    pane.style.display = "";
    shell.style.gridTemplateColumns = "";
  } else {
    pane.style.display = "none";
    shell.style.gridTemplateColumns = "1fr";
  }
  const active = state.terminals.get(state.activeId);
  if (active) active.fit.fit();
}

function applyAllSettings() {
  applyAccent();
  applyTerminalSettings();
  applyFilePane();
}

function initSettingsPanel() {
  const panel = document.getElementById("settingsPanel");
  const overlay = document.getElementById("settingsOverlay");
  const toggleBtn = document.getElementById("settingsToggle");
  const closeBtn = document.getElementById("settingsClose");

  function openSettings() {
    panel.classList.add("open");
    overlay.classList.add("open");
  }
  function closeSettings() {
    panel.classList.remove("open");
    overlay.classList.remove("open");
  }

  toggleBtn.addEventListener("click", openSettings);
  closeBtn.addEventListener("click", closeSettings);
  overlay.addEventListener("click", closeSettings);

  const swatches = document.querySelectorAll("#accentSwatches .swatch");
  function markActiveSwatch() {
    swatches.forEach((s) => {
      s.classList.toggle("active", s.dataset.color === settings.accentDark);
    });
  }
  markActiveSwatch();
  swatches.forEach((swatch) => {
    swatch.addEventListener("click", () => {
      settings.accentDark = swatch.dataset.color;
      settings.accentLight = swatch.dataset.colorLight;
      saveSettings(settings);
      applyAccent();
      applyTerminalSettings();
      markActiveSwatch();
    });
  });

  const fontSizeRange = document.getElementById("fontSizeRange");
  const fontSizeValue = document.getElementById("fontSizeValue");
  fontSizeRange.value = settings.fontSize;
  fontSizeValue.textContent = `${settings.fontSize}px`;
  fontSizeRange.addEventListener("input", () => {
    settings.fontSize = Number(fontSizeRange.value);
    fontSizeValue.textContent = `${settings.fontSize}px`;
    saveSettings(settings);
    applyTerminalSettings();
  });

  const fontFamilySelect = document.getElementById("fontFamilySelect");
  fontFamilySelect.value = settings.fontFamily;
  fontFamilySelect.addEventListener("change", () => {
    settings.fontFamily = fontFamilySelect.value;
    saveSettings(settings);
    applyTerminalSettings();
  });

  const cursorStyleSelect = document.getElementById("cursorStyleSelect");
  cursorStyleSelect.value = settings.cursorStyle;
  cursorStyleSelect.addEventListener("change", () => {
    settings.cursorStyle = cursorStyleSelect.value;
    saveSettings(settings);
    applyTerminalSettings();
  });

  const cursorBlinkToggle = document.getElementById("cursorBlinkToggle");
  cursorBlinkToggle.checked = settings.cursorBlink;
  cursorBlinkToggle.addEventListener("change", () => {
    settings.cursorBlink = cursorBlinkToggle.checked;
    saveSettings(settings);
    applyTerminalSettings();
  });

  const filePaneToggle = document.getElementById("filePaneToggle");
  filePaneToggle.checked = settings.showFilePane;
  filePaneToggle.addEventListener("change", () => {
    settings.showFilePane = filePaneToggle.checked;
    saveSettings(settings);
    applyFilePane();
  });
}

document.getElementById("newTerminal").addEventListener("click", createTerminal);
document.getElementById("emptyNewTerminal").addEventListener("click", createTerminal);
document.getElementById("refreshFiles").addEventListener("click", () => loadFiles());
document.getElementById("themeToggle").addEventListener("click", () => {
  state.theme = state.theme === "dark" ? "light" : "dark";
  localStorage.setItem("theme", state.theme);
  document.documentElement.dataset.theme = state.theme;
  applyAccent();
  for (const session of state.terminals.values()) {
    session.term.options.theme = terminalTheme();
    if (session.surface.querySelector(".terminal-fallback")) {
      session.surface.querySelector(".terminal-fallback").dataset.theme = state.theme;
    }
  }
});

window.addEventListener("resize", () => {
  const session = state.terminals.get(state.activeId);
  if (session) session.fit.fit();
});

async function restoreTerminals() {
  const saved = readSavedTerminals();
  if (!saved || saved.terminals.length === 0) {
    updateEmptyState();
    renderTabs();
    return;
  }
  for (const savedTerminal of saved.terminals) {
    await createTerminal({ id: savedTerminal.id, title: savedTerminal.title || `Terminal ${state.nextId++}` });
  }
  if (saved.activeId && state.terminals.has(saved.activeId)) {
    setActiveTerminal(saved.activeId);
  }
}

applyAccent();
applyFilePane();
initSettingsPanel();
loadFiles();
restoreTerminals();
refreshIcons();
