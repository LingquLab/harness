"""Prefix-preserving HTTP client. Credentials are never placed in URLs or logs."""

import json
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import USER_AGENT

LOG = logging.getLogger(__name__)


class HapiError(RuntimeError):
    def __init__(self, status=None):
        self.status = status
        super().__init__(f"HAPI HTTP {status}" if status else "HAPI connection/protocol failure")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HapiClient:
    def __init__(self, base_url, access_key, timeout=20):
        self.interactive_base = base_url.rstrip("/") + "/api/"
        self.base = self.interactive_base
        endpoint = urllib.parse.urlsplit(self.interactive_base)
        if endpoint.hostname in {"hapi.kurox.cn", "hapi-cf.kurox.cn"}:
            host = "hapi-cf.kurox.cn" + (f":{endpoint.port}" if endpoint.port is not None else "")
            self.discovery_base = endpoint._replace(netloc=host).geturl()
        else:
            self.discovery_base = self.interactive_base
        self.access_key = access_key
        self.timeout = timeout
        self.token = None
        self.expires = 0
        self.auth_lock = threading.Lock()
        self.opener = urllib.request.build_opener(NoRedirect())
        LOG.info("Hub endpoint: mode=interactive host=%s", urllib.parse.urlsplit(self.base).hostname)

    def set_interactive(self, active):
        """Select interaction routing; discovery requests use their own endpoint."""
        previous = self.base
        self.base = ("https://hapi-cf.kurox.cn/api/"
                     if not active and self.interactive_base == "https://hapi.kurox.cn/api/"
                     else self.interactive_base)
        if self.base != previous:
            LOG.info("Hub endpoint: mode=%s host=%s", "interactive" if active else "discovery-idle",
                     urllib.parse.urlsplit(self.base).hostname)

    def _open(self, path, method="GET", body=None, headers=None, timeout=None, *, discovery=False):
        request = urllib.request.Request(
            (self.discovery_base if discovery else self.base) + path,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            method=method,
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT, **(headers or {})},
        )
        started = time.monotonic()
        route_path = path.split("?")[0]
        route = "messages" if route_path.endswith("/messages") else route_path
        if route not in {"auth", "sessions", "events", "messages"}:
            route = "other"
        match = re.fullmatch(r"sessions/([0-9a-fA-F-]{36})/messages", route_path)
        session = match.group(1) if match else "-"
        query = urllib.parse.parse_qs(path.partition("?")[2])
        direction = "after" if "afterSeq" in query else "before" if "beforeSeq" in query else "latest"
        host = urllib.parse.urlsplit(request.full_url).hostname
        trace = id(request)
        LOG.debug("HTTP begin trace=%s method=%s host=%s route=%s session=%s direction=%s timeout=%s thread=%s purpose=%s",
                  trace, method, host, route, session, direction,
                  timeout or self.timeout, threading.current_thread().name, "discovery" if discovery else "interaction")
        try:
            response = self.opener.open(request, timeout=timeout or self.timeout)
            LOG.debug("HTTP headers trace=%s response=%s elapsed_ms=%.1f", trace, id(response),
                      (time.monotonic() - started) * 1000)
            return response
        except urllib.error.HTTPError as exc:
            LOG.warning("HTTP failed trace=%s host=%s method=%s route=%s status=%s elapsed_ms=%.1f",
                        trace, host, method, route, exc.code,
                      (time.monotonic() - started) * 1000)
            status = exc.code
            exc.close()
            raise HapiError(status) from None
        except (OSError, urllib.error.URLError) as exc:
            LOG.warning("HTTP failed trace=%s host=%s method=%s route=%s error=%s elapsed_ms=%.1f",
                        trace, host, method, route, type(exc).__name__,
                      (time.monotonic() - started) * 1000)
            raise HapiError() from None

    @staticmethod
    def _json(response):
        started = time.monotonic()
        LOG.debug("HTTP body begin response=%s thread=%s", id(response), threading.current_thread().name)
        try:
            with response:
                body = response.read(16 * 1024 * 1024 + 1)
        finally:
            LOG.debug("HTTP body end response=%s elapsed_ms=%.1f", id(response),
                      (time.monotonic() - started) * 1000)
        if len(body) > 16 * 1024 * 1024:
            raise HapiError()
        try:
            value = json.loads(body)
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (ValueError, UnicodeError):
            raise HapiError() from None

    def authenticate(self, force=False, *, discovery=False):
        with self.auth_lock:
            if self.token and time.monotonic() < self.expires and not force:
                return self.token
            result = self._json(self._open("auth", "POST", {"accessToken": self.access_key}, discovery=discovery))
            if not isinstance(result.get("token"), str) or not result["token"]:
                raise HapiError()
            self.token = result["token"]
            self.expires = time.monotonic() + 3 * 3600
            return self.token

    def request(self, path, method="GET", body=None, *, discovery=False):
        for attempt in range(2):
            token = self.authenticate(force=attempt == 1, discovery=discovery)
            try:
                return self._json(self._open(path, method, body, {"Authorization": "Bearer " + token}, discovery=discovery))
            except HapiError as exc:
                if exc.status != 401 or attempt:
                    raise
        raise HapiError()

    def sessions(self, *, discovery=False):
        return self.request("sessions?active=true" if discovery else "sessions", discovery=discovery)["sessions"]

    def messages(self, session, *, discovery=False, **query):
        path = "sessions/" + urllib.parse.quote(session, safe="") + "/messages"
        return self.request(path + "?" + urllib.parse.urlencode(query), discovery=discovery)

    def send(self, session, text, event_id):
        path = "sessions/" + urllib.parse.quote(session, safe="") + "/messages"
        return self.request(path, "POST", {"text": text, "localId": event_id, "deliveryMode": "queue"})

    def listen(self, session, wake, stop):
        """SSE is an accelerator only. Durable REST cursors remain authoritative."""
        last_id = None
        delay = 1
        while not stop.is_set():
            connected_at = None
            try:
                token = self.authenticate()
                headers = {"Authorization": "Bearer " + token, "Accept": "text/event-stream"}
                if last_id:
                    headers["Last-Event-ID"] = last_id
                path = "events?" + urllib.parse.urlencode({"sessionId": session})
                with self._open(path, headers=headers, timeout=30) as response:
                    if "text/event-stream" not in response.headers.get("Content-Type", ""):
                        raise HapiError()
                    wake.set()  # REST catch-up on every reconnection, including replay reset.
                    connected_at = time.monotonic()
                    while not stop.is_set():
                        line = response.readline(65537)
                        if not line or len(line) > 65536:
                            break
                        if line.startswith(b"id:"):
                            last_id = line[3:].strip().decode("utf-8")
                        elif line.startswith(b"data:"):
                            wake.set()
            except HapiError as exc:
                if exc.status == 401:
                    self.expires = 0
            except (OSError, ValueError):
                pass
            # Valid headers alone do not prove a healthy stream. Immediate EOFs
            # must back off too, rather than reconnecting once per second forever.
            if connected_at is not None and time.monotonic() - connected_at >= 30:
                delay = 1
            stop.wait(delay)
            delay = min(delay * 2, 30)
