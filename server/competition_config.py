from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any


COMPETITION_CONFIG_VERSION = "competition-2026-v1"
SIMULATION_FPS = 30
FRAME_LIMIT = 900
STAGNATION_TICKS = 180
PHASE_ONE_BATCH_MINUTES = 5
PHASE_ONE_REPLAY_LIMIT = 15
LEADERBOARD_LIMIT = 30
MAX_SUBMISSION_BYTES = 32 * 1024


def next_batch_boundary(now: datetime) -> datetime:
    """Return the first UTC five-minute boundary strictly after ``now``."""
    value = now.astimezone(UTC).replace(second=0, microsecond=0)
    minute = (value.minute // PHASE_ONE_BATCH_MINUTES) * PHASE_ONE_BATCH_MINUTES
    boundary = value.replace(minute=minute)
    return boundary + timedelta(minutes=PHASE_ONE_BATCH_MINUTES)


def previous_batch_boundary(now: datetime) -> datetime:
    value = now.astimezone(UTC).replace(second=0, microsecond=0)
    minute = (value.minute // PHASE_ONE_BATCH_MINUTES) * PHASE_ONE_BATCH_MINUTES
    return value.replace(minute=minute)


def public_config(now: datetime) -> dict[str, Any]:
    return {
        "version": COMPETITION_CONFIG_VERSION,
        "simulation_fps": SIMULATION_FPS,
        "frame_limit": FRAME_LIMIT,
        "stagnation_ticks": STAGNATION_TICKS,
        "phase_one_batch_minutes": PHASE_ONE_BATCH_MINUTES,
        "next_phase_one_batch_at": next_batch_boundary(now).isoformat(),
    }
