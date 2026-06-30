from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from game_engine.backend.serialization import export_submission_payload
from shared.contracts import ClientResult


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
    competition_id: str = "easy",
    client_result: ClientResult | None = None,
    timeout: float = 5.0,
) -> SubmissionResult:
    if client_result is None:
        return SubmissionResult(
            False,
            "Trusted v2 submission requires a client_result. Use competition_main.py.",
        )
    payload = export_submission_payload(
        car=car,
        group_id=group_id,
        username=username,
    )
    body = json.dumps({**payload.to_dict(), "client_result": client_result.to_dict()}).encode(
        "utf-8"
    )
    if competition_id == "final":
        url = server_url.rstrip("/") + "/v2/finals/submissions"
    else:
        url = server_url.rstrip("/") + f"/v2/competitions/{competition_id}/submissions"
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
    if not submission_id:
        return SubmissionResult(False, "Submit failed: missing submission id")
    return SubmissionResult(
        True,
        f"Submitted {submission_id} ({data.get('competition_id', competition_id)})",
        submission_id,
    )
