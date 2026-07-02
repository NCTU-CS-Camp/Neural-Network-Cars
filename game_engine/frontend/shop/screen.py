"""Shop scene: coin balance, gacha (single / 10-pull) that launches a full
reveal animation, and an inventory grid of owned skins that can be equipped.
Blocking loop mirroring the other screens in game_engine/frontend/screens.py.
"""

from __future__ import annotations

import random

import pygame

from game_engine.backend.settings import BLACK, CJK_FONT_PATH, FONT_PATH, WHITE
from game_engine.frontend.shop import catalog, gacha, store
from game_engine.frontend.shop.config import SINGLE_PULL_COST, TEN_PULL_COST
from game_engine.frontend.shop.renderer import surfaces_for
from game_engine.frontend.shop.reveal import play_reveal
from game_engine.frontend.widgets import Button

_TIER_COLORS: dict[str, tuple[int, int, int]] = {
    "SSR": (255, 190, 70),
    "SR": (200, 130, 255),
    "S": (255, 120, 160),
    "A": (120, 200, 255),
    "B": (150, 210, 150),
    "C": (180, 180, 180),
}


def _font(size: int = 22) -> pygame.font.Font:
    path = CJK_FONT_PATH or str(FONT_PATH)
    return pygame.font.Font(path, size)


def run_shop_screen(screen: pygame.Surface) -> None:
    clock = pygame.time.Clock()
    font = _font(22)
    title_font = _font(34)
    small_font = _font(16)
    width, height = screen.get_size()
    rng = random.Random()

    identity = store.active_identity()

    back_button = Button("返回", pygame.Rect(60, 40, 140, 48))
    single_button = Button(
        f"單抽 ({SINGLE_PULL_COST})", pygame.Rect(60, 200, 240, 60)
    )
    ten_button = Button(f"十連 ({TEN_PULL_COST})", pygame.Rect(320, 200, 240, 60))

    message = ""
    inv_top = 375
    scroll = 0
    scrollbar_drag = False

    def owned_skins() -> list[int]:
        if identity is None:
            return []
        return list(store.load_entry(identity)["owned_skins"])

    def equipped_skin() -> int:
        if identity is None:
            return 0
        return int(store.load_entry(identity)["equipped_skin"])

    def balance() -> int:
        if identity is None:
            return 0
        return int(store.load_entry(identity)["coins"])

    def inventory_cell_rect(index: int) -> pygame.Rect:
        columns = 6
        cell = 96
        gap = 16
        grid_x = 60
        grid_y = 380
        row, col = divmod(index, columns)
        return pygame.Rect(
            grid_x + col * (cell + gap),
            grid_y + row * (cell + gap + 20),
            cell,
            cell,
        )

    def equip(skin_id: int) -> None:
        if identity is None:
            return
        entry = store.load_entry(identity)
        entry["equipped_skin"] = skin_id
        store.save_entry(identity, entry)

    while True:
        owned = owned_skins()
        row_pitch = 96 + 16 + 20
        rows = (len(owned) + 5) // 6
        viewport = pygame.Rect(0, inv_top, width, height - inv_top - 8)
        # Content spans from the grid top (380) down; how much overflows the viewport.
        content_h = rows * row_pitch + (380 - inv_top)
        max_scroll = max(0, content_h - viewport.height)
        track = pygame.Rect(width - 26, viewport.top, 12, viewport.height)
        thumb: pygame.Rect | None = None
        if max_scroll > 0:
            thumb_h = max(30, int(viewport.height * viewport.height / content_h))
            thumb_y = viewport.top + int((viewport.height - thumb_h) * scroll / max_scroll)
            thumb = pygame.Rect(track.x, thumb_y, track.width, thumb_h)

        def scroll_from_mouse(mouse_y: int, handle: pygame.Rect) -> int:
            span = max(1, viewport.height - handle.height)
            ratio = (mouse_y - viewport.top - handle.height / 2) / span
            return int(max(0.0, min(1.0, ratio)) * max_scroll)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return
            if event.type == pygame.MOUSEWHEEL:
                scroll -= event.y * 45
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                scrollbar_drag = False
            if event.type == pygame.MOUSEMOTION and scrollbar_drag and thumb is not None:
                scroll = scroll_from_mouse(event.pos[1], thumb)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pos = event.pos
                if thumb is not None and track.collidepoint(pos):
                    scrollbar_drag = True
                    scroll = scroll_from_mouse(pos[1], thumb)
                elif back_button.contains(pos):
                    return
                elif single_button.contains(pos):
                    result = gacha.single_pull(rng)
                    if result is None:
                        message = "金錢不足或尚未登入"
                    else:
                        message = ""
                        play_reveal(screen, [result])
                elif ten_button.contains(pos):
                    results = gacha.ten_pull(rng)
                    if results is None:
                        message = "金錢不足或尚未登入"
                    else:
                        message = ""
                        play_reveal(screen, results)
                elif viewport.collidepoint(pos):
                    for index, skin_id in enumerate(owned):
                        if inventory_cell_rect(index).move(0, -scroll).collidepoint(pos):
                            equip(skin_id)
                            break

        scroll = max(0, min(scroll, max_scroll))

        mouse_pos = pygame.mouse.get_pos()
        for button in (back_button, single_button, ten_button):
            button.update_hover(mouse_pos)

        screen.fill(BLACK)
        screen.blit(title_font.render("商店", True, WHITE), (60, 110))
        screen.blit(
            font.render(f"金錢: {balance()}", True, (255, 220, 120)), (width - 260, 120)
        )
        back_button.draw(screen, font)
        single_button.draw(screen, font)
        ten_button.draw(screen, font)

        if message:
            screen.blit(font.render(message, True, (255, 120, 120)), (60, 300))

        screen.blit(font.render("我的車庫 (點擊裝備・滾輪捲動)", True, WHITE), (60, 348))
        current = equipped_skin()
        previous_clip = screen.get_clip()
        screen.set_clip(viewport)
        for index, skin_id in enumerate(owned):
            rect = inventory_cell_rect(index).move(0, -scroll)
            if rect.bottom < viewport.top or rect.top > viewport.bottom:
                continue
            skin = catalog.get_skin(skin_id)
            sprite = surfaces_for(skin_id)["small"]
            sprite = pygame.transform.scale(sprite, (rect.width - 16, rect.height - 16))
            screen.blit(sprite, (rect.x + 8, rect.y + 8))
            # White border for every cell so the equipped one (gold + thicker)
            # is the only highlighted frame and easy to spot.
            is_equipped = skin_id == current
            border = (255, 220, 120) if is_equipped else WHITE
            pygame.draw.rect(screen, border, rect, 5 if is_equipped else 2, border_radius=6)
            # Tier is shown by a colored badge with the tier text, so the level
            # stays readable without color-coding the border.
            tier_color = _TIER_COLORS.get(skin.tier, WHITE)
            tier_surf = small_font.render(skin.tier, True, BLACK)
            badge = pygame.Rect(
                rect.x + 6, rect.y + 6, tier_surf.get_width() + 10, tier_surf.get_height() + 4
            )
            pygame.draw.rect(screen, tier_color, badge, border_radius=4)
            screen.blit(tier_surf, (badge.x + 5, badge.y + 2))
            screen.blit(small_font.render(skin.name, True, WHITE), (rect.x, rect.bottom + 2))
        screen.set_clip(previous_clip)

        if thumb is not None:
            pygame.draw.rect(screen, (40, 40, 46), track, border_radius=6)
            pygame.draw.rect(screen, (120, 120, 130), thumb, border_radius=6)

        pygame.display.update()
        clock.tick(30)
