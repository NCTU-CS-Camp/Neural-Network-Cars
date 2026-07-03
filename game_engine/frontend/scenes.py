from __future__ import annotations

from dataclasses import dataclass, field

import pygame

from game_engine.frontend.widgets import Label
from shared.contracts import RuntimeSettings


@dataclass
class Scene:
    name: str
    title: str
    subtitle: str
    labels: list[Label] = field(default_factory=list)

    def render_overlay(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        title = font.render(self.title, True, (255, 255, 255))
        subtitle = font.render(self.subtitle, True, (200, 200, 200))
        surface.blit(title, (20, 20))
        surface.blit(subtitle, (20, 48))
        for label in self.labels:
            label.draw(surface, font)


def build_default_scenes(settings: RuntimeSettings) -> dict[str, Scene]:
    common_labels = [
        Label(
            f"使用者：{settings.username}  組別：{settings.group_id}",
            (20, 76),
        ),
    ]
    return {
        "home": Scene(
            name="home",
            title="神經網路賽車",
            subtitle="賽車訓練與測試主畫面。",
            labels=common_labels,
        ),
        "settings": Scene(
            name="settings",
            title="設定",
            subtitle="調整遊戲設定與使用者資料。",
            labels=common_labels,
        ),
        "training": Scene(
            name="training",
            title="訓練",
            subtitle="查看目前的模擬與訓練進度。",
            labels=common_labels,
        ),
        "replay": Scene(
            name="replay",
            title="重播",
            subtitle="查看本機評測與伺服器重播。",
            labels=common_labels,
        ),
    }


@dataclass
class AppShell:
    settings: RuntimeSettings
    current_scene_name: str = "training"
    scenes: dict[str, Scene] = field(init=False)

    def __post_init__(self) -> None:
        self.scenes = build_default_scenes(self.settings)

    @property
    def current_scene(self) -> Scene:
        return self.scenes[self.current_scene_name]

    def set_scene(self, scene_name: str) -> None:
        if scene_name in self.scenes:
            self.current_scene_name = scene_name
