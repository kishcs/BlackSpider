from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from .terminal import TerminalSession


class TerminalManager:
    def __init__(self) -> None:
        self.sessions: dict[str, TerminalSession] = {}
        self.ttl_seconds = int(os.environ.get("TERMINAL_IDLE_TTL_SECONDS", "1800"))
        self._lock = threading.Lock()

    def create(self, cwd: Path) -> TerminalSession:
        session = TerminalSession(cwd=cwd)
        session.start()
        with self._lock:
            self.sessions[session.id] = session
        return session

    def get(self, session_id: str) -> TerminalSession | None:
        with self._lock:
            session = self.sessions.get(session_id)
        if session and session.is_running:
            return session
        if session:
            self.close(session_id)
        return None

    def close(self, session_id: str) -> bool:
        with self._lock:
            session = self.sessions.pop(session_id, None)
        if not session:
            return False
        session.close()
        return True

    def cleanup_idle(self) -> None:
        now = time.time()
        expired_ids = []
        with self._lock:
            for session_id, session in self.sessions.items():
                if not session.is_running:
                    expired_ids.append(session_id)
                elif session.last_detached_at and now - session.last_detached_at > self.ttl_seconds:
                    expired_ids.append(session_id)
        for session_id in expired_ids:
            self.close(session_id)
