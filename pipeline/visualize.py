from __future__ import annotations

from html import escape
import math
from pathlib import Path
import queue
import shutil
import time
from typing import Any


def _polyline_points(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{point[0]:.2f},{point[1]:.2f}" for point in points)


def _car_angle(points: list[tuple[float, float]]) -> float:
    if len(points) < 2:
        return 0.0
    x1, y1 = points[-2]
    x2, y2 = points[-1]
    return math.degrees(math.atan2(y2 - y1, x2 - x1))


def _format_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


BEST_COLORS = ("#ffb703", "#fb5607", "#8338ec", "#06d6a0", "#f72585", "#3a86ff")


def _render_rank(render: dict[str, Any]) -> tuple[int, float, float, float]:
    metrics = render["metrics"]
    finish_time = metrics.get("finish_time")
    return (
        1 if metrics.get("finished_within_30s") else 0,
        -(finish_time if finish_time is not None else 999999.0),
        float(metrics.get("max_track_progress", 0.0)),
        -float(metrics.get("collision_count", 0.0)),
    )


def _map_key(title: str, render: dict[str, Any] | None) -> str:
    if not render:
        return title
    return f"{title}:{render['seed']}"


def _dashboard_image_href(map_image_path: str, dashboard_dir: Path) -> str:
    source = Path(map_image_path)
    if not source.exists():
        return source.as_posix()

    assets_dir = dashboard_dir / "dashboard_assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    asset_name = f"{source.parent.name}_{source.name}"
    target = assets_dir / asset_name
    if not target.exists() or target.stat().st_size != source.stat().st_size:
        shutil.copy2(source, target)
    return target.relative_to(dashboard_dir).as_posix()


def _render_game_view(
    title: str,
    render: dict[str, Any] | None,
    best_entry: dict[str, Any] | None = None,
    dashboard_dir: Path | None = None,
) -> str:
    if not render:
        return f"""
<div class="game-card">
  <div class="game-title">{escape(title)}</div>
  <div class="game-placeholder">Waiting for first rollout...</div>
</div>
"""

    width, height = render["canvas_size"]
    track_points = _polyline_points(render["track_polyline"])
    trajectory_points = _polyline_points(render["trajectory"])
    best_render = best_entry.get("render") if best_entry else None
    best_points = _polyline_points(best_render["trajectory"]) if best_render else ""
    best_color = best_entry.get("color", "#ffb703") if best_entry else "#ffb703"
    car_x, car_y = render["car_position"]
    angle = _car_angle(render["trajectory"])
    metrics = render["metrics"]
    start_x, start_y = render["track_polyline"][0]
    finish_x, finish_y = render["track_polyline"][-1]
    map_image_path = render.get("map_image_path")
    map_image = ""
    if map_image_path:
        path = Path(map_image_path)
        if dashboard_dir is not None:
            href = _dashboard_image_href(map_image_path, dashboard_dir)
        else:
            href = path.as_posix()
        map_image = (
            f'<image href="{escape(href)}" xlink:href="{escape(href)}" x="0" y="0" '
            f'width="{width}" height="{height}" preserveAspectRatio="xMidYMid meet" />'
        )
    simplified_track = "" if map_image else f"""
    <rect width="100%" height="100%" fill="#102016" />
    <rect width="100%" height="100%" fill="url(#grid-{escape(title).replace(" ", "-")})" />
    <polyline points="{track_points}" fill="none" stroke="#2f3338" stroke-width="{render["track_half_width"] * 2:.2f}" stroke-linecap="round" stroke-linejoin="round" />
    <polyline points="{track_points}" fill="none" stroke="#4b5058" stroke-width="{max(render["track_half_width"] * 1.55, 1):.2f}" stroke-linecap="round" stroke-linejoin="round" />
"""
    centerline = f"""
    <polyline points="{track_points}" fill="none" stroke="#ffffff" stroke-width="4" stroke-dasharray="12 14" stroke-linecap="round" stroke-linejoin="round" opacity="0.88" />
    <polyline points="{track_points}" fill="none" stroke="#111827" stroke-width="1.5" stroke-dasharray="12 14" stroke-linecap="round" stroke-linejoin="round" opacity="0.75" />
"""
    return f"""
<div class="game-card">
  <div class="game-title">{escape(title)} <span>seed {render["seed"]}</span></div>
  <svg viewBox="0 0 {width} {height}" class="game-screen" role="img" aria-label="{escape(title)} game view" xmlns:xlink="http://www.w3.org/1999/xlink">
    <defs>
      <pattern id="grid-{escape(title).replace(" ", "-")}" width="60" height="60" patternUnits="userSpaceOnUse">
        <path d="M 60 0 L 0 0 0 60" fill="none" stroke="rgba(255,255,255,0.045)" stroke-width="2" />
      </pattern>
    </defs>
    {map_image or simplified_track}
    {centerline}
    <circle cx="{start_x:.2f}" cy="{start_y:.2f}" r="14" fill="#38d97b" stroke="#0b1b12" stroke-width="4" />
    <circle cx="{finish_x:.2f}" cy="{finish_y:.2f}" r="14" fill="#ffd166" stroke="#261f0a" stroke-width="4" />
    {f'<polyline points="{best_points}" fill="none" stroke="{best_color}" stroke-width="8" stroke-linecap="round" stroke-linejoin="round" opacity="0.72" />' if best_points else ''}
    <polyline points="{trajectory_points}" fill="none" stroke="#32e6ff" stroke-width="6" stroke-linecap="round" stroke-linejoin="round" opacity="0.85" />
    <g transform="translate({car_x:.2f} {car_y:.2f}) rotate({angle:.2f})">
      <rect x="-15" y="-9" width="30" height="18" rx="3" fill="#ff4d5e" stroke="#ffffff" stroke-width="2" />
      <rect x="1" y="-6" width="10" height="12" rx="2" fill="#171a21" opacity="0.75" />
      <circle cx="-9" cy="-10" r="3" fill="#111" />
      <circle cx="-9" cy="10" r="3" fill="#111" />
      <circle cx="9" cy="-10" r="3" fill="#111" />
      <circle cx="9" cy="10" r="3" fill="#111" />
    </g>
  </svg>
  <div class="game-stats">
    <span>progress <strong>{metrics["max_track_progress"]:.3f}</strong></span>
    <span>finish <strong>{_format_value(metrics["finish_time"])}</strong></span>
    <span>crash <strong>{metrics["collision_count"]}</strong></span>
    {f'<span class="best-chip"><i style="background:{best_color}"></i>best <strong>{best_render["metrics"]["max_track_progress"]:.3f}</strong></span>' if best_render else ''}
  </div>
</div>
"""


def _with_best_map_renders(
    previous: dict[str, dict[str, Any]],
    message: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    best_map_renders = {key: dict(value) for key, value in previous.items()}
    candidates: list[tuple[str, dict[str, Any]]] = []

    train_render = message.get("train_render")
    if train_render:
        candidates.append(("Training map", train_render))

    validation_renders = message.get("validation_renders")
    if validation_renders is None:
        validation_render = message.get("validation_render", message.get("render"))
        validation_renders = [validation_render] if validation_render else []
    for render in validation_renders:
        if render:
            candidates.append((f"Validation map {render['seed']}", render))

    for title, render in candidates:
        key = _map_key(title, render)
        current = best_map_renders.get(key)
        if current is None:
            color = BEST_COLORS[len(best_map_renders) % len(BEST_COLORS)]
            best_map_renders[key] = {"render": render, "color": color}
        elif _render_rank(render) > _render_rank(current["render"]):
            best_map_renders[key] = {**current, "render": render}

    return best_map_renders


def _render_history_table(history: list[dict[str, Any]]) -> str:
    if not history:
        return ""
    rows = []
    for item in reversed(history):
        train = item.get("train_summary", {})
        validation = item.get("validation_summary", {})
        retry = "yes" if item.get("retry_scheduled") else ""
        rows.append(
            f"""
<tr>
  <td>{item.get("attempt", 1)}</td>
  <td>{item.get("generation", 0)}</td>
  <td>{_format_value(item.get("best_training_fitness", 0.0))}</td>
  <td>{_format_value(train.get("avg_max_track_progress", 0.0))}</td>
  <td>{_format_value(train.get("avg_collision_count", 0.0))}</td>
  <td>{_format_value(item.get("best_validation_fitness", 0.0))}</td>
  <td>{_format_value(validation.get("avg_max_track_progress", 0.0))}</td>
  <td>{validation.get("finish_count", 0)}</td>
  <td>{_format_value(validation.get("avg_collision_count", 0.0))}</td>
  <td>{retry}</td>
</tr>
"""
        )
    return f"""
<div class="history">
  <h3>Generation History</h3>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Attempt</th>
          <th>Gen</th>
          <th>Train fit</th>
          <th>Train prog</th>
          <th>Train crash</th>
          <th>Valid fit</th>
          <th>Valid prog</th>
          <th>Valid finish</th>
          <th>Valid crash</th>
          <th>Retry</th>
        </tr>
      </thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
  </div>
</div>
"""


def _render_strategy_panel(strategy: str, state: dict[str, Any], dashboard_dir: Path) -> str:
    if state.get("error"):
        return f"""
<section class="panel">
  <div class="header">
    <h2>{escape(strategy)}</h2>
    <div class="sub">Training process stopped with an error</div>
  </div>
  <pre class="error">{escape(state["error"])}</pre>
</section>
"""

    train_render = state.get("train_render")
    validation_renders = state.get("validation_renders")
    if validation_renders is None:
        validation_renders = [state.get("validation_render", state.get("render"))]
    validation_renders = [render for render in validation_renders if render]
    best_map_renders = state.get("best_map_renders", {})
    history_html = _render_history_table(state.get("history", []))
    metrics_html = ""
    validation_views = "\n".join(
        _render_game_view(
            f"Validation map {render['seed']}",
            render,
            best_map_renders.get(_map_key(f"Validation map {render['seed']}", render)),
            dashboard_dir,
        )
        for render in validation_renders
    )
    game_html = f"""
<div class="game-grid">
  {_render_game_view("Training map", train_render, best_map_renders.get(_map_key("Training map", train_render)), dashboard_dir)}
  {validation_views or _render_game_view("Validation map", None, dashboard_dir=dashboard_dir)}
</div>
"""
    if validation_renders:
        metrics_html = f"""
<div class="stats">
  <div>Validation-bred fitness: <strong>{state.get("best_breeding_fitness", state["best_training_fitness"]):.2f}</strong></div>
  <div>Train fitness: <strong>{state["best_training_fitness"]:.2f}</strong></div>
  <div>Validation fitness: <strong>{state.get("best_validation_fitness", 0.0):.2f}</strong></div>
  <div>Current round: <strong>{state["generation"]}/{state["completed_generations"]}</strong></div>
  <div>Seed attempt: <strong>{state.get("attempt", 1)}</strong></div>
  <div>Best validation gen: <strong>{state["best_validation_generation"]}</strong></div>
  <div>Validation progress: <strong>{state["validation_summary"]["avg_max_track_progress"]:.3f}</strong></div>
  <div>Validation finish time: <strong>{_format_value(state["validation_summary"]["avg_finish_time"])}</strong></div>
</div>
"""

    return f"""
<section class="panel">
  <div class="header">
    <h2>{escape(strategy)}</h2>
    <div class="sub">Current generation game view</div>
  </div>
  {game_html}
  {metrics_html}
  {history_html}
</section>
"""


def _write_dashboard(
    dashboard_path: Path,
    run_name: str,
    states: dict[str, dict[str, Any]],
    strategies: list[str],
    finished: int,
) -> None:
    dashboard_dir = dashboard_path.parent
    panels = "\n".join(_render_strategy_panel(strategy, states[strategy], dashboard_dir) for strategy in strategies)
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="1">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(run_name)} dashboard</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0f1115;
      --panel: #171a21;
      --text: #f2f4f8;
      --muted: #9aa4b2;
      --accent: #00dc78;
      --border: #242937;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 24px;
      background: radial-gradient(circle at top, #1a2230, var(--bg) 55%);
      color: var(--text);
      font: 14px/1.45 ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    .top {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: baseline;
      margin-bottom: 20px;
    }}
    h1 {{ margin: 0; font-size: 24px; }}
    .meta {{ color: var(--muted); }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
      gap: 18px;
    }}
    .panel {{
      background: linear-gradient(180deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01));
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 16px;
      box-shadow: 0 18px 40px rgba(0,0,0,0.25);
    }}
    .header h2 {{ margin: 0 0 4px; font-size: 18px; }}
    .sub {{ color: var(--muted); margin-bottom: 12px; }}
    .game-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
      gap: 14px;
    }}
    .game-card {{
      min-width: 0;
    }}
    .game-title {{
      display: flex;
      justify-content: space-between;
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 6px;
    }}
    .game-title span {{
      color: var(--accent);
    }}
    .game-screen {{
      width: 100%;
      aspect-ratio: 16 / 10;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: #102016;
      display: block;
    }}
    .game-placeholder {{
      display: grid;
      place-items: center;
      aspect-ratio: 16 / 10;
      border: 1px dashed var(--border);
      border-radius: 12px;
      color: var(--muted);
      background: #102016;
    }}
    .game-stats {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px 14px;
      color: var(--muted);
      font-size: 12px;
      margin-top: 6px;
    }}
    .game-stats strong {{
      color: var(--text);
    }}
    .best-chip {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }}
    .best-chip i {{
      display: inline-block;
      width: 9px;
      height: 9px;
      border-radius: 999px;
      box-shadow: 0 0 10px currentColor;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px 16px;
      margin-top: 12px;
    }}
    .history {{
      margin-top: 16px;
    }}
    .history h3 {{
      margin: 0 0 8px;
      font-size: 14px;
      color: var(--muted);
      font-weight: 600;
    }}
    .table-wrap {{
      overflow-x: auto;
      border: 1px solid var(--border);
      border-radius: 12px;
    }}
    table {{
      width: 100%;
      min-width: 820px;
      border-collapse: collapse;
      font-size: 12px;
    }}
    th, td {{
      padding: 7px 8px;
      border-bottom: 1px solid var(--border);
      text-align: right;
      white-space: nowrap;
    }}
    th {{
      color: var(--muted);
      font-weight: 600;
      background: rgba(255,255,255,0.03);
    }}
    th:first-child, td:first-child {{
      text-align: left;
    }}
    tbody tr:last-child td {{
      border-bottom: 0;
    }}
    .placeholder {{
      display: grid;
      place-items: center;
      min-height: 240px;
      border: 1px dashed var(--border);
      border-radius: 12px;
      color: var(--muted);
    }}
    .error {{
      white-space: pre-wrap;
      color: #ffb4b4;
      background: rgba(255, 90, 90, 0.12);
      border: 1px solid rgba(255, 90, 90, 0.35);
      border-radius: 12px;
      padding: 12px;
      overflow: auto;
    }}
  </style>
</head>
<body>
  <div class="top">
    <div>
      <h1>{escape(run_name)} training dashboard</h1>
      <div class="meta">Panels update every generation. Refresh is automatic while training is running.</div>
    </div>
    <div class="meta">Completed strategies: {finished}/{len(strategies)}</div>
  </div>
  <div class="grid">
    {panels}
  </div>
</body>
</html>
"""
    dashboard_path.write_text(html, encoding="utf-8")


def run_dashboard(
    run_name: str,
    dashboard_path: Path,
    strategies: list[str],
    progress_queue: Any,
    processes: list[Any],
) -> list[dict[str, Any]]:
    states: dict[str, dict[str, Any]] = {
        strategy: {
            "generation": 0,
            "attempt": 1,
            "completed_generations": 0,
            "render": None,
            "validation_summary": {"avg_max_track_progress": 0.0, "avg_finish_time": None},
            "best_training_fitness": 0.0,
            "best_validation_generation": 0,
            "history": [],
            "best_map_renders": {},
        }
        for strategy in strategies
    }
    results: list[dict[str, Any]] = []
    finished = 0
    stopped: set[str] = set()

    _write_dashboard(dashboard_path, run_name, states, strategies, finished)

    while True:
        drained = False
        while True:
            try:
                message = progress_queue.get_nowait()
            except queue.Empty:
                break
            drained = True
            if message["type"] == "progress":
                strategy = message["strategy_name"]
                history = states[strategy].get("history", [])
                best_map_renders = _with_best_map_renders(
                    states[strategy].get("best_map_renders", {}),
                    message,
                )
                states[strategy] = {
                    **message,
                    "best_map_renders": best_map_renders,
                    "history": [
                        *history,
                        {
                            "attempt": message.get("attempt", 1),
                            "generation": message.get("generation", 0),
                            "best_training_fitness": message.get("best_training_fitness", 0.0),
                            "best_validation_fitness": message.get("best_validation_fitness", 0.0),
                            "train_summary": message.get("train_summary", {}),
                            "validation_summary": message.get("validation_summary", {}),
                            "retry_scheduled": message.get("retry_scheduled", False),
                        },
                    ],
                }
            elif message["type"] == "result":
                results.append(message["result"])
                finished += 1
                stopped.add(message["result"]["strategy_name"])
            elif message["type"] == "error":
                states[message["strategy_name"]] = {
                    **states[message["strategy_name"]],
                    "error": message["error"],
                    "traceback": message.get("traceback", ""),
                }
                stopped.add(message["strategy_name"])
                finished += 1

        if drained:
            _write_dashboard(dashboard_path, run_name, states, strategies, finished)

        if not any(process.is_alive() for process in processes) and len(stopped) < len(strategies):
            for strategy in strategies:
                if strategy in stopped:
                    continue
                states[strategy] = {
                    **states[strategy],
                    "error": "Process stopped before reporting a result.",
                }
                stopped.add(strategy)
                finished += 1
            _write_dashboard(dashboard_path, run_name, states, strategies, finished)

        if (
            (finished >= len(strategies) or not any(process.is_alive() for process in processes))
            and len(stopped) >= len(strategies)
        ):
            break
        time.sleep(0.25)

    _write_dashboard(dashboard_path, run_name, states, strategies, finished)
    results.sort(key=lambda item: item["strategy_name"])
    return results
