"""Gacha reveal animation: a full-screen, ceremonial reveal for pulled skins.

`play_reveal` runs its own blocking loop (like the other screens). Each pull is
revealed with a rarity-scaled build-up (glowing orb + rays), a white flash with
an expanding tier-colored ring, then the car art scales in with its name, tier,
and a NEW!/已擁有 badge. Rarer tiers get longer build-up, brighter flash, more
spark particles, and a short screen shake. A 10-pull reveals card-by-card
(click / space to advance, Skip to jump ahead) and ends on a summary grid with
the rarest pull emphasised.

Requires the pygame display to be initialised. Reuses renderer surfaces and the
catalog; it never touches coins, ownership, or draw odds (that already happened
in gacha before this runs).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import pygame

from game_engine.backend.settings import CJK_FONT_PATH, FONT_PATH, WHITE
from game_engine.frontend.shop import catalog, renderer
from game_engine.frontend.shop.gacha import PullResult
from game_engine.frontend.widgets import Button

_TIER_COLORS: dict[str, tuple[int, int, int]] = {
    "SSR": (255, 190, 70),
    "SR": (200, 130, 255),
    "S": (255, 120, 160),
    "A": (120, 200, 255),
    "B": (150, 210, 150),
    "C": (180, 180, 180),
    "DEFAULT": (230, 230, 230),
}

# Rarity order, best first — used to emphasise the rarest card in the summary.
_TIER_ORDER: list[str] = ["SSR", "SR", "S", "A", "B", "C", "DEFAULT"]

# Per-tier drama: (build_up_frames, flash_frames, particle_count, shake_frames)
# at 60 fps. Rarer = longer build-up, bigger burst, and a screen shake.
_DRAMA: dict[str, tuple[int, int, int, int]] = {
    "DEFAULT": (12, 6, 0, 0),
    "C": (16, 6, 8, 0),
    "B": (16, 6, 8, 0),
    "S": (28, 8, 22, 0),
    "A": (28, 8, 22, 0),
    "SR": (48, 12, 44, 8),
    "SSR": (56, 14, 64, 12),
}

_HERO_HEIGHT = 240


@dataclass
class _Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    color: tuple[int, int, int]


def _font(size: int) -> pygame.font.Font:
    path = CJK_FONT_PATH or str(FONT_PATH)
    return pygame.font.Font(path, size)


def _ease_out(t: float) -> float:
    return 1.0 - (1.0 - t) ** 3


def _hero_surface(skin_id: int) -> pygame.Surface:
    big = renderer.surfaces_for(skin_id)["big"]
    scale = _HERO_HEIGHT / big.get_height()
    size = (max(1, int(big.get_width() * scale)), max(1, int(big.get_height() * scale)))
    return pygame.transform.scale(big, size)


def _soft_circle(radius: int, color: tuple[int, int, int], alpha: int) -> pygame.Surface:
    surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    pygame.draw.circle(surface, (*color, alpha), (radius, radius), radius)
    return surface


def _reveal_one(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    result: PullResult,
    index: int,
    total: int,
) -> str:
    """Play one card's reveal. Returns "next" (advance) or "skip_all" (jump ahead)."""
    width, height = screen.get_size()
    cx, cy = width // 2, height // 2 - 30
    skin = catalog.get_skin(result.skin_id)
    color = _TIER_COLORS.get(result.tier, WHITE)
    buildup, flash_len, particle_count, shake_len = _DRAMA.get(result.tier, _DRAMA["C"])
    hero = _hero_surface(result.skin_id)

    name_font = _font(52)
    tier_font = _font(40)
    badge_font = _font(28)
    hint_font = _font(24)

    skip_button = Button("Skip ▶", pygame.Rect(width - 180, height - 80, 150, 50))

    particles: list[_Particle] = []
    phase = "buildup"
    frame = 0
    shake = 0
    ring = 0.0

    def burst() -> None:
        for _ in range(particle_count):
            angle = random.uniform(0.0, math.tau)
            speed = random.uniform(3.0, 11.0)
            particles.append(
                _Particle(cx, cy, math.cos(angle) * speed, math.sin(angle) * speed, 1.0, color)
            )

    def to_reveal() -> None:
        nonlocal phase, ring, shake
        if phase in ("buildup", "flash", "reveal_in"):
            if phase == "buildup":
                burst()
                shake = shake_len
                ring = 1.0
            phase = "hold"

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return "skip_all"
                if event.key in (pygame.K_SPACE, pygame.K_RETURN):
                    if phase == "hold":
                        return "next"
                    to_reveal()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if total > 1 and skip_button.contains(event.pos):
                    return "skip_all"
                if phase == "hold":
                    return "next"
                to_reveal()

        # advance state machine
        if phase == "buildup":
            frame += 1
            if frame >= buildup:
                phase, frame = "flash", 0
                burst()
                shake = shake_len
        elif phase == "flash":
            frame += 1
            ring += 26.0
            if frame >= flash_len:
                phase, frame = "reveal_in", 0
        elif phase == "reveal_in":
            frame += 1
            ring += 18.0
            if frame >= 14:
                phase, frame = "hold", 0

        for particle in particles:
            particle.x += particle.vx
            particle.y += particle.vy
            particle.vx *= 0.94
            particle.vy = particle.vy * 0.94 + 0.15
            particle.life -= 0.02
        particles[:] = [particle for particle in particles if particle.life > 0]
        if shake > 0:
            shake -= 1

        ox = random.randint(-shake, shake) if shake > 0 else 0
        oy = random.randint(-shake, shake) if shake > 0 else 0

        screen.fill((8, 8, 12))

        if phase == "buildup":
            progress = frame / max(1, buildup)
            base_r = int(30 + 130 * progress)
            pulse = int(10 * math.sin(frame * 0.5))
            for k in range(4):
                rr = base_r - k * 14 + pulse
                if rr > 0:
                    screen.blit(_soft_circle(rr, color, 55), (cx - rr + ox, cy - rr + oy))
            for k in range(8):
                angle = frame * 0.1 + k * math.tau / 8
                end = (cx + math.cos(angle) * (base_r + 40), cy + math.sin(angle) * (base_r + 40))
                pygame.draw.line(screen, color, (cx + ox, cy + oy), (end[0] + ox, end[1] + oy), 2)

        if phase in ("reveal_in", "hold"):
            for k in range(3):
                rr = 190 - k * 45
                screen.blit(_soft_circle(rr, color, 38), (cx - rr + ox, cy - rr + oy))

        if phase in ("flash", "reveal_in") and ring > 0:
            pygame.draw.circle(
                screen, color, (cx + ox, cy + oy), int(ring), max(1, 9 - frame // 2)
            )

        if phase in ("reveal_in", "hold"):
            reveal_t = 1.0 if phase == "hold" else _ease_out(frame / 14)
            scale = 0.4 + 0.6 * reveal_t
            hw, hh = hero.get_size()
            scaled = pygame.transform.scale(hero, (max(1, int(hw * scale)), max(1, int(hh * scale))))
            scaled.set_alpha(int(255 * reveal_t))
            screen.blit(scaled, scaled.get_rect(center=(cx + ox, cy + oy)))

        for particle in particles:
            alpha = max(0, min(255, int(255 * particle.life)))
            screen.blit(_soft_circle(3, particle.color, alpha), (particle.x - 3 + ox, particle.y - 3 + oy))

        if phase == "flash":
            overlay = pygame.Surface((width, height))
            overlay.fill((255, 255, 255))
            overlay.set_alpha(int(255 * (1 - frame / max(1, flash_len))))
            screen.blit(overlay, (0, 0))

        if phase == "hold":
            name_surface = name_font.render(skin.name, True, WHITE)
            screen.blit(name_surface, name_surface.get_rect(center=(cx, cy + 165)))
            tier_surface = tier_font.render(f"【{result.tier}】", True, color)
            screen.blit(tier_surface, tier_surface.get_rect(center=(cx, cy + 220)))
            badge_text, badge_color = (
                ("NEW!", (255, 215, 90)) if not result.duplicate else ("已擁有", (150, 150, 150))
            )
            badge_surface = badge_font.render(badge_text, True, badge_color)
            screen.blit(badge_surface, badge_surface.get_rect(center=(cx + 130, cy - 120)))
            hint = "點擊 / 空白鍵 繼續" if total == 1 else "點擊 / 空白鍵 下一張"
            hint_surface = hint_font.render(hint, True, (200, 200, 200))
            screen.blit(hint_surface, hint_surface.get_rect(center=(cx, height - 56)))

        if total > 1:
            progress_surface = hint_font.render(f"{index + 1} / {total}", True, (210, 210, 210))
            screen.blit(progress_surface, (44, 40))
            skip_button.update_hover(pygame.mouse.get_pos())
            skip_button.draw(screen, hint_font)

        pygame.display.update()
        clock.tick(60)


def _summary(screen: pygame.Surface, clock: pygame.time.Clock, results: list[PullResult]) -> None:
    width, height = screen.get_size()
    title_font = _font(40)
    label_font = _font(20)
    hint_font = _font(24)
    back_button = Button("返回商店", pygame.Rect(40, 40, 180, 48))

    rarest = min(
        range(len(results)),
        key=lambda i: _TIER_ORDER.index(results[i].tier) if results[i].tier in _TIER_ORDER else 99,
    )

    columns = 5
    cell = 150
    gap = 24
    grid_w = columns * cell + (columns - 1) * gap
    grid_x = (width - grid_w) // 2
    grid_y = 170

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                return

        back_button.update_hover(pygame.mouse.get_pos())

        screen.fill((10, 10, 14))
        title = title_font.render("本次抽卡結果", True, WHITE)
        screen.blit(title, title.get_rect(center=(width // 2, 90)))

        for i, result in enumerate(results):
            row, col = divmod(i, columns)
            rect = pygame.Rect(
                grid_x + col * (cell + gap), grid_y + row * (cell + gap + 30), cell, cell
            )
            color = _TIER_COLORS.get(result.tier, WHITE)
            emphasised = i == rarest
            border_color = (255, 215, 90) if emphasised else color
            pygame.draw.rect(screen, (24, 24, 30), rect, border_radius=8)
            pygame.draw.rect(screen, border_color, rect, 5 if emphasised else 3, border_radius=8)

            sprite = renderer.surfaces_for(result.skin_id)["big"]
            target_h = int(cell * 0.62)
            scale = target_h / sprite.get_height()
            sprite = pygame.transform.scale(
                sprite, (max(1, int(sprite.get_width() * scale)), target_h)
            )
            screen.blit(sprite, sprite.get_rect(center=(rect.centerx, rect.centery - 6)))

            skin = catalog.get_skin(result.skin_id)
            name_surface = label_font.render(skin.name, True, WHITE)
            screen.blit(name_surface, name_surface.get_rect(center=(rect.centerx, rect.bottom + 12)))
            tier_label = f"{result.tier}{' ★' if emphasised else ''}"
            tier_surface = label_font.render(tier_label, True, color)
            screen.blit(tier_surface, tier_surface.get_rect(center=(rect.centerx, rect.bottom + 34)))

        hint = hint_font.render("點擊任意處返回商店", True, (200, 200, 200))
        screen.blit(hint, hint.get_rect(center=(width // 2, height - 56)))
        back_button.draw(screen, hint_font)

        pygame.display.update()
        clock.tick(60)


def play_reveal(screen: pygame.Surface, results: list[PullResult]) -> None:
    """Reveal one (single pull) or several (10-pull) results with ceremony."""
    if not results:
        return
    clock = pygame.time.Clock()
    for index, result in enumerate(results):
        action = _reveal_one(screen, clock, result, index, len(results))
        if action == "skip_all":
            break
    if len(results) > 1:
        _summary(screen, clock, results)
