import io
import json
import unittest
import urllib.error
from unittest.mock import Mock

from cross_zone.hapi import HapiClient, HapiError


def response(value):
    return io.BytesIO(json.dumps(value).encode())


class HubEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = HapiClient("https://hapi.kurox.cn/", "test-key")
        self.client.opener = Mock()

    def urls(self):
        return [call.args[0].full_url for call in self.client.opener.open.call_args_list]

    def test_auth_rest_and_send_use_configured_hub(self):
        self.client.opener.open.side_effect = [response({"token": "jwt"}),
                                               response({"sessions": []}), response({"ok": True})]
        self.assertEqual(self.client.sessions(), [])
        self.client.send("blue", "result", "stable-id")
        self.assertEqual(self.urls(), ["https://hapi.kurox.cn/api/auth",
                                       "https://hapi.kurox.cn/api/sessions",
                                       "https://hapi.kurox.cn/api/sessions/blue/messages"])
        request = self.client.opener.open.call_args.args[0]
        self.assertEqual(json.loads(request.data),
                         {"text": "result", "localId": "stable-id", "deliveryMode": "queue"})
        self.assertEqual(request.get_header("Authorization"), "Bearer jwt")

    def test_event_stream_uses_configured_hub(self):
        stream = io.BytesIO(b"data: {}\n\n")
        self.client.opener.open.return_value = stream
        self.assertIs(self.client._open("events?sessionId=blue", timeout=30), stream)
        self.assertEqual(self.urls(), ["https://hapi.kurox.cn/api/events?sessionId=blue"])
        self.assertEqual(self.client.opener.open.call_args.kwargs["timeout"], 30)

    def test_failure_does_not_switch_hosts(self):
        for error, status in ((urllib.error.URLError("unreachable"), None),
                              (urllib.error.HTTPError("https://hapi.kurox.cn/api/auth",
                                                      530, "unavailable", {}, None), 530)):
            with self.subTest(status=status):
                self.client.opener.open.reset_mock()
                self.client.opener.open.side_effect = error
                with self.assertLogs("cross_zone.hapi", level="WARNING") as captured, self.assertRaises(HapiError) as raised:
                    self.client.authenticate()
                self.assertIn("host=hapi.kurox.cn", "\n".join(captured.output))
                self.assertEqual(raised.exception.status, status)
                self.assertEqual(self.urls(), ["https://hapi.kurox.cn/api/auth"])

    def test_idle_polling_and_interaction_switch_hosts(self):
        self.client.opener.open.side_effect = [response({"token": "jwt"}),
                                               response({"sessions": []}),
                                               response({"ok": True}),
                                               response({"sessions": []})]
        self.client.set_interactive(False)
        self.client.sessions()
        self.client.set_interactive(True)
        self.client.send("blue", "ready", "ready-id")
        self.client.set_interactive(False)
        self.client.sessions()
        self.assertEqual(self.urls(), ["https://hapi-cf.kurox.cn/api/auth",
                                       "https://hapi-cf.kurox.cn/api/sessions",
                                       "https://hapi.kurox.cn/api/sessions/blue/messages",
                                       "https://hapi-cf.kurox.cn/api/sessions"])

    def test_debug_timings_do_not_log_credentials_or_bodies(self):
        self.client.opener.open.side_effect = [response({"token": "private-response-token"}),
                                               response({"ok": "private-response-body"})]
        with self.assertLogs("cross_zone.hapi", level="DEBUG") as captured:
            self.client.send("blue", "private-request-body", "event-1")
        logs = "\n".join(captured.output)
        self.assertIn("HTTP begin", logs)
        self.assertIn("HTTP headers", logs)
        self.assertIn("HTTP body end", logs)
        self.assertIn("route=messages", logs)
        self.assertIn("elapsed_ms=", logs)
        for secret in ("test-key", "private-response-token", "private-response-body", "private-request-body"):
            self.assertNotIn(secret, logs)

    def test_message_logs_identify_session_and_page_direction_without_query_values(self):
        session = "19146292-52a4-4094-9cd5-6086b0c3ec05"
        for query, direction in (({}, "latest"), ({"afterSeq": 1}, "after"), ({"beforeSeq": 2}, "before")):
            with self.subTest(direction=direction):
                self.client.opener.open.side_effect = [response({"token": "jwt"}), response({"messages": []})]
                self.client.token = None
                with self.assertLogs("cross_zone.hapi", level="DEBUG") as captured:
                    self.client.messages(session, **query, private="private-query-value")
                logs = "\n".join(captured.output)
                self.assertIn("route=messages session=" + session + " direction=" + direction, logs)
                self.assertNotIn("private-query-value", logs)

    def test_bound_discovery_requests_stay_on_cf_while_interaction_uses_hapi(self):
        self.client.set_interactive(True)
        self.client.opener.open.side_effect = [response({"token": "jwt"}), response({"sessions": []}),
                                               response({"messages": []}), response({"messages": []}),
                                               response({"ok": True})]
        self.client.sessions(discovery=True)
        self.client.messages("blue", discovery=True, afterSeq=1)
        self.client.messages("blue", afterSeq=1)
        self.client.send("blue", "result", "event-1")
        self.assertEqual(self.urls(), ["https://hapi-cf.kurox.cn/api/auth",
                                       "https://hapi-cf.kurox.cn/api/sessions?active=true",
                                       "https://hapi-cf.kurox.cn/api/sessions/blue/messages?afterSeq=1",
                                       "https://hapi.kurox.cn/api/sessions/blue/messages?afterSeq=1",
                                       "https://hapi.kurox.cn/api/sessions/blue/messages"])
        self.assertEqual(self.client.base, "https://hapi.kurox.cn/api/")

    def test_failed_discovery_request_never_falls_back_to_hapi(self):
        self.client.set_interactive(True)
        self.client.token = "jwt"
        self.client.expires = float("inf")
        self.client.opener.open.side_effect = urllib.error.URLError("unavailable")
        with self.assertLogs("cross_zone.hapi", level="WARNING"), self.assertRaises(HapiError):
            self.client.sessions(discovery=True)
        self.assertEqual(self.urls(), ["https://hapi-cf.kurox.cn/api/sessions?active=true"])

    def test_discovery_host_rule_preserves_prefixes_and_custom_hubs(self):
        for base, expected in (("https://hapi.kurox.cn/prefix/", "https://hapi-cf.kurox.cn/prefix/api/"),
                               ("https://hapi.kurox.cn:443/", "https://hapi-cf.kurox.cn:443/api/"),
                               ("https://example.test/prefix/", "https://example.test/prefix/api/")):
            with self.subTest(base=base):
                client = HapiClient(base, "test-key")
                self.assertEqual(client.discovery_base, expected)
                self.assertEqual(client.base, base + "api/")

    def test_custom_hubs_and_path_prefixes_are_preserved(self):
        for base in ("https://example.test/prefix/", "https://hapi.kurox.cn/prefix/",
                     "http://hapi.kurox.cn/", "https://hapi-cf.kurox.cn/"):
            with self.subTest(base=base):
                client = HapiClient(base, "test-key")
                for active in (False, True):
                    client.set_interactive(active)
                    self.assertEqual(client.base, base + "api/")
