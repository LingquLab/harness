import io
import json
import unittest
import urllib.error
from unittest.mock import Mock

from cross_zone.hapi import HapiClient, HapiError


def response(value):
    return io.BytesIO(json.dumps(value).encode())


class HubFallbackTests(unittest.TestCase):
    def setUp(self):
        self.client = HapiClient("https://hapi.kurox.cn/", "test-key")
        self.client.opener = Mock()

    def urls(self):
        return [call.args[0].full_url for call in self.client.opener.open.call_args_list]

    def test_prefers_cf_for_auth_and_rest(self):
        self.client.opener.open.side_effect = [response({"token": "jwt"}), response({"sessions": []})]
        self.assertEqual(self.client.sessions(), [])
        self.assertEqual(self.urls(), ["https://hapi-cf.kurox.cn/api/auth",
                                       "https://hapi-cf.kurox.cn/api/sessions"])

    def test_auth_failure_falls_back_and_stays_on_original(self):
        for error in (urllib.error.URLError("unreachable"),
                      urllib.error.HTTPError("https://hapi-cf.kurox.cn/api/auth", 503, "unavailable", {}, None)):
            with self.subTest(error=type(error).__name__):
                self.setUp()
                self.client.opener.open.side_effect = [error, response({"token": "jwt"}),
                                                       response({"sessions": []})]
                with self.assertLogs("cross_zone.hapi", level="WARNING"):
                    self.assertEqual(self.client.sessions(), [])
                self.assertEqual(self.urls(), ["https://hapi-cf.kurox.cn/api/auth",
                                               "https://hapi.kurox.cn/api/auth",
                                               "https://hapi.kurox.cn/api/sessions"])

    def test_send_fallback_preserves_auth_body_and_deduplication_id(self):
        self.client.opener.open.side_effect = [response({"token": "jwt"}),
                                               urllib.error.URLError("unreachable"), response({"ok": True})]
        with self.assertLogs("cross_zone.hapi", level="WARNING"):
            self.client.send("blue", "result", "stable-id")
        calls = self.client.opener.open.call_args_list
        first, fallback = calls[1].args[0], calls[2].args[0]
        self.assertEqual(first.full_url, "https://hapi-cf.kurox.cn/api/sessions/blue/messages")
        self.assertEqual(fallback.full_url, "https://hapi.kurox.cn/api/sessions/blue/messages")
        self.assertEqual(first.data, fallback.data)
        self.assertEqual(json.loads(fallback.data)["localId"], "stable-id")
        self.assertEqual(fallback.get_header("Authorization"), "Bearer jwt")

    def test_event_stream_connection_uses_same_fallback(self):
        stream = io.BytesIO(b"data: {}\n\n")
        self.client.opener.open.side_effect = [urllib.error.URLError("unreachable"), stream]
        with self.assertLogs("cross_zone.hapi", level="WARNING"):
            self.assertIs(self.client._open("events?sessionId=blue", timeout=30), stream)
        self.assertEqual(self.urls(), ["https://hapi-cf.kurox.cn/api/events?sessionId=blue",
                                       "https://hapi.kurox.cn/api/events?sessionId=blue"])
        self.assertEqual(self.client.opener.open.call_args.kwargs["timeout"], 30)

    def test_both_fail_preserves_final_error(self):
        self.client.opener.open.side_effect = [urllib.error.URLError("unreachable"),
            urllib.error.HTTPError("https://hapi.kurox.cn/api/auth", 403, "forbidden", {}, None)]
        with self.assertLogs("cross_zone.hapi", level="WARNING"), self.assertRaises(HapiError) as error:
            self.client.authenticate()
        self.assertEqual(error.exception.status, 403)
        self.assertEqual(len(self.urls()), 2)

    def test_custom_hubs_and_path_prefixes_are_unchanged(self):
        for base in ("https://example.test/prefix/", "https://hapi.kurox.cn/prefix/",
                     "http://hapi.kurox.cn/", "https://hapi-cf.kurox.cn/"):
            with self.subTest(base=base):
                client = HapiClient(base, "test-key")
                self.assertEqual(client.base, base + "api/")
                self.assertIsNone(client.fallback_base)
