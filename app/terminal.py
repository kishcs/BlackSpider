from __future__ import annotations

import asyncio
import fcntl
import os
import pty
import signal
import struct
import subprocess
import termios
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TerminalSubscriber:
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue[bytes | None]


class TerminalSession:
    def __init__(self, cwd: Path, session_id: str | None = None) -> None:
        self.id = session_id or uuid.uuid4().hex
        self.cwd = cwd
        self.output_history = bytearray()
        self.master_fd: int | None = None
        self.process: subprocess.Popen[bytes] | None = None
        self.last_detached_at: float | None = None
        self._closed = threading.Event()
        self._lock = threading.Lock()
        self._reader: threading.Thread | None = None
        self._subscribers: set[TerminalSubscriber] = set()

    @property
    def is_running(self) -> bool:
        return not self._closed.is_set() and self.process is not None and self.process.poll() is None

    def start(self) -> None:
        master_fd, slave_fd = pty.openpty()
        self.master_fd = master_fd
        shell = os.environ.get("TERMINAL_SHELL") or "/bin/bash"
        custom_ps1 = os.environ.get("TERMINAL_PS1", r"\u@\h:\W \$ ")

        env = os.environ.copy()
        env.update({
            "TERM": "xterm-256color",
            "COLORTERM": "truecolor",
        })

        # Build a custom rcfile that sources the user's bashrc first,
        # then enforces our PS1 so it isn't overridden.
        shell_args = [shell]
        if shell.endswith("bash"):
            rcfile = os.path.join(os.path.dirname(__file__), ".bashrc_blackspider")
            with open(rcfile, "w") as f:
                f.write('[ -f ~/.bashrc ] && source ~/.bashrc\n')
                f.write(f'export PS1=\'{custom_ps1}\'\n')
            shell_args = [shell, "--rcfile", rcfile]

        self.process = subprocess.Popen(
            shell_args,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=self.cwd,
            env=env,
            preexec_fn=os.setsid,
            close_fds=True,
        )
        os.close(slave_fd)
        self.resize(100, 30)
        self._reader = threading.Thread(target=self._read_forever, daemon=True)
        self._reader.start()

    def subscribe(self) -> TerminalSubscriber:
        subscriber = TerminalSubscriber(asyncio.get_running_loop(), asyncio.Queue())
        with self._lock:
            self.last_detached_at = None
            self._subscribers.add(subscriber)
            history = bytes(self.output_history)
        if history:
            subscriber.queue.put_nowait(history)
        return subscriber

    def unsubscribe(self, subscriber: TerminalSubscriber) -> None:
        with self._lock:
            self._subscribers.discard(subscriber)
            if not self._subscribers:
                self.last_detached_at = time.time()

    def write(self, data: str) -> None:
        if self.master_fd is None or self._closed.is_set():
            return
        os.write(self.master_fd, data.encode())

    def resize(self, cols: int, rows: int) -> None:
        if self.master_fd is None:
            return
        size = struct.pack("HHHH", max(rows, 1), max(cols, 1), 0, 0)
        fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, size)
        if self.process and self.process.poll() is None:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGWINCH)
            except ProcessLookupError:
                pass

    def close(self) -> None:
        self._closed.set()
        with self._lock:
            subscribers = list(self._subscribers)
            self._subscribers.clear()
        for subscriber in subscribers:
            subscriber.loop.call_soon_threadsafe(subscriber.queue.put_nowait, None)

        if self.process and self.process.poll() is None:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGHUP)
            except ProcessLookupError:
                pass
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None

    def _publish(self, data: bytes | None) -> None:
        with self._lock:
            if data:
                self.output_history.extend(data)
                if len(self.output_history) > 500_000:
                    del self.output_history[:-500_000]
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            subscriber.loop.call_soon_threadsafe(subscriber.queue.put_nowait, data)

    def _read_forever(self) -> None:
        assert self.master_fd is not None
        while not self._closed.is_set():
            try:
                data = os.read(self.master_fd, 4096)
            except OSError:
                break
            if not data:
                break
            self._publish(data)
        self._closed.set()
        self._publish(None)
