# Trusted Client Competition API v2

The server validates payloads, identities, cooldowns, batches, snapshots, and ranking. It
does not replay submissions to calculate official metrics: the client-provided
`client_result` is the ranking source.

## Competition State

`GET /v2/state` returns the active stage, `competition-2026-v1` settings, next UTC batch
time, and the fixed Easy, Hard, and Final maps.

- Phase 1 accepts `easy` and `hard` submissions from individual identities
  `(group_id, username)`.
- Final accepts one submission per `group_id`.
- Configuration: 30 FPS, 900-frame limit, 180-tick stagnation limit, and an admin-selected
  Phase 1 snapshot/cooldown interval of 1, 2, or 5 minutes.

## Eligibility And Submission

Before local evaluation, clients call one of these endpoints with `group_id` and `username`:

```text
POST /v2/competitions/easy/eligibility
POST /v2/competitions/hard/eligibility
POST /v2/finals/eligibility
```

The response includes `eligible`, a rejection `reason` when blocked, `next_submission_at`,
current `stage`, and `competition_config_version`. Eligibility is advisory; the matching
submission endpoint repeats the check atomically.

```text
POST /v2/competitions/{easy|hard}/submissions
POST /v2/finals/submissions
```

Request body:

```json
{
  "group_id": "1",
  "username": "player1",
  "weights": [[36 floats], [24 floats]],
  "biases": [[6 floats], [4 floats]],
  "client_result": {
    "completed": false,
    "lap_ticks": null,
    "max_progress": 1250.5,
    "ticks_to_max_progress": 840
  }
}
```

All genes and progress values must be finite. Incomplete runs require `lap_ticks: null`;
completed runs require a positive `lap_ticks`. Tick values cannot exceed 900.

Easy and Hard have separate cooldowns using the current `phase_one_batch_minutes` interval.
Cooldown failures return `429` with `error: submission_cooldown`; closed competitions and a
locked Final group return `409`. Successful Phase 1 submissions are `queued` until the next
snapshot; Final submissions become `completed` immediately.

## Public Data

```text
GET /v2/competitions/{easy|hard|final}/leaderboard
GET /v2/competitions/{competition_id}/submissions/{submission_id}
GET /v2/maps
GET /v2/maps/{competition_id}/preview
GET /ws/events
```

Leaderboards keep each individual's historical best for Easy/Hard and each group's locked
Final result. Ranking is completed runs, fastest lap ticks, maximum progress, earliest tick to
that progress, earliest accepted submission, then submission ID.

Public responses never contain weights or biases. WebSocket events use
`competition_snapshot_updated` and contain stage, config, and public leaderboards.

## Protected Admin And Replay APIs

All protected endpoints require `X-Admin-Token`.

```text
GET  /v2/admin/submissions
GET  /v2/admin/replay
POST /v2/admin/stage              { "stage": "phase_one" | "final" }
POST /v2/admin/config             { "phase_one_batch_minutes": 1 | 2 | 5 }
POST /v2/admin/batches/run-now
POST /v2/admin/replay/restart
POST /v2/admin/reset-all
```

`/v2/admin/replay` is the only HTTP endpoint that returns top-15 model parameters for the
Pygame big-screen replay. Reset clears submissions, cooldown history, and snapshots while
preserving the selected stage and Phase 1 interval.

`POST /v2/admin/replay/restart` increments the replay generation without changing any
submission or leaderboard data. Active replay clients poll this generation and restart from
spawn within one second.
