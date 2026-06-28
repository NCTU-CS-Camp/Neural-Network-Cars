from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any


COMPETITION_CONFIG_VERSION = "competition-2026-v1"
SIMULATION_FPS = 30
FRAME_LIMIT = 900
STAGNATION_TICKS = 180
PHASE_ONE_BATCH_MINUTES = 1
ALLOWED_PHASE_ONE_BATCH_MINUTES = (1, 2, 5)
PHASE_ONE_REPLAY_LIMIT = 15
LEADERBOARD_LIMIT = 30
MAX_SUBMISSION_BYTES = 32 * 1024


def validate_phase_one_batch_minutes(value: int) -> int:
    if value not in ALLOWED_PHASE_ONE_BATCH_MINUTES:
        allowed = ", ".join(str(item) for item in ALLOWED_PHASE_ONE_BATCH_MINUTES)
        raise ValueError(f"phase_one_batch_minutes must be one of: {allowed}")
    return value


def next_batch_boundary(
    now: datetime,
    phase_one_batch_minutes: int = PHASE_ONE_BATCH_MINUTES,
) -> datetime:
    """Return the first UTC batch boundary strictly after ``now``."""
    phase_one_batch_minutes = validate_phase_one_batch_minutes(phase_one_batch_minutes)
    value = now.astimezone(UTC).replace(second=0, microsecond=0)
    minute = (value.minute // phase_one_batch_minutes) * phase_one_batch_minutes
    boundary = value.replace(minute=minute)
    return boundary + timedelta(minutes=phase_one_batch_minutes)


def previous_batch_boundary(
    now: datetime,
    phase_one_batch_minutes: int = PHASE_ONE_BATCH_MINUTES,
) -> datetime:
    phase_one_batch_minutes = validate_phase_one_batch_minutes(phase_one_batch_minutes)
    value = now.astimezone(UTC).replace(second=0, microsecond=0)
    minute = (value.minute // phase_one_batch_minutes) * phase_one_batch_minutes
    return value.replace(minute=minute)


def public_config(
    now: datetime,
    *,
    phase_one_batch_minutes: int = PHASE_ONE_BATCH_MINUTES,
) -> dict[str, Any]:
    phase_one_batch_minutes = validate_phase_one_batch_minutes(phase_one_batch_minutes)
    return {
        "version": COMPETITION_CONFIG_VERSION,
        "simulation_fps": SIMULATION_FPS,
        "frame_limit": FRAME_LIMIT,
        "stagnation_ticks": STAGNATION_TICKS,
        "phase_one_batch_minutes": phase_one_batch_minutes,
        "next_phase_one_batch_at": next_batch_boundary(
            now,
            phase_one_batch_minutes,
        ).isoformat(),
    }
