# Current Replay And Leaderboard UI Notes

This document records the current frontend style and implementation shape for the Pygame replay display and browser leaderboard. It is a baseline for future redesign work, not a redesign proposal.

## Entry Points

- Pygame big-screen replay:
  - Root launcher: `replay.py`
  - Main implementation: `game_engine/frontend/replay_client.py`
  - Data source: protected `GET /v2/admin/replay`
  - Token: `COMPETITION_REPLAY_TOKEN`, defaulting to `admin`
- Browser leaderboard:
  - Static page: `server/static/leaderboard.html`
  - Data sources:
    - `GET /v2/state`
    - `GET /v2/competitions/{easy|hard|final}/leaderboard`
    - WebSocket `/ws/events`

## Pygame Replay Visual Style

Current replay uses a dark dashboard style:

- Background: charcoal `#0B1118`
- Panel fill: `#101921`
- Border: `#273643`
- Primary text: near-white `#F4F7FB`
- Muted text: slate `#9DAEBF`
- Easy accent: cyan `#57D3CF`
- Hard accent: amber `#F4B16F`
- Final accent: violet `#D9A8FF`
- Inactive/crashed/finished car label color: gray `#5C6974`

The visual language is restrained and data-display oriented. It avoids illustration outside the track PNGs. Most UI elements are rectangular panels, thin borders, accent lines, and compact typography.

## Pygame Replay Layout

Replay renders everything to a fixed virtual canvas:

```python
VIRTUAL_SIZE = SCREEN_SIZE  # currently 1600x900
```

The actual OS window is resizable. Rendering is scaled from the virtual canvas to the real window while preserving 16:9 aspect ratio. Non-16:9 windows are letterboxed with the charcoal background.

Window controls:

- `F`: toggle fullscreen
- `R`: reset window to 1600x900
- `Esc`: leave fullscreen, or quit if already windowed

### Phase 1 Layout

Phase 1 shows Easy and Hard side by side:

- Header/title area:
  - Title: `NEURAL CARS / PHASE 1`
  - Status bar at `x=24, y=58, w=1552, h=54`
  - Status chips show elapsed time, next replay countdown, and next snapshot countdown
- Map panels:
  - Easy: `Rect(24, 136, 764, 390)`
  - Hard: `Rect(812, 136, 764, 390)`
- Leaderboard panels:
  - Easy: `Rect(24, 554, 764, 316)`
  - Hard: `Rect(812, 554, 764, 316)`
- Compact leaderboard rows:
  - Default visible rows: top 5
  - Row height: about 48 px

### Final Layout

Final uses one larger map and a right-side leaderboard:

- Header/title: `NEURAL CARS / FINAL`
- Map panel: `Rect(24, 136, 1032, 540)`
- Leaderboard panel: `Rect(1080, 136, 496, 734)`
- Visible rows: top 10

## Pygame Replay State Flow

Replay is not a browser UI; it is an immediate-mode Pygame render loop. It stores state in dataclasses and dictionaries, then redraws every frame.

Important dataclasses:

- `ReplayTrack`
  - Holds the competition map, front PNG, and collision surface.
- `ReplayCar`
  - Wraps a `Car`, color, tracker, status flags, tick count, and stagnation tracking.
- `ReplaySession`
  - Holds one competition panel's track, cars, leaderboard, reveal state, frame count, and stop state.
- `ReplayStatus`
  - Holds header status label, elapsed seconds, restart countdown, and snapshot countdown.

Main runtime state inside `run()`:

- `state`: current replay payload
- `pending_state`: fetched replay payload waiting for a safe switch
- `sessions`: current `ReplaySession` objects keyed by competition id
- `revealed_signatures`: leaderboard signatures already revealed by this replay client
- `hold_until`: 3-second hold timer after a replay cycle finishes
- `next_fetch_at`: protected replay payload polling schedule

## Replay Data Refresh Behavior

The replay client fetches protected replay data every 5 seconds:

```python
GET /v2/admin/replay
```

It compares the incoming payload identity:

- stage
- `replay_generation`
- leaderboard signatures, based on `(rank, submission_id)`

If a different payload arrives while cars are runnable, it is stored as `pending_state` and only adopted after the current replay cycle finishes. If there are no runnable cars, it can be adopted immediately.

This means replay avoids mid-race visual jumps.

## Safe-Reveal Behavior

For a newly seen leaderboard signature:

1. Replay runs the cars first.
2. The leaderboard panel shows a reveal placeholder:
   - `New snapshot replay running`
   - `Leaderboard reveals after this replay`
   - elapsed seconds
3. When that session stops, the leaderboard is revealed.
4. The panel border is highlighted for 2 seconds.
5. Later replay cycles for the same leaderboard show the leaderboard immediately.

Easy, Hard, and Final reveal independently. In Phase 1, Easy can reveal without waiting for Hard, and vice versa.

## Replay Car Behavior

Each replay car:

- Loads submitted weights/biases into a `Car`
- Uses the map-specific collision surface
- Starts from that map's spawn
- Tracks lap progress through `CompetitionRunTracker`
- Stops when:
  - first lap completes,
  - collision happens,
  - stagnation reaches `STAGNATION_TICKS`,
  - session frame limit is reached

Labels:

- Default label: username
- Finished: `username FINISHED {seconds}s`
- Stalled: `username STALLED`
- Crashed: `username CRASHED`

Labels are drawn near car positions and clamped inside the map panel.

## Replay Rendering Style

Rendering is direct Pygame drawing, not component-based:

- `_draw_phase_one(...)`
- `_draw_final(...)`
- `_draw_header(...)`
- `_draw_map_panel(...)`
- `_draw_compact_leaderboard(...)`
- `_draw_leaderboard_reveal_panel(...)`
- `_draw_panel_badge(...)`

Layout is mostly fixed rectangles and manual coordinates. There is no layout engine, flex/grid abstraction, or reusable panel object.

Current tradeoffs:

- Good: predictable big-screen composition and simple render loop.
- Good: virtual canvas keeps design stable across resizable windows.
- Weak: many magic numbers are embedded in draw functions.
- Weak: visual style and state logic are mixed in the same file.
- Weak: adding a substantially different layout will likely require refactoring draw helpers.

## Replay Fonts

Replay loads fonts through `_fonts()` in `replay_client.py`.

Current strategy:

1. Use `COMPETITION_REPLAY_FONT_PATH` if provided.
2. Try project/global CJK-capable font file paths.
3. Try Pygame font-name matching.
4. Fall back to Arial.

The font map:

- `title`: 28 px bold
- `status`: 30 px bold
- `chip`: 20 px bold
- `panel`: 18 px bold
- `row`: 17 px bold
- `label`: 15 px bold
- `meta`: 14 px regular

Note: current visible replay status strings are English. Earlier Chinese status text required a CJK font fallback; the code still supports CJK font paths.

## Browser Leaderboard Visual Style

The browser leaderboard is implemented as one static HTML file with inline CSS and JavaScript:

```text
server/static/leaderboard.html
```

Style:

- Dark background `#0B1118`
- Max content width: `1180px`
- Header with title and connection/status text
- Tabs for Easy, Hard, Final
- Accent colors match replay:
  - Easy cyan
  - Hard amber
  - Final violet
- Table-based leaderboard
- First row gets a darker highlight background
- Responsive mobile behavior hides the `Result` column at narrow widths

Current table columns:

- Rank
- Player
- Group
- Result
- Completed

For Final, the display swaps identity emphasis:

- Main name: `Group {group_id}`
- Muted text: submitting username

For Easy/Hard:

- Main name: username
- Muted text: `individual`

## Browser Leaderboard Data Flow

Initial/fallback refresh:

```javascript
Promise.all([
  fetch("/v2/state", {cache:"no-store"}),
  fetch(`/v2/competitions/${activeCompetition}/leaderboard`, {cache:"no-store"})
])
```

Live updates:

```javascript
new WebSocket(`${protocol}//${location.host}/ws/events`)
```

When a WebSocket event includes `leaderboards`, the page re-renders the active competition from the payload.

Fallback polling:

- Refresh every 15 seconds.
- Countdown text updates every 1 second.

Displayed timing:

- Phase 1 tabs show `Next snapshot in M:SS · Last updated HH:MM:SS`.
- Final shows only last updated time.

## Browser Leaderboard Implementation Style

The browser page is intentionally simple:

- No bundler
- No framework
- Inline CSS
- Inline JavaScript
- Full table HTML is replaced via `rows.innerHTML`
- HTML escaping is handled manually with `escapeHtml(...)`

Current tradeoffs:

- Good: easy to deploy as FastAPI static HTML.
- Good: no frontend build step.
- Weak: no component boundaries.
- Weak: visual design is not shared with replay except by duplicated color values.
- Weak: row rendering is string-template based.
- Weak: there is no dedicated empty/error/loading component model.

## Current Redesign Constraints

Before redesigning, keep these constraints in mind:

- Replay is a Pygame canvas UI, not HTML/CSS.
- Leaderboard is a browser HTML UI, not Pygame.
- The two UIs currently duplicate style values manually.
- Replay needs protected model payloads and an admin/replay token.
- Browser leaderboard must not expose weights or biases.
- Replay must support both Phase 1 dual-panel and Final single-map layouts.
- Replay should not update leaderboard mid-race; current behavior is safe-reveal at replay-cycle boundaries.
- Empty Easy/Hard panels remain visible, showing waiting state.
- Resizable replay must preserve 16:9 virtual-canvas alignment.

## Likely Redesign Touch Points

If redesigning UI, the main files are:

- `game_engine/frontend/replay_client.py`
  - layout rectangles
  - color constants
  - header/status bar
  - map panel rendering
  - leaderboard panel rendering
  - car labels and panel badges
- `server/static/leaderboard.html`
  - CSS theme
  - tab layout
  - leaderboard table rendering
  - countdown/status copy
- `server/storage.py`
  - if more leaderboard fields are needed
- `server/app.py`
  - if new display endpoints are needed

Good first refactor targets before a larger redesign:

- Extract replay layout rectangles into named constants.
- Extract replay theme colors and typography into one config block.
- Separate replay state-machine helpers from draw helpers.
- Define a shared display vocabulary for status labels, empty states, and result text.
- Decide whether browser leaderboard should remain table-based or become card/list-based.
