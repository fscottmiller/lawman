"""A stand-in for GitHub's REST API, served over a real local socket.

CI must not depend on a live, mutable issue: an edit to a real issue would
change what the suite proves, and a network outage would change whether it
runs at all. So these tests point Lawman at a local server that speaks HTTP
for real — real request line, real headers, real bytes back.

It records what it was asked for, which is half the contract under test. The
other half is what Lawman refuses, so the server can also answer with a
status, a body, or a delay that GitHub would never produce.
"""

import contextlib
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OWNER = "fscottmiller"
REPOSITORY = "lawman"
NUMBER = 8
NODE_ID = "I_kwDOexample"
UPDATED_AT = "2026-08-08T00:00:00Z"


def issue(body, *, number=NUMBER, owner=OWNER, repository=REPOSITORY, node_id=NODE_ID, updated_at=UPDATED_AT, **rest):
    """A GitHub issue payload, shaped like the real one and mostly ignored."""
    return {
        "number": number,
        "node_id": node_id,
        "title": "Read authoritative work contracts from GitHub Issues",
        "state": "open",
        "html_url": f"https://github.com/{owner}/{repository}/issues/{number}",
        "updated_at": updated_at,
        "labels": [{"name": "contract"}, {"name": "AC1: everything passes"}],
        "comments": 3,
        "user": {"login": owner},
        "body": body,
        **rest,
    }


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._answer()

    def do_POST(self):
        self._answer()

    def do_PATCH(self):
        self._answer()

    def do_DELETE(self):
        self._answer()

    def _answer(self):
        # Header names are case-insensitive on the wire, so they are recorded
        # in one case and a test asserts on that, not on how urllib spelled it.
        self.server.received.append(
            {
                "method": self.command,
                "path": self.path,
                "headers": {name.lower(): value for name, value in self.headers.items()},
            }
        )
        if self.server.delay:
            threading.Event().wait(self.server.delay)
        body = self.server.body
        self.send_response(self.server.status)
        for name, value in self.server.headers_out:
            self.send_header(name, value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            self.wfile.write(body)

    def log_message(self, *args):
        """A test suite is not a web server log."""

    def handle_one_request(self):
        """A client that gave up — Lawman timing out — is not a server error."""
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            super().handle_one_request()


def _bytes(body):
    if isinstance(body, bytes):
        return body
    return (body if isinstance(body, str) else json.dumps(body)).encode("utf-8")


@contextmanager
def serving(body, *, status=200, headers=(), delay=0.0):
    """Serve one canned response, and hand back the server that recorded the requests."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.received = []
    server.status = status
    server.body = _bytes(body)
    server.headers_out = tuple(headers)
    server.delay = delay
    server.origin = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def unreachable():
    """An origin nothing is listening on: a bound port, closed again."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    origin = f"http://127.0.0.1:{server.server_address[1]}"
    server.server_close()
    return origin
