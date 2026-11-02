"""Coalesce SSE hints without turning worker completion into network polling."""

import threading


class SessionSync:
    def __init__(self, poll_seconds, wake):
        self.poll_seconds = poll_seconds
        self.wake = wake
        self.pending = threading.Event()
        self.next_poll = 0
        self.next_event_sync = 0

    def set(self):
        # One wake per pending batch, including during a notification storm.
        if not self.pending.is_set():
            self.pending.set()
            self.wake.set()

    def due(self, now):
        if now < self.next_poll and not (self.pending.is_set() and now >= self.next_event_sync):
            return False
        # Clear before fetching: notifications arriving during the fetch survive.
        self.pending.clear()
        self.next_poll = now + self.poll_seconds
        self.next_event_sync = now + min(1, self.poll_seconds)
        return True

    def wait_seconds(self, now):
        deadline = self.next_poll
        if self.pending.is_set():
            deadline = min(deadline, self.next_event_sync)
        return max(0, deadline - now)
