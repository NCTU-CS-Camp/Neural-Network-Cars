from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from server.models import SubmissionRecord
from server.replay_queue import ReplayQueue
from server.storage import JsonStorage
from shared.contracts import ReplayRequest, WeightPayload


STORAGE = JsonStorage()
REPLAY_QUEUE = ReplayQueue(STORAGE)


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "NeuralCarsServer/0.1"

    def _read_json(self) -> dict:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, payload: dict | list, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/health":
            self._send_json({"status": "ok"})
            return

        if path == "/submissions":
            self._send_json(STORAGE.list_submissions())
            return

        if path.startswith("/submissions/"):
            submission_id = path.split("/")[-1]
            submission = STORAGE.get_submission(submission_id)
            if submission is None:
                self._send_json(
                    {"error": "submission not found"},
                    status=HTTPStatus.NOT_FOUND,
                )
                return
            self._send_json(submission)
            return

        if path == "/leaderboard":
            self._send_json(STORAGE.leaderboard())
            return

        if path == "/replays":
            self._send_json(STORAGE.list_replay_jobs())
            return

        self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        payload = self._read_json()

        if path == "/submissions":
            weight_payload = WeightPayload.from_dict(payload)
            submission = SubmissionRecord.create(weight_payload)
            self._send_json(
                STORAGE.add_submission(submission.to_dict()),
                status=HTTPStatus.CREATED,
            )
            return

        if path == "/replays":
            replay_request = ReplayRequest.from_dict(payload)
            replay_job = REPLAY_QUEUE.enqueue(replay_request)
            self._send_json(replay_job, status=HTTPStatus.CREATED)
            return

        self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), RequestHandler)
    print(f"Server listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
