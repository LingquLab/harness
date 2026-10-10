"""Prefix-preserving HTTP client. Credentials are never placed in URLs or logs."""

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


class HapiError(RuntimeError):
    def __init__(self, status=None):
        self.status = status
        super().__init__(f"HAPI HTTP {status}" if status else "HAPI connection/protocol failure")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HapiClient:
    def __init__(self, base_url, access_key, timeout=20):
        self.base = base_url.rstrip("/") + "/api/"
        self.access_key = access_key
        self.timeout = timeout
        self.token = None
        self.expires = 0
        self.auth_lock = threading.Lock()
        self.opener = urllib.request.build_opener(NoRedirect())

    def _open(self, path, method="GET", body=None, headers=None, timeout=None):
        request = urllib.request.Request(
            self.base + path,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            method=method,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        try:
            return self.opener.open(request, timeout=timeout or self.timeout)
        except urllib.error.HTTPError as exc:
            exc.close()
            raise HapiError(exc.code) from None
        except (OSError, urllib.error.URLError):
            raise HapiError() from None

    @staticmethod
    def _json(response):
        with response:
            body = response.read(16 * 1024 * 1024 + 1)
        if len(body) > 16 * 1024 * 1024:
            raise HapiError()
        try:
            value = json.loads(body)
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (ValueError, UnicodeError):
            raise HapiError() from None

    def authenticate(self, force=False):
        with self.auth_lock:
            if self.token and time.monotonic() < self.expires and not force:
                return self.token
            result = self._json(self._open("auth", "POST", {"accessToken": self.access_key}))
            if not isinstance(result.get("token"), str) or not result["token"]:
                raise HapiError()
            self.token = result["token"]
            self.expires = time.monotonic() + 3 * 3600
            return self.token

    def request(self, path, method="GET", body=None):
        for attempt in range(2):
            token = self.authenticate(force=attempt == 1)
            try:
                return self._json(self._open(path, method, body, {"Authorization": "Bearer " + token}))
            except HapiError as exc:
                if exc.status != 401 or attempt:
                    raise
        raise HapiError()

    def sessions(self):
        return self.request("sessions")["sessions"]

    def messages(self, session, **query):
        path = "sessions/" + urllib.parse.quote(session, safe="") + "/messages"
        return self.request(path + "?" + urllib.parse.urlencode(query))

    def send(self, session, text, event_id):
        path = "sessions/" + urllib.parse.quote(session, safe="") + "/messages"
        return self.request(path, "POST", {"text": text, "localId": event_id, "deliveryMode": "queue"})

    def listen(self, session, wake, stop):
        """SSE is an accelerator only. Durable REST cursors remain authoritative."""
        last_id = None
        delay = 1
        while not stop.is_set():
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
                    delay = 1
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
            stop.wait(delay)
            delay = min(delay * 2, 30)
