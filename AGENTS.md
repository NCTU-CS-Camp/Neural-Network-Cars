# Server Agent Handoff

## Project Mission

This repo now centers on a trusted-client Neural Cars competition server. The server receives exactly one locally selected winner model plus its client-reported `client_result`, validates and stores that payload, ranks by the uploaded metrics, and feeds the browser leaderboard plus Pygame replay.

The server must not breed, mutate, select among 20 candidates, or overwrite official metrics by rejudging submissions. Those steps belong to the Game Engine client. Server replay is for visualization and audit, not for replacing the submitted result.

## Current State

- FastAPI v2 server lives in `server/app.py`.
- SQLite persistence and ranking live in `server/storage.py`; schema version is `trusted-client-v2`.
- Fixed competition maps are loaded from `maps/kaggle_easy.*`, `maps/kaggle_hard.*`, and `maps/kaggle_final.*` through `server/competition_maps.py`.
- Shared payload contracts live in `shared/contracts.py`.
- Phase 1 has independent `easy` and `hard` competitions keyed by `(group_id, username)`.
- Final is group-based and locks one accepted model per `group_id`.
- Public browser leaderboard is served at `/leaderboard`.
- Admin page is served at `/admin`.
- Admin UI initially shows only the token form; protected content is revealed after `GET /v2/admin/state` succeeds.
- Protected replay payload is served by `GET /v2/admin/replay`.
- Pygame big-screen replay is launched with `uv run python replay.py`.
- Manual training/submission test client is launched with `uv run python competition_main.py`.
- `judge_demo.py` has been removed; do not document or revive it unless explicitly requested.
- Competition maps under `maps/*_maps` carry ordered `route_cells` and boundary `checkpoints`.
- Shared lap/progress tracking lives in `game_engine/backend/competition_track.py` and is used by local scoring plus replay visualization.

## Public Contract

Current implemented submission payload shape:

Model payload shape:

```json
{
  "group_id": "1",
  "username": "player1",
  "weights": [[36], [24]],
  "biases": [[6], [4]]
}
```

Submission adds `client_result`:

```json
{
  "completed": false,
  "lap_ticks": null,
  "max_progress": 1250.5,
  "ticks_to_max_progress": 840
}
```

Spec_v2 pending payload additions:

```json
{
  "skin_id": 3,
  "maxSpeed": 10.0,
  "client_result": {
    "survival_rate": 0.467
  },
  "training_strategy": {
    "strategy_id": "progress_first_v2",
    "base_preset_id": "progress-first",
    "fitness_config": {}
  }
}
```

Current implementation does not yet accept or persist `skin_id`, `maxSpeed`, or `client_result.survival_rate`. `training_strategy` appears in the spec_v2 export format and should not be treated as a required submission field unless the server contract is explicitly changed. When implementing alignment, prefer accepting the new fields as optional metadata first; ranking must remain based on `completed`, `lap_ticks`, `max_progress`, and `ticks_to_max_progress`.

Validation rules:

- `group_id` and `username` must be non-empty strings.
- Weight lengths are 36 and 24; bias lengths are 6 and 4.
- All gene and result values must be finite.
- Completed runs require positive `lap_ticks`.
- Incomplete runs require `lap_ticks: null`.
- Tick values must not exceed the configured frame limit.

Ranking order:

- Completed submissions rank before incomplete submissions.
- Completed submissions sort by lowest `lap_ticks`.
- Incomplete submissions sort by highest `max_progress`.
- Ties use lowest `ticks_to_max_progress`, earliest accepted submission time, then submission ID.
- Easy/Hard keep each `(group_id, username)` identity's historical best.
- Final keeps each `group_id` locked model.

## API Surface

Public:

```text
GET  /v2/state
GET  /v2/maps
GET  /v2/maps/{competition_id}/preview
POST /v2/competitions/{easy|hard}/eligibility
POST /v2/competitions/{easy|hard}/submissions
POST /v2/finals/eligibility
POST /v2/finals/submissions
GET  /v2/competitions/{easy|hard|final}/leaderboard
GET  /v2/competitions/{competition_id}/submissions/{submission_id}
GET  /ws/events
```

Protected admin/replay, all requiring `X-Admin-Token`:

```text
GET  /v2/admin/submissions
GET  /v2/admin/state
GET  /v2/admin/replay
POST /v2/admin/stage
POST /v2/admin/config
POST /v2/admin/batches/run-now
POST /v2/admin/replay/restart
POST /v2/admin/reset-all
```

Current implementation uses `POST` eligibility endpoints and expects both `group_id` and `username`, including Final eligibility. If spec text says GET or group-only Final eligibility, treat that as an alignment gap rather than silently changing behavior.

## Spec_v2 Server Delta

The latest spec_v2 reinforces the server-first boundary:

- Server receives only one locally selected winner model plus `client_result`.
- Client owns parent training, 20-candidate generation, local evaluation, and local winner selection.
- Server validates, rate-limits, queues, persists, ranks, and feeds replay/leaderboard.
- Server must not breed, mutate, select candidates, or overwrite official metrics by re-running scoring.

New or sharpened server-facing requirements:

- Submission/export metadata now mentions `skin_id` and `maxSpeed`.
- `client_result` now mentions optional-looking `survival_rate`; it is not part of the stated ranking tuple.
- Eligibility responses should expose `next_submission_at`, current stage, and `competition_config_version`.
- Submission responses should expose `submission_id`, `status`, `submitted_at`, `next_submission_at`, and `competition_config_version`.
- Phase 1 spec language says 5-minute replay/leaderboard cadence; current implementation supports admin-configurable 1/2/5 minute intervals and defaults to 1 minute for classroom/demo use.
- Dashboard/leaderboard should show rank, group id, username, submission id, status, result, replay completed time, and next submission time.
- Replay batch should retain included submission IDs, deferred submission IDs, leaderboard snapshot, replay status, termination reason, map/config versions, and optional deterministic tick/state logs.

Current alignment gaps:

- `skin_id`, `maxSpeed`, and `survival_rate` are not in `shared/contracts.py`, storage, public responses, or replay payloads.
- `running` is currently transitional inside one storage transaction, not a long-lived replay-processing state.
- No persistent deferred-submission list or deferred notification exists.
- No persistent replay playback/audit record exists beyond `batches.snapshot_json`.
- Public leaderboard does not yet expose every spec-listed field consistently.
- Candidate tie-breaker `candidate_index` is client-only because the server receives only the selected winner; server tie-breaks remaining equality by accepted time and submission ID.

## Batching Process

Phase 1 Easy/Hard submissions enter storage as `queued`. Final submissions skip the Phase 1 batch path and become completed immediately after acceptance.

`BatchWorker` in `server/evaluation_worker.py` polls periodically and calls `CompetitionStorage.seal_phase_one_batches()`. Normal sealing uses the previous UTC boundary for the persisted `phase_one_batch_minutes` interval as the cutoff. Admin demo sealing uses `POST /v2/admin/batches/run-now`, which force-seals currently queued Easy/Hard submissions. Admin can set the interval to 1, 2, or 5 minutes through `POST /v2/admin/config`; the selected interval also controls Easy/Hard cooldown.

Current batch behavior:

- For each of `easy` and `hard`, select queued rows with `submitted_at` before the cutoff, or at/before `now` in force mode.
- Update selected rows to `running`.
- Immediately update the same rows to `completed`, set `completed_at`, and assign a new `batch_id`.
- Create one `batches` row per competition with `window_start`, `window_end`, `created_at`, included `submission_ids`, and the public leaderboard snapshot.
- Publish a competition update event after worker processing when submissions were processed.

Known batching gaps:

- No persistent deferred submission list.
- No persistent replay playback record.
- No tick/state audit log.
- No saved termination reason or replay status per submitted model.
- No explicit notification for submissions that missed the current batch.
- The `running` state is currently transitional inside one transaction, not a long-lived replay-processing state.

## Replay And Lap Detection

- Local scoring and Pygame replay use sequential boundary checkpoint crossing to detect first-lap completion.
- A replay car stops updating after first lap completion, collision, or stagnation.
- Finished replay cars stay visible, dimmed, and labeled `FINISHED` with finish time.
- The Pygame replay client fetches the protected replay payload every 5 seconds and compares stage, replay generation, and leaderboard signatures to detect new data without changing API shape.
- New snapshots and admin stage changes are adopted only at a safe replay boundary, after the current replay cycle finishes.
- The first replay cycle for a newly seen leaderboard hides that competition's leaderboard, then reveals it after the corresponding Easy/Hard/Final session stops; later cycles for the same snapshot show the leaderboard normally.
- Once all replay cars are finished/crashed/stalled, the replay holds for 3 seconds and then either adopts pending replay data or restarts the current payload.
- Browser leaderboard displays a live countdown to the next Phase 1 snapshot and last update time.
- Replay header uses large status/timing text for projection. `COMPETITION_REPLAY_FONT_PATH` can force a CJK-capable font if the OS fallback is insufficient.
- The server still trusts submitted `client_result`; replay completion never overwrites ranking metrics.

## Server Ownership Rules

- Validate payload shape, identity, finite values, payload size, cooldown, stage gates, and Final locks.
- Keep public responses free of weights and biases.
- Keep protected replay/admin payloads behind `X-Admin-Token`.
- Preserve immutable competition configuration unless the spec explicitly changes it.
- Publish update events after stage changes, Final acceptance, reset, replay restart, and completed batch work.
- Reset should clear submissions, batches, snapshots, cooldown history, and replay data while preserving current stage/configuration.
- Do not make server-side GA decisions. The submitted winner model and `client_result` are authoritative.
- Keep admin UI state and controls behind token validation; public `/v2/state` remains available for public leaderboard/replay countdown behavior.

## Server-Facing Integration Boundaries

Game Engine client responsibilities:

- Train parents across maps.
- Build 20 candidates from parents before submission.
- Run candidates locally on the selected competition map.
- Select the single local winner by the official ranking tuple.
- Submit only that winner model plus `client_result`.

GA/Fitness responsibilities:

- Provide experimental fitness functions and parent selection.
- Produce fitness panel data for the Game Engine UI.
- Never write experimental fitness scores into the official leaderboard contract.

Server responsibilities:

- Accept only one winner model per submission request.
- Rank only by `client_result`.
- Replay submitted model payloads for display/audit.

## Operational Commands

Use `uv run ...` directly in this environment. Some historical docs mention `rtk`; do not assume it exists in the shell.

```bash
uv sync
uv run python -m server.app
uv run python competition_main.py
uv run python replay.py
uv run pytest
uv run ruff check .
uv run mypy game_engine GA server shared
```

For classroom LAN deployment, bind FastAPI to all interfaces:

```bash
uv run uvicorn server.app:app --host 0.0.0.0 --port 8000
```

If replay cannot render CJK status text on a lab machine, provide an installed font path:

```bash
COMPETITION_REPLAY_FONT_PATH=/path/to/NotoSansCJK-Regular.ttc uv run python replay.py
```

Useful local URLs:

- `http://127.0.0.1:8000/leaderboard`
- `http://127.0.0.1:8000/admin`

Default local admin/replay token is `admin`, overridden by `COMPETITION_ADMIN_TOKEN`.

## Roadmap

1. Replay/Audit Persistence
   - Persist replay batches beyond public leaderboard snapshots.
   - Store deferred submission IDs, map/config versions, simulation version, replay status, termination reason, and audit references.
   - Add optional deterministic tick/state logs or compact replay traces for later verification.
   - Make `running` meaningful if replay processing becomes asynchronous instead of immediately completed.
   - Consider persisting replay-loop status now shown client-side only.

2. API Spec Alignment
   - Add optional server support for `skin_id`, `maxSpeed`, and `client_result.survival_rate`, including validation, persistence, public/admin response policy, and replay payload policy.
   - Decide whether eligibility should remain `POST` or move to spec-mentioned `GET`.
   - Align response field names across docs and code.
   - Decide whether Final eligibility should require `username` or only `group_id`.
   - Decide whether the official Phase 1 interval should be fixed at 5 minutes during real competition while keeping 1/2/5 minute admin control for demos.
   - Keep docs/api-spec.md and AGENTS.md updated together.

3. Leaderboard And Replay Completeness
   - Expose submission ID, status, completed/replay time, next submission time, rank, and audit/replay references consistently.
   - Preserve top-15 protected replay payload behavior while improving public leaderboard detail.
   - Add clear handling for empty windows, deferred submissions, and replay restart semantics.

4. Competition Client Alignment
   - `competition_main.py` is currently a manual test client.
   - Future Game Engine work should implement spec_v2's parent export/import, 20-candidate local winner selection, validation mode, and official local ranking tuple.
   - Server contract should remain one submitted winner model plus `client_result`.

5. GA/Fitness Integration Boundary
   - Document official metric definitions shared with GA/Fitness.
   - Keep experimental fitness score APIs out of the server ranking path.
   - Add tests that leaderboard order cannot be affected by non-contract fitness metadata.

## Testing Expectations

Run tests for any behavior change:

```bash
uv run pytest
uv run ruff check .
uv run mypy game_engine GA server shared
```

Current key test coverage is in `tests/test_competition_server.py`, `tests/test_competition_client.py`, and `tests/test_track_generation.py`.

When changing server behavior, add focused tests for:

- eligibility and cooldown enforcement;
- payload validation;
- ranking ties;
- batch sealing;
- protected replay payload access;
- reset behavior;
- public responses not leaking weights or biases.

## Maintenance Rule

Treat this file as the living server handoff. Update it whenever spec_v2, public APIs, batching, replay, leaderboard, storage, or operational commands change.
