# Repository Guidelines

## Project Structure & Module Organization

`game_engine/frontend/app.py` contains the main Pygame loop and training UI. Core simulation, geometry, assets, settings, and track generation live in `game_engine/backend/`. Genetic operators and fitness strategies live in `GA/`. Root entry points such as `main.py` and `mapGen.py` are thin launch scripts. Visual assets are stored in `Images/`, with car sprites in `Images/Sprites/`, track tiles in `Images/TracksMapGen/`, and playable/generated track images in `Images/Tracks/`.

## Build, Test, and Development Commands

Use `uv` for environment management and `rtk` as the shell wrapper used in this workspace.

```bash
uv sync
rtk uv run python main.py
rtk uv run python mapGen.py
rtk uv run pytest
rtk uv run ruff check .
rtk uv run mypy game_engine GA server shared
```

`uv sync` installs runtime and dev dependencies. `main.py` launches the simulator, and `mapGen.py` regenerates track assets. Run `pytest`, `ruff`, and `mypy` before opening a PR, especially when changing physics, neural-network inputs, or asset loading.

## Coding Style & Naming Conventions

Target Python 3.12 and follow PEP 8 with 4-space indentation. Use `snake_case` for functions, variables, and modules; use `UPPER_SNAKE_CASE` for constants in `game_engine/backend/settings.py`. Keep new game engine modules focused, and keep GA-specific algorithms in `GA/`. Match existing names when touching legacy methods such as `resetPosition()`, but prefer `snake_case` for new APIs.

## Testing Guidelines

There is no committed `tests/` directory yet, so add one for new behavior. Use `pytest` with files named `test_<module>.py`, and keep deterministic unit tests around geometry, genetic operators, and track generation. For gameplay changes, include at least one logic-level test and note any manual validation steps used in the simulator.

## Commit & Pull Request Guidelines

Recent history uses short, imperative commit messages such as `Setting env` and `seperate file`. Keep commits concise, present-tense, and scoped to one change; clearer examples would be `Refactor car collision checks` or `Add tests for track generator`. PRs should include a short summary, testing notes, linked issues if any, and screenshots or clips when UI, sprites, or track rendering change.

## Assets & Configuration Tips

Avoid hardcoding new asset paths outside `game_engine/backend/settings.py` or `game_engine/backend/assets.py`. Large generated images should only be updated when the underlying generation logic changes, and contributors should mention those regenerated files explicitly in the PR description.

