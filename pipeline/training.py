from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import csv
from dataclasses import asdict
import json
import multiprocessing as mp
from pathlib import Path
import random
import subprocess
import traceback
from typing import Any

import numpy as np

from .config import ExperimentConfig, StrategyConfig
from .export import export_network_model
from .fitness import build_strategy
from .nn import NeuralNetwork, mutate, uniform_crossover
from .paths import resolve_project_path
from .simulator import Simulator
from .storage import append_jsonl, ensure_dir, save_model, utc_timestamp, write_json
from .track import MapRef, load_track_ref


DEFAULT_GROUP_ID = "1"
DEFAULT_USERNAME = "player1"


def _rank_key(validation_summary: dict[str, Any]) -> tuple[int, float, float]:
    finish_count = int(validation_summary["finish_count"])
    avg_finish_time = validation_summary["avg_finish_time"]
    finish_time_score = -(avg_finish_time if avg_finish_time is not None else 999999.0)
    return finish_count, finish_time_score, validation_summary["avg_max_track_progress"]


def _best_client_episode(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    return max(
        episodes,
        key=lambda item: (
            item.get("finish_time") is not None,
            -(item.get("finish_time") if item.get("finish_time") is not None else 999999.0),
            float(item.get("max_track_progress", 0.0)),
        ),
    )


def _client_result_from_validation(
    validation_summary: dict[str, Any],
    fps: int,
) -> dict[str, Any]:
    episodes = validation_summary.get("episodes", [])
    if not episodes:
        return {
            "completed": False,
            "lap_ticks": None,
            "max_progress": 0.0,
            "ticks_to_max_progress": 0,
        }
    episode = _best_client_episode(episodes)
    finish_time = episode.get("finish_time")
    max_progress = episode.get("max_track_progress_distance")
    if max_progress is None:
        max_progress = episode.get("max_track_progress", 0.0)
    return {
        "completed": finish_time is not None,
        "lap_ticks": round(float(finish_time) * fps) if finish_time is not None else None,
        "max_progress": float(max_progress),
        "ticks_to_max_progress": int(episode.get("ticks_to_max_progress", episode.get("frames", 0))),
    }


def _stable_strategy_seed(master_seed: int, strategy_name: str) -> int:
    return master_seed + sum(ord(char) for char in strategy_name)


def _evaluate_network(
    network: NeuralNetwork,
    track_refs: list[MapRef],
    strategy_config: StrategyConfig,
    config: ExperimentConfig,
    stop_on_finish: bool = True,
) -> tuple[float, dict[str, float], list[dict[str, Any]]]:
    strategy = build_strategy(strategy_config.strategy, strategy_config.params)
    episode_metrics: list[dict[str, Any]] = []
    training_fitness: list[float] = []
    finish_times: list[float] = []
    progresses: list[float] = []
    collisions: list[int] = []
    stalls: list[float] = []
    spins: list[float] = []
    wrong_ways: list[float] = []
    reverse_distances: list[float] = []

    for track_ref in track_refs:
        resolved_ref = resolve_project_path(track_ref) if not isinstance(track_ref, int) else track_ref
        track = load_track_ref(
            resolved_ref,
            cell_size=config.track_cell_size,
            half_width=config.track_half_width,
        )
        simulator = Simulator(track=track, fps=config.fps, time_limit_seconds=config.time_limit_seconds)
        result = simulator.run_episode(network, strategy, stop_on_finish=stop_on_finish)
        metrics = asdict(result.metrics)
        metrics["seed"] = track.seed
        episode_metrics.append(metrics)
        training_fitness.append(result.metrics.training_fitness)
        progresses.append(result.metrics.max_track_progress)
        collisions.append(result.metrics.collision_count)
        stalls.append(result.metrics.stall_time)
        spins.append(result.metrics.spin_time)
        wrong_ways.append(result.metrics.wrong_way_time)
        reverse_distances.append(result.metrics.reverse_progress_distance)
        if result.metrics.finish_time is not None:
            finish_times.append(result.metrics.finish_time)

    summary = {
        "avg_training_fitness": float(np.mean(training_fitness)),
        "avg_finish_time": float(np.mean(finish_times)) if finish_times else None,
        "avg_max_track_progress": float(np.mean(progresses)),
        "avg_collision_count": float(np.mean(collisions)),
        "avg_stall_time": float(np.mean(stalls)),
        "avg_spin_time": float(np.mean(spins)),
        "avg_wrong_way_time": float(np.mean(wrong_ways)),
        "avg_reverse_progress_distance": float(np.mean(reverse_distances)),
        "finish_count": int(sum(1 for item in episode_metrics if item["finished_within_30s"])),
    }
    return summary["avg_training_fitness"], summary, episode_metrics


def _evaluate_network_job(
    args: tuple[NeuralNetwork, list[MapRef], StrategyConfig, ExperimentConfig, bool],
) -> tuple[float, dict[str, float], list[dict[str, Any]]]:
    network, track_refs, strategy_config, config, stop_on_finish = args
    return _evaluate_network(
        network=network,
        track_refs=track_refs,
        strategy_config=strategy_config,
        config=config,
        stop_on_finish=stop_on_finish,
    )


def _evaluate_population(
    networks: list[NeuralNetwork],
    track_refs: list[MapRef],
    strategy_config: StrategyConfig,
    config: ExperimentConfig,
    stop_on_finish: bool = True,
) -> list[tuple[NeuralNetwork, float, dict[str, float], list[dict[str, Any]]]]:
    if config.population_workers <= 1 or len(networks) <= 1:
        results = [
            _evaluate_network(
                network=network,
                track_refs=track_refs,
                strategy_config=strategy_config,
                config=config,
                stop_on_finish=stop_on_finish,
            )
            for network in networks
        ]
    else:
        max_workers = min(config.population_workers, len(networks))
        jobs = [(network, track_refs, strategy_config, config, stop_on_finish) for network in networks]
        with ProcessPoolExecutor(max_workers=max_workers) as pool:
            results = list(pool.map(_evaluate_network_job, jobs))

    return [
        (network, score, summary, episodes)
        for network, (score, summary, episodes) in zip(networks, results)
    ]


def _render_payload(
    network: NeuralNetwork,
    strategy_config: StrategyConfig,
    track_ref: MapRef,
    config: ExperimentConfig,
    stop_on_finish: bool = True,
) -> dict[str, Any]:
    resolved_ref = resolve_project_path(track_ref) if not isinstance(track_ref, int) else track_ref
    track = load_track_ref(
        resolved_ref,
        cell_size=config.track_cell_size,
        half_width=config.track_half_width,
    )
    simulator = Simulator(track=track, fps=config.fps, time_limit_seconds=config.time_limit_seconds)
    result = simulator.run_episode(
        network,
        build_strategy(strategy_config.strategy, strategy_config.params),
        stop_on_finish=stop_on_finish,
    )
    stride = max(1, len(result.trajectory) // 200)
    map_image_path = None
    if not isinstance(resolved_ref, int):
        image_path = resolved_ref.with_suffix(".png")
        if image_path.exists():
            map_image_path = str(image_path)
    return {
        "seed": track.seed,
        "track_polyline": track.polyline,
        "canvas_size": track.canvas_size,
        "track_half_width": track.half_width,
        "map_image_path": map_image_path,
        "trajectory": result.trajectory[::stride] or result.trajectory,
        "car_position": result.trajectory[-1],
        "metrics": asdict(result.metrics),
    }


def _breed_next_generation(
    scored_population: list[tuple[NeuralNetwork, float, dict[str, Any]]],
    population_size: int,
    mutation_rate: int,
    rng: random.Random,
) -> tuple[list[NeuralNetwork], tuple[NeuralNetwork, NeuralNetwork]]:
    sorted_population = sorted(scored_population, key=lambda item: item[1], reverse=True)
    parent_a = sorted_population[0][0].clone()
    parent_b = sorted_population[1][0].clone()
    next_population = [parent_a.clone(), parent_b.clone()]

    while len(next_population) < population_size:
        child_a, child_b = uniform_crossover(parent_a, parent_b)
        mutate(child_a, mutation_rate, rng)
        mutate(child_b, mutation_rate, rng)
        next_population.append(child_a)
        if len(next_population) < population_size:
            next_population.append(child_b)

    return next_population, (parent_a, parent_b)


def _filter_maps_by_difficulty(
    refs: list[MapRef],
    difficulty: str,
    label: str,
) -> list[MapRef]:
    if difficulty == "all" or not refs or isinstance(refs[0], int):
        return refs
    if difficulty not in {"easy", "hard"}:
        raise ValueError("map_difficulty must be one of: easy, hard, all")

    marker = f"_{difficulty}"
    selected = [
        ref
        for ref in refs
        if marker in Path(str(ref)).stem
    ]
    if not selected:
        raise ValueError(f"No {label} map matched map_difficulty={difficulty!r}")
    return selected


def _train_strategy(
    strategy_config: StrategyConfig,
    config: ExperimentConfig,
    run_dir: Path,
    progress_queue: mp.Queue | None = None,
) -> dict[str, Any]:
    train_track_refs = _filter_maps_by_difficulty(
        list(config.train_maps or config.train_seeds),
        config.map_difficulty,
        "training",
    )
    validation_track_refs = _filter_maps_by_difficulty(
        list(config.validation_maps or config.validation_seeds),
        config.map_difficulty,
        "validation",
    )
    strategy_dir = ensure_dir(run_dir / "strategies" / strategy_config.name)
    base_strategy_seed = _stable_strategy_seed(config.master_seed, strategy_config.name)
    train_log_path = strategy_dir / "train_log.jsonl"
    best_model: NeuralNetwork | None = None
    best_validation_summary: dict[str, Any] | None = None
    best_metadata: dict[str, Any] | None = None
    best_rank: tuple[int, float, float] | None = None
    best_training_parent_models: tuple[NeuralNetwork, NeuralNetwork] | None = None
    best_training_parent_metadata: dict[str, Any] | None = None
    best_training_parent_summary: dict[str, Any] | None = None
    best_training_parent_score: float | None = None
    attempt_seeds: list[int] = []
    total_completed_generations = 0
    retry_triggered = False

    for attempt in range(1, config.max_seed_retries + 2):
        evolution_seed = base_strategy_seed + (attempt - 1)
        attempt_seeds.append(evolution_seed)
        rng = np.random.default_rng(evolution_seed)
        py_rng = random.Random(evolution_seed)
        population = [
            NeuralNetwork.random(config.architecture, rng)
            for _ in range(config.population_size)
        ]
        attempt_best_completion_rate = 0.0
        attempt_best_avg_max_track_progress = 0.0
        retry_this_attempt = False

        for generation in range(1, config.generations + 1):
            scored_population: list[tuple[NeuralNetwork, float, dict[str, Any], list[dict[str, Any]]]] = [
                (network, train_score, train_summary, train_episodes)
                for network, train_score, train_summary, train_episodes in _evaluate_population(
                    networks=population,
                    track_refs=train_track_refs,
                    strategy_config=strategy_config,
                    config=config,
                    stop_on_finish=False,
                )
            ]

            scored_population.sort(key=lambda item: item[1], reverse=True)
            best_train_network = scored_population[0][0].clone()
            if best_training_parent_score is None or scored_population[0][1] > best_training_parent_score:
                best_training_parent_score = scored_population[0][1]
                best_training_parent_models = (
                    scored_population[0][0].clone(),
                    scored_population[1][0].clone(),
                )
                best_training_parent_summary = {
                    "parent_1_score": scored_population[0][1],
                    "parent_1_summary": scored_population[0][2],
                    "parent_1_episodes": scored_population[0][3],
                    "parent_2_score": scored_population[1][1],
                    "parent_2_summary": scored_population[1][2],
                    "parent_2_episodes": scored_population[1][3],
                }
                best_training_parent_metadata = {
                    "strategy_name": strategy_config.name,
                    "strategy": strategy_config.strategy,
                    "strategy_params": strategy_config.params,
                    "architecture": config.architecture,
                    "generation": generation,
                    "attempt": attempt,
                    "evolution_seed": evolution_seed,
                    "selection": "top_2_by_training_maps",
                    "train_seeds": config.train_seeds,
                    "validation_seeds": config.validation_seeds,
                    "train_maps": config.train_maps,
                    "validation_maps": config.validation_maps,
                    "map_difficulty": config.map_difficulty,
                    "mutation_rate": config.mutation_rate,
                    "time_limit_seconds": config.time_limit_seconds,
                    "fps": config.fps,
                    "track_cell_size": config.track_cell_size,
                    "track_half_width": config.track_half_width,
                    "model_architecture_version": "v1",
                }
            next_population, parents = _breed_next_generation(
                scored_population=scored_population,
                population_size=config.population_size,
                mutation_rate=config.mutation_rate,
                rng=py_rng,
            )
            validation_population, parents = _breed_next_generation(
                scored_population=scored_population,
                population_size=config.population_size,
                mutation_rate=config.mutation_rate,
                rng=py_rng,
            )
            validation_candidates: list[
                tuple[NeuralNetwork, float, dict[str, Any], list[dict[str, Any]]]
            ] = [
                (candidate, validation_score, candidate_summary, candidate_episodes)
                for candidate, validation_score, candidate_summary, candidate_episodes in _evaluate_population(
                    networks=validation_population,
                    track_refs=validation_track_refs,
                    strategy_config=strategy_config,
                    config=config,
                )
            ]

            best_validation_candidate = max(
                validation_candidates,
                key=lambda item: (_rank_key(item[2]), item[1]),
            )
            best_validation_network = best_validation_candidate[0].clone()
            best_validation_fitness = best_validation_candidate[1]
            validation_summary = best_validation_candidate[2]
            validation_episodes = best_validation_candidate[3]
            total_completed_generations += 1
            completion_rate = validation_summary["finish_count"] / len(validation_track_refs)
            attempt_best_completion_rate = max(attempt_best_completion_rate, completion_rate)
            attempt_best_avg_max_track_progress = max(
                attempt_best_avg_max_track_progress,
                float(validation_summary["avg_max_track_progress"]),
            )
            current_rank = _rank_key(validation_summary)
            if best_rank is None or current_rank > best_rank:
                best_rank = current_rank
                best_model = best_validation_network.clone()
                best_validation_summary = {
                    **validation_summary,
                    "episodes": validation_episodes,
                    "attempt": attempt,
                    "evolution_seed": evolution_seed,
                    "validation_breed_population_size": len(validation_population),
                }
                best_metadata = {
                    "strategy_name": strategy_config.name,
                    "strategy": strategy_config.strategy,
                    "strategy_params": strategy_config.params,
                    "architecture": config.architecture,
                    "generation": generation,
                    "attempt": attempt,
                    "evolution_seed": evolution_seed,
                    "train_seeds": config.train_seeds,
                    "validation_seeds": config.validation_seeds,
                    "train_maps": config.train_maps,
                    "validation_maps": config.validation_maps,
                    "mutation_rate": config.mutation_rate,
                    "time_limit_seconds": config.time_limit_seconds,
                    "fps": config.fps,
                    "track_cell_size": config.track_cell_size,
                    "track_half_width": config.track_half_width,
                    "model_architecture_version": "v1",
                }

            if (
                generation == config.retry_generation
                and attempt_best_avg_max_track_progress < config.retry_min_avg_max_track_progress
                and attempt <= config.max_seed_retries
            ):
                retry_this_attempt = True
                retry_triggered = True

            append_jsonl(
                train_log_path,
                {
                    "attempt": attempt,
                    "evolution_seed": evolution_seed,
                    "generation": generation,
                    "strategy_name": strategy_config.name,
                    "best_training_fitness": scored_population[0][1],
                    "best_validation_fitness": best_validation_fitness,
                    "validation_breed_population_size": len(validation_population),
                    "validation_breed_adopted": False,
                    "completion_rate": completion_rate,
                    "attempt_best_completion_rate": attempt_best_completion_rate,
                    "attempt_best_avg_max_track_progress": attempt_best_avg_max_track_progress,
                    "retry_scheduled": retry_this_attempt,
                    "parent_selection": "top_2_by_training; validation_breed_is_probe_only",
                    "train_summary": scored_population[0][2],
                    "train_episodes": scored_population[0][3],
                    "validation_summary": validation_summary,
                    "validation_episodes": validation_episodes,
                },
            )
            if progress_queue is not None:
                progress_queue.put(
                    {
                        "type": "progress",
                        "strategy_name": strategy_config.name,
                        "attempt": attempt,
                        "evolution_seed": evolution_seed,
                        "generation": generation,
                        "completed_generations": config.generations,
                        "best_training_fitness": scored_population[0][1],
                        "best_validation_fitness": best_validation_fitness,
                        "best_breeding_fitness": best_validation_fitness,
                        "validation_breed_population_size": len(validation_population),
                        "validation_breed_adopted": False,
                        "best_validation_generation": (
                            best_metadata["generation"] if best_metadata else generation
                        ),
                        "train_summary": scored_population[0][2],
                        "validation_summary": validation_summary,
                        "retry_scheduled": retry_this_attempt,
                        "train_render": _render_payload(
                            network=best_train_network,
                            strategy_config=strategy_config,
                            track_ref=train_track_refs[0],
                            config=config,
                            stop_on_finish=False,
                        ),
                        "validation_render": _render_payload(
                            network=best_validation_network,
                            strategy_config=strategy_config,
                            track_ref=validation_track_refs[0],
                            config=config,
                        ),
                        "validation_renders": [
                            _render_payload(
                                network=best_validation_network,
                                strategy_config=strategy_config,
                                track_ref=track_ref,
                                config=config,
                            )
                            for track_ref in validation_track_refs
                        ],
                        "render": _render_payload(
                            network=best_validation_network,
                            strategy_config=strategy_config,
                            track_ref=validation_track_refs[0],
                            config=config,
                        ),
                    }
                )
            if retry_this_attempt:
                break

            population = next_population

        if not retry_this_attempt:
            break

    if (
        best_model is None
        or best_validation_summary is None
        or best_metadata is None
        or best_training_parent_models is None
        or best_training_parent_metadata is None
        or best_training_parent_summary is None
    ):
        raise RuntimeError(f"No model produced for strategy {strategy_config.name}")

    parent_1_path = strategy_dir / "best_training_parent_1.npz"
    parent_2_path = strategy_dir / "best_training_parent_2.npz"
    parent_1_metadata = {**best_training_parent_metadata, "parent_rank": 1}
    parent_2_metadata = {**best_training_parent_metadata, "parent_rank": 2}
    save_model(parent_1_path, best_training_parent_models[0], parent_1_metadata)
    save_model(parent_2_path, best_training_parent_models[1], parent_2_metadata)
    save_model(strategy_dir / "best_model.npz", best_model, best_metadata)
    save_model(strategy_dir / "best_validation_model.npz", best_model, best_metadata)
    client_result = _client_result_from_validation(best_validation_summary, config.fps)
    best_car_path = strategy_dir / "best_car.json"
    write_json(
        best_car_path,
        export_network_model(
            best_model,
            group_id=DEFAULT_GROUP_ID,
            username=DEFAULT_USERNAME,
            client_result=client_result,
        ),
    )
    write_json(
        strategy_dir / "training_parents.json",
        {
            **best_training_parent_summary,
            "attempt": best_training_parent_metadata["attempt"],
            "generation": best_training_parent_metadata["generation"],
            "evolution_seed": best_training_parent_metadata["evolution_seed"],
            "parent_1_model_path": str(parent_1_path),
            "parent_2_model_path": str(parent_2_path),
        },
    )
    write_json(strategy_dir / "validation.json", best_validation_summary)
    result = {
        "strategy_name": strategy_config.name,
        "best_generation": best_metadata["generation"],
        "best_attempt": best_metadata["attempt"],
        "evolution_seed": best_metadata["evolution_seed"],
        "attempts_completed": len(attempt_seeds),
        "attempt_seeds": attempt_seeds,
        "retry_triggered": retry_triggered,
        "completed_generations": total_completed_generations,
        "best_validation": best_validation_summary,
        "best_training_parents": best_training_parent_summary,
        "best_model_path": str(strategy_dir / "best_model.npz"),
        "best_car_path": str(best_car_path),
        "client_result": client_result,
        "best_training_parent_1_path": str(parent_1_path),
        "best_training_parent_2_path": str(parent_2_path),
        "best_validation_model_path": str(strategy_dir / "best_validation_model.npz"),
    }
    if progress_queue is not None:
        progress_queue.put({"type": "result", "result": result})
    return result


def _train_strategy_worker(
    strategy_config: StrategyConfig,
    config: ExperimentConfig,
    run_dir: Path,
    progress_queue: mp.Queue,
) -> None:
    try:
        _train_strategy(
            strategy_config=strategy_config,
            config=config,
            run_dir=run_dir,
            progress_queue=progress_queue,
        )
    except Exception as exc:
        progress_queue.put(
            {
                "type": "error",
                "strategy_name": strategy_config.name,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }
        )


def _write_summary(run_dir: Path, run_id: str, results: list[dict[str, Any]]) -> None:
    write_json(run_dir / "summary.json", {"run_id": run_id, "strategies": results})
    with (run_dir / "summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "strategy_name",
                "best_generation",
                "best_attempt",
                "evolution_seed",
                "attempts_completed",
                "retry_triggered",
                "completed_generations",
                "validation_finish_count",
                "finished_within_30s_any_validation",
                "avg_finish_time",
                "avg_max_track_progress",
                "avg_collision_count",
                "avg_stall_time",
                "avg_spin_time",
                "best_model_path",
                "best_car_path",
                "best_training_parent_1_path",
                "best_training_parent_2_path",
                "best_validation_model_path",
            ],
        )
        writer.writeheader()
        for result in results:
            validation = result["best_validation"]
            writer.writerow(
                {
                    "strategy_name": result["strategy_name"],
                    "best_generation": result["best_generation"],
                    "best_attempt": result["best_attempt"],
                    "evolution_seed": result["evolution_seed"],
                    "attempts_completed": result["attempts_completed"],
                    "retry_triggered": result["retry_triggered"],
                    "completed_generations": result["completed_generations"],
                    "validation_finish_count": validation["finish_count"],
                    "finished_within_30s_any_validation": validation["finish_count"] > 0,
                    "avg_finish_time": validation["avg_finish_time"],
                    "avg_max_track_progress": validation["avg_max_track_progress"],
                    "avg_collision_count": validation["avg_collision_count"],
                    "avg_stall_time": validation["avg_stall_time"],
                    "avg_spin_time": validation["avg_spin_time"],
                    "best_model_path": result["best_model_path"],
                    "best_car_path": result.get("best_car_path"),
                    "best_training_parent_1_path": result.get("best_training_parent_1_path"),
                    "best_training_parent_2_path": result.get("best_training_parent_2_path"),
                    "best_validation_model_path": result.get("best_validation_model_path"),
                }
            )

    if results:
        best_result = max(results, key=lambda item: _rank_key(item["best_validation"]))
        best_car_path = best_result.get("best_car_path")
        if best_car_path:
            best_car = json.loads(Path(best_car_path).read_text(encoding="utf-8"))
            write_json(run_dir / "best_car.json", best_car)


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=resolve_project_path("."),
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except Exception:
        return "unknown"


def run_experiment(config: ExperimentConfig, render: bool = False) -> Path:
    run_id = f"{utc_timestamp()}_{config.run_name}"
    run_dir = ensure_dir(resolve_project_path(config.output_dir) / run_id)
    ensure_dir(run_dir / "strategies")
    manifest = {
        "run_id": run_id,
        "run_name": config.run_name,
        "git_commit": _git_commit(),
        "architecture": config.architecture,
        "population_size": config.population_size,
        "generations": config.generations,
        "mutation_rate": config.mutation_rate,
        "train_seeds": config.train_seeds,
        "validation_seeds": config.validation_seeds,
        "train_maps": config.train_maps,
        "validation_maps": config.validation_maps,
        "time_limit_seconds": config.time_limit_seconds,
        "fps": config.fps,
        "parallel_workers": config.parallel_workers,
        "population_workers": config.population_workers,
        "strategy_randomization": "master_seed plus stable strategy-name offset",
        "retry_generation": config.retry_generation,
        "retry_min_avg_max_track_progress": config.retry_min_avg_max_track_progress,
        "max_seed_retries": config.max_seed_retries,
        "seed_retry_behavior": "stop the current attempt at retry_generation when best validation avg_max_track_progress stays below threshold, then rerun with the next evolution seed",
        "strategies": [asdict(strategy) for strategy in config.strategies],
        "model_architecture_version": "v1",
        "parent_selection": "top_2_by_training; validation_breed_is_probe_only",
        "fitness_baseline": "score += velocity",
        "best_generation_meaning": "best by validation finish count, then finish time, then progress",
    }
    write_json(run_dir / "manifest.json", manifest)

    if render:
        print(f"Dashboard: {run_dir / 'dashboard.html'}", flush=True)
        from .visualize import run_dashboard

        ctx = mp.get_context("spawn")
        progress_queue: mp.Queue = ctx.Queue()
        processes = [
            ctx.Process(
                target=_train_strategy_worker,
                args=(strategy, config, run_dir, progress_queue),
            )
            for strategy in config.strategies
        ]
        for process in processes:
            process.start()
        try:
            results = run_dashboard(
                run_name=config.run_name,
                dashboard_path=run_dir / "dashboard.html",
                strategies=[strategy.name for strategy in config.strategies],
                progress_queue=progress_queue,
                processes=processes,
            )
        finally:
            for process in processes:
                process.join()
    elif config.parallel_workers > 1 and len(config.strategies) > 1:
        with ProcessPoolExecutor(max_workers=config.parallel_workers) as pool:
            futures = [
                pool.submit(_train_strategy, strategy, config, run_dir)
                for strategy in config.strategies
            ]
            results = [future.result() for future in futures]
    else:
        results = [_train_strategy(strategy, config, run_dir) for strategy in config.strategies]

    _write_summary(run_dir, run_id, results)
    return run_dir
