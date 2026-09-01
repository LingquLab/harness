#!/usr/bin/env python3
"""Serve a compact, read-only dashboard for Ascend NPU occupancy."""

from __future__ import annotations

import argparse
import json
import pathlib
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import check_npu_status


DEFAULT_INTERVAL = 10.0
DEFAULT_PORT = 0
DASHBOARD_PATH = pathlib.Path(__file__).resolve().parent.parent / "assets" / "dashboard.html"


class StatusStore:
    def __init__(self, targets: list[check_npu_status.Target], max_workers: int, interval: float):
        self.targets = targets
        self.max_workers = max_workers
        self.interval = interval
        self._started_at = time.time()
        self._last_busy_at: dict[str, float] = {}
        self._lock = threading.Lock()
        self._result: dict[str, Any] = {
            "schema_version": check_npu_status.SCHEMA_VERSION,
            "status": "checking",
            "safe_to_use": False,
            "summary": {
                "environments": len(targets),
                "devices": sum(len(target.devices) for target in targets),
                "idle": 0,
                "busy": 0,
                "unknown": 0,
            },
            "environments": [],
        }
        self._stop = threading.Event()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._result

    def run(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            result = check_npu_status.check_targets(self.targets, self.max_workers)
            observed_at = time.time()
            for environment in result["environments"]:
                name = environment["name"]
                if environment["status"] == "busy":
                    self._last_busy_at[name] = observed_at
                last_busy_at = self._last_busy_at.get(name)
                if environment["status"] == "idle":
                    environment["idle_since_epoch_seconds"] = last_busy_at or self._started_at
                    environment["idle_duration_lower_bound"] = last_busy_at is None
                else:
                    environment["idle_since_epoch_seconds"] = None
                    environment["idle_duration_lower_bound"] = False
            result["refresh_interval_seconds"] = self.interval
            with self._lock:
                self._result = result
            remaining = max(0.0, self.interval - (time.monotonic() - started))
            self._stop.wait(remaining)

    def stop(self) -> None:
        self._stop.set()


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], store: StatusStore, html: bytes):
        super().__init__(address, DashboardHandler)
        self.store = store
        self.html = html


class DashboardHandler(BaseHTTPRequestHandler):
    server: DashboardServer

    def do_GET(self) -> None:
        path = self.path.partition("?")[0]
        if path == "/":
            self._send(HTTPStatus.OK, "text/html; charset=utf-8", self.server.html)
        elif path == "/api/status":
            payload = json.dumps(self.server.store.snapshot(), separators=(",", ":")).encode()
            self._send(HTTPStatus.OK, "application/json; charset=utf-8", payload)
        elif path == "/favicon.ico":
            self._send(HTTPStatus.NO_CONTENT, "image/x-icon", b"")
        else:
            self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", b"Not found")

    def _send(self, status: HTTPStatus, content_type: str, payload: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


def _bounded_float(value: str) -> float:
    try:
        result = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("interval must be a number") from error
    if not 2 <= result <= 300:
        raise argparse.ArgumentTypeError("interval must be between 2 and 300 seconds")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve a compact Ascend NPU occupancy dashboard.")
    parser.add_argument("env_list_json", help="v1 env_list.json file")
    parser.add_argument("--interval", type=_bounded_float, default=DEFAULT_INTERVAL, metavar="SECONDS")
    parser.add_argument(
        "--max-workers",
        type=lambda value: check_npu_status._cli_integer(value, "max workers", 1, 64),
        default=check_npu_status.DEFAULT_MAX_WORKERS,
        metavar="COUNT",
    )
    parser.add_argument("--port", type=lambda value: check_npu_status._cli_integer(value, "port", 0, 65535), default=DEFAULT_PORT)
    return parser


def main(arguments: list[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    try:
        targets = check_npu_status.load_config(args.env_list_json)
        html = DASHBOARD_PATH.read_bytes()
    except (check_npu_status.ConfigError, OSError) as error:
        print(json.dumps({"status": "invalid_input", "error": str(error)}), flush=True)
        return 2

    store = StatusStore(targets, args.max_workers, args.interval)
    server = DashboardServer(("127.0.0.1", args.port), store, html)
    worker = threading.Thread(target=store.run, name="npu-status-probe", daemon=True)
    worker.start()
    host, port = server.server_address
    print(json.dumps({"status": "serving", "url": f"http://{host}:{port}/"}), flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        store.stop()
        server.server_close()
        worker.join(timeout=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
