"""賺錢方式 (earning guide): a clickable, scrollable list of every way to earn
coins. Rows are built from config so the amounts shown always match the values
the game actually awards.

Blocking loop mirroring the other shop screens.
"""

from __future__ import annotations

import pygame

from game_engine.backend.settings import BLACK, CJK_FONT_PATH, FONT_PATH, WHITE
from game_engine.frontend.shop.config import (
    EASY_VALIDATION_MILESTONES,
    GENERATION_REWARD,
    HARD_VALIDATION_MILESTONES,
    RANDOM_VALIDATION_MILESTONES,
    TRAINING_FINISH_REWARD,
)
from game_engine.frontend.widgets import Button

# A row is either a section header ("section", text) or an earning entry
# (description, coin_reward).
_Row = tuple[str, object]


def _rows() -> list[_Row]:
    rows: list[_Row] = [("section", "重複可得（不限次數）")]
    rows.append(("完成一次 generation", GENERATION_REWARD))
    rows.append(("easy training 到達終點", TRAINING_FINISH_REWARD.get(1, 0)))
    rows.append(("hard training 到達終點", TRAINING_FINISH_REWARD.get(2, 0)))
    rows.append(("random training 到達終點", TRAINING_FINISH_REWARD.get(3, 0)))

    rows.append(("section", "首次達成（每項限一次）"))
    for label, milestones in (
        ("easy validation", EASY_VALIDATION_MILESTONES),
        ("hard validation", HARD_VALIDATION_MILESTONES),
        ("random validation", RANDOM_VALIDATION_MILESTONES),
    ):
        for _key, threshold, reward in milestones:
            rows.append((f"{label} {int(threshold)} 秒內完成", reward))
    return rows


def run_earn_guide_screen(screen: pygame.Surface) -> None:
    clock = pygame.time.Clock()
    font = _make_font(22)
    title_font = _make_font(34)
    section_font = _make_font(24)
    width, height = screen.get_size()

    rows = _rows()
    back_button = Button("返回", pygame.Rect(60, 40, 140, 48))

    top = 150
    line_h = 44
    list_left = 80
    coin_right = width - 120
    inv_top = 145
    scroll = 0

    while True:
        # Precompute total content height for scroll clamping.
        content_h = 0
        for kind, _ in rows:
            content_h += line_h if kind != "section" else line_h + 14
        viewport = pygame.Rect(0, inv_top, width, height - inv_top - 8)
        max_scroll = max(0, content_h - viewport.height)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return
            if event.type == pygame.MOUSEWHEEL:
                scroll -= event.y * 45
            if (
                event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 1
                and back_button.contains(event.pos)
            ):
                return

        scroll = max(0, min(scroll, max_scroll))
        back_button.update_hover(pygame.mouse.get_pos())

        screen.fill(BLACK)
        screen.blit(title_font.render("賺錢方式", True, WHITE), (230, 46))
        back_button.draw(screen, font)

        previous_clip = screen.get_clip()
        screen.set_clip(viewport)
        y = top - scroll
        for kind, value in rows:
            if kind == "section":
                y += 14
                screen.blit(section_font.render(str(value), True, (140, 200, 255)), (60, y))
                pygame.draw.line(
                    screen, (60, 70, 90), (60, y + line_h - 6), (width - 60, y + line_h - 6)
                )
            else:
                if viewport.top - line_h < y < viewport.bottom:
                    screen.blit(font.render(kind, True, WHITE), (list_left, y))
                    coin = font.render(f"+{value}", True, (255, 220, 120))
                    screen.blit(coin, (coin_right - coin.get_width(), y))
            y += line_h
        screen.set_clip(previous_clip)

        pygame.display.update()
        clock.tick(30)


def _make_font(size: int = 22) -> pygame.font.Font:
    path = CJK_FONT_PATH or str(FONT_PATH)
    return pygame.font.Font(path, size)
