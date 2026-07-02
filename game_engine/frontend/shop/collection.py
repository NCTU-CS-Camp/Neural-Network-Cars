"""Skin 圖鑑 (collection): one tier per row, rarest tier at the top. Owned skins
show their art; not-yet-owned ones show a locked silhouette that unlocks on
obtain.

Blocking loop mirroring the other shop screens.
"""

from __future__ import annotations

import pygame

from game_engine.backend.settings import BLACK, CJK_FONT_PATH, FONT_PATH, WHITE
from game_engine.frontend.shop import catalog, store
from game_engine.frontend.shop.config import TIERS
from game_engine.frontend.shop.renderer import surfaces_for
from game_engine.frontend.widgets import Button

# One row per tier, high to low, with the free starter car last.
_TIER_ROWS: tuple[str, ...] = (*TIERS, "DEFAULT")

# Short row labels; "DEFAULT" is too wide for the label column, so show 原廠.
_TIER_LABELS: dict[str, str] = {"DEFAULT": "原廠"}


def _font(size: int = 22) -> pygame.font.Font:
    path = CJK_FONT_PATH or str(FONT_PATH)
    return pygame.font.Font(path, size)


def _fit_label(font: pygame.font.Font, text: str, max_width: int) -> str:
    """Trim text with an ellipsis so a long name can't overflow its cell."""
    if font.size(text)[0] <= max_width:
        return text
    while text and font.size(text + "…")[0] > max_width:
        text = text[:-1]
    return text + "…"


def run_collection_screen(screen: pygame.Surface) -> None:
    clock = pygame.time.Clock()
    font = _font(22)
    title_font = _font(34)
    tier_font = _font(24)
    small_font = _font(16)
    big_q_font = _font(40)
    width, height = screen.get_size()

    identity = store.active_identity()
    owned: set[int] = set()
    if identity is not None:
        owned = set(store.load_entry(identity)["owned_skins"])

    all_skins = catalog.all_skins()
    back_button = Button("返回", pygame.Rect(60, 40, 140, 48))

    cell = 96
    gap = 16
    grid_x = 60
    label_w = 64
    grid_y = 150
    row_pitch = cell + gap + 20
    inv_top = 145

    scroll = 0
    while True:
        viewport = pygame.Rect(0, inv_top, width, height - inv_top - 8)
        content_h = len(_TIER_ROWS) * row_pitch + (grid_y - inv_top)
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
        screen.blit(title_font.render("車子圖鑑", True, WHITE), (230, 46))
        collected = sum(1 for s in all_skins if s.id in owned)
        screen.blit(
            font.render(f"已收集 {collected} / {len(all_skins)}", True, (255, 220, 120)),
            (width - 320, 54),
        )
        back_button.draw(screen, font)

        previous_clip = screen.get_clip()
        screen.set_clip(viewport)
        for row, tier in enumerate(_TIER_ROWS):
            row_y = grid_y + row * row_pitch - scroll
            if row_y + cell < viewport.top or row_y > viewport.bottom:
                continue
            tier_color = catalog.TIER_COLORS.get(tier, WHITE)
            label = tier_font.render(_TIER_LABELS.get(tier, tier), True, tier_color)
            screen.blit(label, (grid_x, row_y + cell // 2 - label.get_height() // 2))

            for col, skin in enumerate(catalog.skins_by_tier(tier)):
                rect = pygame.Rect(
                    grid_x + label_w + col * (cell + gap), row_y, cell, cell
                )
                is_owned = skin.id in owned
                inner = rect.inflate(-16, -16)
                if is_owned:
                    sprite = surfaces_for(skin.id)["display"]
                    sprite = pygame.transform.smoothscale(sprite, (inner.width, inner.height))
                    screen.blit(sprite, inner.topleft)
                    name = skin.name
                    name_color = WHITE
                else:
                    pygame.draw.rect(screen, (28, 28, 34), inner, border_radius=6)
                    q = big_q_font.render("?", True, (90, 90, 100))
                    screen.blit(q, q.get_rect(center=inner.center))
                    name = "???"
                    name_color = (120, 120, 130)

                pygame.draw.rect(screen, WHITE, rect, 2, border_radius=6)
                label = _fit_label(small_font, name, rect.width + 14)
                screen.blit(
                    small_font.render(label, True, name_color), (rect.x, rect.bottom + 2)
                )
        screen.set_clip(previous_clip)

        pygame.display.update()
        clock.tick(30)
