import asyncio
import json
import threading
import subprocess
import os
import secrets
import socket
import tempfile
import time

if os.name == "nt":
    import _winapi
    from multiprocessing.connection import PipeConnection

from src.config import MPV_PATH
from src.log import logger

class MpvError(RuntimeError):
    pass


class MPVController(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.ipc_path = self.make_mpv_ipc_address()
        self.mpv: subprocess.Popen | None = None
        self._request_id = 0
        self._request_lock = threading.Lock()
        self._mpv_lock = threading.Lock()
        self.running = threading.Event()
        self._stop_requested = threading.Event()

    def start(self) -> None:
        if MPV_PATH is None:
            raise MpvError("mpv executable not found in MPV_PATH or system PATH")
        self.mpv_path = MPV_PATH
        self._stop_requested.clear()
        super().start()
    
    def make_mpv_ipc_address(self) -> str:
        suffix = secrets.token_hex(8)

        if os.name == "nt":
            return rf"\\.\pipe\mpv_socket_{suffix}"

        return os.path.join(tempfile.gettempdir(), f"mpv_socket_{suffix}.sock")

    def _cleanup_ipc_path(self) -> None:
        if os.name == "nt":
            return

        try:
            if os.path.exists(self.ipc_path):
                os.unlink(self.ipc_path)
        except OSError:
            pass

    def run(self):
        consecutive_failures = 0

        while not self._stop_requested.is_set():
            self._cleanup_ipc_path()
            proc = subprocess.Popen(
                [
                    self.mpv_path,
                    f"--input-ipc-server={self.ipc_path}",
                    "--fullscreen",
                    "--no-terminal",
                    "--hwdec=yes",
                    "--idle=yes",
                    "--ontop",
                    "--on-all-workspaces",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            with self._mpv_lock:
                self.mpv = proc

            if self._stop_requested.is_set():
                with self._mpv_lock:
                    if self.mpv is proc:
                        self.mpv = None
                proc.terminate()
                try:
                    proc.wait()
                finally:
                    self._cleanup_ipc_path()
                break

            start = time.monotonic()
            self.running.set()

            try:
                proc.wait()
            finally:
                self.running.clear()
                self._cleanup_ipc_path()

            if self._stop_requested.is_set():
                with self._mpv_lock:
                    if self.mpv is proc:
                        self.mpv = None
                break

            with self._mpv_lock:
                if self.mpv is proc:
                    self.mpv = None

            runtime = time.monotonic() - start
            if runtime >= 5.0:
                consecutive_failures = 0
            else:
                consecutive_failures += 1

            if consecutive_failures > 5:
                logger.error(
                    "mpv crashed %d times consecutively, giving up",
                    consecutive_failures,
                )
                break

            backoff = min(1.0 * (2 ** (consecutive_failures - 1)), 30.0)
            self._stop_requested.wait(backoff)
            if self._stop_requested.is_set():
                break

            logger.warning(
                "mpv exited, restarting (attempt %d/5, backoff %.0fs)",
                min(consecutive_failures, 5),
                backoff,
            )

    async def load(self, url: str) -> bool:
        return await asyncio.to_thread(self._load_sync, url)

    async def stop_playback(self) -> bool:
        if not self.running.is_set():
            return True
        return await asyncio.to_thread(self._stop_playback_sync)

    def _stop_playback_sync(self, timeout: float = 5.0) -> bool:
        deadline = time.monotonic() + timeout
        request_id = self._next_request_id()
        read_buffer = bytearray()

        conn = self._connect_ipc_stream(deadline)
        if conn is None:
            return False

        try:
            payload = {
                "command": ["stop"],
                "request_id": request_id,
            }
            self._send_ipc_message(conn, payload)

            while time.monotonic() < deadline:
                msg = self._read_ipc_message(conn, read_buffer)
                if msg is None:
                    return False

                if msg.get("request_id") == request_id:
                    return msg.get("error") == "success"

            return False
        except OSError:
            return False
        finally:
            conn.close()

    def _load_sync(self, url: str, timeout: float = 10.0) -> bool:
        if not self.running.is_set():
            return False

        deadline = time.monotonic() + timeout
        request_id = self._next_request_id()
        read_buffer = bytearray()

        conn = self._connect_ipc_stream(deadline)
        if conn is None:
            return False

        try:
            payload = {
                "command": ["loadfile", url, "replace"],
                "request_id": request_id,
            }
            self._send_ipc_message(conn, payload)

            while time.monotonic() < deadline:
                msg = self._read_ipc_message(conn, read_buffer)
                if msg is None:
                    return False

                if msg.get("request_id") == request_id:
                    if msg.get("error") != "success":
                        return False
                    continue

                if msg.get("event") == "file-loaded":
                    return True

                if msg.get("event") == "end-file" and msg.get("reason") == "error":
                    return False

            return False
        except OSError:
            return False
        finally:
            conn.close()

    def _next_request_id(self) -> int:
        with self._request_lock:
            self._request_id += 1
            return self._request_id

    def _connect_ipc_stream(self, deadline: float):
        if not self.running.is_set() or self._stop_requested.is_set():
            return None

        while time.monotonic() < deadline:
            if self._stop_requested.is_set():
                return None

            sock = None
            try:
                if os.name == "nt":
                    handler = _winapi.CreateFile(
                        self.ipc_path,
                        _winapi.GENERIC_READ | _winapi.GENERIC_WRITE,
                        0,
                        _winapi.NULL,
                        _winapi.OPEN_EXISTING,
                        _winapi.FILE_FLAG_OVERLAPPED,
                        _winapi.NULL,
                    )
                    return PipeConnection(handler)

                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(self.ipc_path)
                return sock
            except (FileNotFoundError, ConnectionRefusedError, OSError):
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
                time.sleep(0.05)

        return None

    def _send_ipc_message(self, conn, payload: dict) -> None:
        msg = (json.dumps(payload) + "\n").encode("utf-8")

        if os.name == "nt":
            conn.send_bytes(msg)
        else:
            conn.sendall(msg)

    def _read_ipc_message(self, conn, buffer: bytearray) -> dict | None:
        while True:
            newline = buffer.find(b"\n")
            if newline != -1:
                line = bytes(buffer[:newline])
                del buffer[: newline + 1]
                try:
                    return json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    return None

            if os.name == "nt":
                chunk = conn.recv_bytes(1048576)
            else:
                chunk = conn.recv(1048576)

            if chunk == b"":
                return None

            buffer.extend(chunk)
    
    def stop(self):
        self._stop_requested.set()
        with self._mpv_lock:
            proc = self.mpv
            if proc is None:
                return
            self.mpv = None
        if proc.poll() is None:
            proc.terminate()
            proc.wait()
        self._cleanup_ipc_path()
