from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from game_engine.backend.serialization import export_submission_payload


@dataclass(slots=True)
class SubmissionResult:
    ok: bool
    message: str
    submission_id: str | None = None


def submit_car(
    *,
    server_url: str,
    car: Any,
    group_id: str,
    username: str,
    timeout: float = 5.0,
) -> SubmissionResult:
    payload = export_submission_payload(
        car=car,
        group_id=group_id,
        username=username,
    )
    body = json.dumps(payload.to_dict()).encode("utf-8")
    url = server_url.rstrip("/") + "/api/submissions"
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return SubmissionResult(False, f"Submit failed: HTTP {exc.code} {detail}")
    except (TimeoutError, URLError) as exc:
        return SubmissionResult(False, f"Submit failed: {exc}")

    submission_id = data.get("submission_id")
    phase = data.get("phase", "unknown")
    if not submission_id:
        return SubmissionResult(False, "Submit failed: missing submission id")
    return SubmissionResult(True, f"Submitted {submission_id} ({phase})", submission_id)
