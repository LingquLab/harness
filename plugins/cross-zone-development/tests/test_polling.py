"""Deterministic traffic regressions without external services or real sleeps."""

import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from cross_zone.config import load_config
from cross_zone.controller import Bridge
from cross_zone.hapi import HapiClient, HapiError
from cross_zone.scheduling import SessionSync
OWNER = "19146292-52a4-4094-9cd5-6086b0c3ec05"
from test_bridge import FakeClient, config, general_task


class SessionSyncTests(unittest.TestCase):
    def test_hints_coalesce_and_worker_wakes_do_not_fetch(self):
        sync = SessionSync(5, threading.Event())
        self.assertTrue(sync.due(0))
        for _ in range(1000):
            sync.set()
        self.assertFalse(sync.due(0.5))
        self.assertEqual(sync.wait_seconds(0.5), 0.5)
        self.assertTrue(sync.due(1))
        self.assertFalse(sync.pending.is_set())
        sync.wake.set()  # Worker completion, independent of SSE.
        self.assertFalse(sync.due(2))
        self.assertEqual(sync.wait_seconds(2), 4)
        self.assertTrue(sync.due(6))  # REST fallback, with no further SSE.

    def test_notification_during_fetch_survives_and_small_poll_is_respected(self):
        sync = SessionSync(0.1, threading.Event())
        self.assertTrue(sync.due(0))
        sync.set()  # Arrives after due() cleared hints, while REST is in flight.
        self.assertFalse(sync.due(0.05))
        self.assertTrue(sync.due(0.1))


class BridgeLoopTests(unittest.TestCase):
    def run_loop(self, sse):
        with tempfile.TemporaryDirectory() as directory:
            cfg = config(directory)
            cfg.update(poll_seconds=5, sse=sse)
            client = FakeClient()
            client.listen = Mock()
            bridge = Bridge(cfg, client)
            bridge.bind()
            clock = [0]
            receiver = []

            def launch_listener(**kwargs):
                receiver.append(kwargs['args'][1])
                return Mock()

            def wait(timeout):
                clock[0] += min(timeout, 0.25)
                if receiver:
                    receiver[0].set()
                else:
                    bridge.wake.set()  # Frequent worker wakes must not force GETs.
                if clock[0] >= 12:
                    bridge.stop.set()

            with patch('cross_zone.controller.time.monotonic', side_effect=lambda: clock[0]), \
                    patch('cross_zone.controller.threading.Thread', side_effect=launch_listener), \
                    patch.object(bridge.wake, 'wait', side_effect=wait), \
                    patch.object(client, 'messages', wraps=client.messages) as messages:
                bridge.run()
            return messages.call_count

    def test_worker_wakes_preserve_rest_fallback_cadence(self):
        self.assertEqual(self.run_loop(False), 3)  # t=0,5,10

    def test_explicit_bridge_also_coalesces_sse_hints(self):
        self.assertEqual(self.run_loop(True), 12)  # t=0..11, despite 4 hints/sec


class SseBackoffTests(unittest.TestCase):
    def exercise(self, durations):
        clock, delays, requests = [0], [], []
        stop, wake = threading.Event(), threading.Event()
        client = HapiClient('http://localhost/', 'fixture-key')

        def open_stream(path, **kwargs):
            requests.append((path, kwargs))
            stream = io.BytesIO(b'id: saved-event\ndata: {}\n\n')
            stream.headers = {'Content-Type': 'text/event-stream'}
            original = stream.readline
            duration = durations[len(requests) - 1]

            def read(size):
                line = original(size)
                if not line:
                    clock[0] += duration
                return line

            stream.readline = read
            return stream

        def wait(delay):
            delays.append(delay)
            clock[0] += delay
            if len(delays) == len(durations):
                stop.set()

        with patch.object(client, 'authenticate', return_value='fixture-token'), \
                patch.object(client, '_open', side_effect=open_stream), \
                patch('cross_zone.hapi.time.monotonic', side_effect=lambda: clock[0]), \
                patch.object(stop, 'wait', side_effect=wait):
            client.listen(OWNER, wake, stop)
        self.assertTrue(wake.is_set())
        self.assertEqual(requests[1][1]['headers']['Last-Event-ID'], 'saved-event')
        self.assertEqual(requests[0][1]['headers']['Authorization'], 'Bearer fixture-token')
        return delays

    def test_successful_headers_with_immediate_eof_back_off(self):
        self.assertEqual(self.exercise([0] * 8), [1, 2, 4, 8, 16, 30, 30, 30])

    def test_only_stable_stream_resets_backoff(self):
        self.assertEqual(self.exercise([0, 0, 30, 0]), [1, 2, 1, 2])
