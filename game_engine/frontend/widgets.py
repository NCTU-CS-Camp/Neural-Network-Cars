from __future__ import annotations

from dataclasses import dataclass

import pygame


# --- F1 Broadcast palette ---
BG       = (10, 11, 14)
CARBON   = (20, 22, 28)
CARBON2  = (27, 30, 38)
FIELD    = (12, 14, 18)
LINE     = (42, 46, 57)
INK      = (238, 241, 246)
DIM      = (138, 146, 163)
RED      = (255, 43, 33)
CYAN     = (24, 223, 230)
YELLOW   = (255, 214, 10)
GREEN    = (58, 224, 110)
SELECT_BG = (28, 17, 20)

CHAMFER = 10


def _chamfer_points(rect: pygame.Rect, cut: int) -> list[tuple[int, int]]:
    """左上 + 右下切角的多邊形頂點，做出 F1 稜角感。"""
    x, y, r, b = rect.left, rect.top, rect.right, rect.bottom
    c = min(cut, rect.width // 2, rect.height // 2)
    return [
        (x + c, y), (r, y), (r, b - c),
        (r - c, b), (x, b), (x, y + c),
    ]


@dataclass(slots=True)
class Label:
    text: str
    position: tuple[int, int]
    color: tuple[int, int, int] = INK

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        rendered = font.render(self.text, True, self.color)
        surface.blit(rendered, self.position)


@dataclass(slots=True)
class Button:
    text: str
    rect: pygame.Rect
    fill_color: tuple[int, int, int] = CARBON       # CTA 請設 RED
    hover_color: tuple[int, int, int] = CARBON2
    text_color: tuple[int, int, int] = INK
    border_color: tuple[int, int, int] = LINE
    shadow_color: tuple[int, int, int] = (0, 0, 0)
    press_offset: int = 3
    hovered: bool = False

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        face_rect = self.rect.copy()
        face_rect.height -= self.press_offset
        if self.hovered:
            face_rect.y += self.press_offset

        fill = self.hover_color if self.hovered else self.fill_color
        pygame.draw.polygon(
            surface, self.shadow_color,
            _chamfer_points(face_rect.move(0, self.press_offset), CHAMFER),
        )
        pygame.draw.polygon(surface, fill, _chamfer_points(face_rect, CHAMFER))
        # 深色一般鈕畫 1px 框；實心彩色 CTA 不畫框
        if fill in (CARBON, CARBON2):
            pygame.draw.lines(
                surface, self.border_color, True,
                _chamfer_points(face_rect, CHAMFER), 1,
            )
        rendered = font.render(self.text, True, self.text_color)
        surface.blit(rendered, rendered.get_rect(center=face_rect.center))

    def contains(self, position: tuple[int, int]) -> bool:
        return self.rect.collidepoint(position)

    def update_hover(self, position: tuple[int, int]) -> None:
        self.hovered = self.contains(position)


@dataclass(slots=True)
class Checkbox:
    rect: pygame.Rect
    label: str = ""
    checked: bool = False
    box_color: tuple[int, int, int] = FIELD
    border_color: tuple[int, int, int] = LINE
    check_color: tuple[int, int, int] = CYAN
    text_color: tuple[int, int, int] = INK

    def contains(self, position: tuple[int, int]) -> bool:
        return self.rect.collidepoint(position)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.contains(event.pos)
        ):
            self.checked = not self.checked
            return True
        return False

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        pygame.draw.rect(surface, self.box_color, self.rect)
        border = self.check_color if self.checked else self.border_color
        pygame.draw.rect(surface, border, self.rect, 1)
        if self.checked:
            inset = self.rect.inflate(-self.rect.width // 3, -self.rect.height // 3)
            pygame.draw.rect(surface, self.check_color, inset)
        if self.label:
            label_surface = font.render(self.label, True, self.text_color)
            surface.blit(
                label_surface,
                label_surface.get_rect(
                    midleft=(self.rect.right + 10, self.rect.centery)
                ),
            )


@dataclass(slots=True)
class Dropdown:
    rect: pygame.Rect
    options: tuple[str, ...]
    placeholder: str = "Select"
    selected: str | None = None
    is_open: bool = False
    fill_color: tuple[int, int, int] = CARBON
    hover_color: tuple[int, int, int] = CARBON2
    text_color: tuple[int, int, int] = INK
    border_color: tuple[int, int, int] = LINE

    def _option_rect(self, index: int) -> pygame.Rect:
        return pygame.Rect(
            self.rect.x,
            self.rect.bottom + index * self.rect.height,
            self.rect.width,
            self.rect.height,
        )

    def contains(
        self, position: tuple[int, int], *, include_options: bool = False
    ) -> bool:
        if self.rect.collidepoint(position):
            return True
        return include_options and any(
            self._option_rect(index).collidepoint(position)
            for index in range(len(self.options))
        )

    def handle_event(self, event: pygame.event.Event) -> str | None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.is_open = False
            return None

        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return None

        if self.rect.collidepoint(event.pos):
            self.is_open = not self.is_open
            return None

        if self.is_open:
            for index, option in enumerate(self.options):
                if self._option_rect(index).collidepoint(event.pos):
                    self.selected = option
                    self.is_open = False
                    return option
            self.is_open = False

        return None

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        mouse_pos = pygame.mouse.get_pos()
        fill = (
            self.hover_color if self.rect.collidepoint(mouse_pos) else self.fill_color
        )
        pygame.draw.rect(surface, fill, self.rect)
        pygame.draw.rect(surface, self.border_color, self.rect, 1)

        text = self.selected or self.placeholder
        rendered = font.render(text, True, self.text_color)
        surface.blit(
            rendered, rendered.get_rect(midleft=(self.rect.x + 10, self.rect.centery))
        )

        arrow_x = self.rect.right - 16
        arrow_y = self.rect.centery
        arrow_points = (
            (
                (arrow_x - 5, arrow_y - 3),
                (arrow_x + 5, arrow_y - 3),
                (arrow_x, arrow_y + 4),
            )
            if not self.is_open
            else (
                (arrow_x - 5, arrow_y + 3),
                (arrow_x + 5, arrow_y + 3),
                (arrow_x, arrow_y - 4),
            )
        )
        pygame.draw.polygon(surface, CYAN, arrow_points)

        if not self.is_open:
            return

        for index, option in enumerate(self.options):
            option_rect = self._option_rect(index)
            option_fill = (
                self.hover_color
                if option_rect.collidepoint(mouse_pos)
                else self.fill_color
            )
            pygame.draw.rect(surface, option_fill, option_rect)
            pygame.draw.rect(surface, self.border_color, option_rect, 1)
            option_surface = font.render(option, True, self.text_color)
            surface.blit(
                option_surface,
                option_surface.get_rect(
                    midleft=(option_rect.x + 10, option_rect.centery)
                ),
            )


@dataclass(slots=True)
class TextInput:
    rect: pygame.Rect
    text: str = ""
    active: bool = False
    composing: str = ""
    max_length: int = 24
    fill_color: tuple[int, int, int] = FIELD
    text_color: tuple[int, int, int] = INK
    border_color: tuple[int, int, int] = LINE
    active_border_color: tuple[int, int, int] = CYAN
    composing_color: tuple[int, int, int] = CYAN
    allowed_characters: str | None = None
    clear_on_focus: bool = False

    def focus(self) -> None:
        self.active = True
        pygame.key.start_text_input()
        pygame.key.set_text_input_rect(self.rect)

    def blur(self) -> None:
        self.active = False
        self.composing = ""
        pygame.key.stop_text_input()

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN:
            was_active = self.active
            clicked_inside = self.rect.collidepoint(event.pos)
            if clicked_inside and not was_active:
                if self.clear_on_focus:
                    self.text = ""
                self.focus()
            elif clicked_inside:
                pygame.key.set_text_input_rect(self.rect)
            elif was_active:
                self.blur()
            return self.active

        if not self.active:
            return False

        if event.type == pygame.TEXTEDITING:
            self.composing = event.text
            return True

        if event.type == pygame.TEXTINPUT:
            self.composing = ""
            entered_text = event.text
            if self.allowed_characters is not None:
                entered_text = "".join(
                    character
                    for character in entered_text
                    if character in self.allowed_characters
                )
            available = self.max_length - len(self.text)
            if available > 0:
                self.text += entered_text[:available]
            return True

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                if self.composing:
                    self.composing = ""
                else:
                    self.text = self.text[:-1]
                return True
            if event.key == pygame.K_v and (event.mod & pygame.KMOD_CTRL):
                try:
                    raw = pygame.scrap.get(pygame.SCRAP_TEXT)
                    if raw:
                        pasted = raw.decode("utf-8", errors="ignore").replace("\x00", "").replace("\r", "")
                        if self.allowed_characters is not None:
                            pasted = "".join(c for c in pasted if c in self.allowed_characters)
                        available = self.max_length - len(self.text)
                        if available > 0:
                            self.text += pasted[:available]
                except Exception:
                    pass
                return True

        return False

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        pygame.draw.rect(surface, self.fill_color, self.rect)
        border = self.active_border_color if self.active else self.border_color
        pygame.draw.rect(surface, border, self.rect, 1)

        committed_surf = font.render(self.text, True, self.text_color)
        committed_rect = committed_surf.get_rect(midleft=(self.rect.x + 8, self.rect.centery))
        surface.blit(committed_surf, committed_rect)

        if self.composing:
            composing_surf = font.render(self.composing, True, self.composing_color)
            composing_rect = composing_surf.get_rect(midleft=(committed_rect.right, self.rect.centery))
            surface.blit(composing_surf, composing_rect)
            underline_y = composing_rect.bottom - 1
            pygame.draw.line(surface, self.composing_color,
                             (composing_rect.left, underline_y),
                             (composing_rect.right, underline_y), 1)


@dataclass(slots=True)
class ProgressBar:
    rect: pygame.Rect
    value: float = 0.0
    max_value: float = 1.0
    track_color: tuple[int, int, int] = FIELD
    fill_color: tuple[int, int, int] = CYAN
    border_color: tuple[int, int, int] = LINE

    def ratio(self) -> float:
        if self.max_value <= 0:
            return 0.0
        return max(0.0, min(1.0, self.value / self.max_value))

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        pygame.draw.rect(surface, self.track_color, self.rect)
        fill_width = int(self.rect.width * self.ratio())
        if fill_width > 0:
            fill_rect = pygame.Rect(self.rect.x, self.rect.y, fill_width, self.rect.height)
            pygame.draw.rect(surface, self.fill_color, fill_rect)
        pygame.draw.rect(surface, self.border_color, self.rect, 1)
        del font


@dataclass(slots=True)
class VerticalScrollbar:
    rect: pygame.Rect
    total_items: int
    visible_items: int
    offset: int = 0
    dragging: bool = False
    drag_grab_offset: int = 0
    track_color: tuple[int, int, int] = CARBON
    thumb_color: tuple[int, int, int] = (74, 80, 94)
    hover_thumb_color: tuple[int, int, int] = CYAN

    def max_offset(self) -> int:
        return max(0, self.total_items - self.visible_items)

    def clamp(self) -> None:
        self.offset = max(0, min(self.offset, self.max_offset()))

    def is_needed(self) -> bool:
        return self.total_items > self.visible_items

    def _thumb_rect(self) -> pygame.Rect:
        ratio = self.visible_items / max(1, self.total_items)
        thumb_h = max(24, int(self.rect.height * ratio))
        span = self.rect.height - thumb_h
        max_offset = self.max_offset()
        thumb_y = self.rect.y + (0 if max_offset == 0 else int(span * self.offset / max_offset))
        return pygame.Rect(self.rect.x, thumb_y, self.rect.width, thumb_h)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.is_needed():
            return False
        if event.type == pygame.MOUSEWHEEL:
            self.offset -= event.y
            self.clamp()
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            thumb_rect = self._thumb_rect()
            if thumb_rect.collidepoint(event.pos):
                self.dragging = True
                self.drag_grab_offset = event.pos[1] - thumb_rect.y
                return True
            if self.rect.collidepoint(event.pos):
                span = self.rect.height - thumb_rect.height
                if span > 0:
                    target_y = event.pos[1] - thumb_rect.height // 2 - self.rect.y
                    self.offset = round(self.max_offset() * max(0, min(span, target_y)) / span)
                    self.clamp()
                return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was_dragging = self.dragging
            self.dragging = False
            return was_dragging
        if event.type == pygame.MOUSEMOTION and self.dragging:
            thumb_rect = self._thumb_rect()
            span = self.rect.height - thumb_rect.height
            if span > 0:
                target_y = event.pos[1] - self.drag_grab_offset - self.rect.y
                self.offset = round(self.max_offset() * max(0, min(span, target_y)) / span)
                self.clamp()
            return True
        return False

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        del font
        if not self.is_needed():
            return
        pygame.draw.rect(surface, self.track_color, self.rect)
        thumb_rect = self._thumb_rect()
        mouse_pos = pygame.mouse.get_pos()
        color = (
            self.hover_thumb_color
            if self.dragging or thumb_rect.collidepoint(mouse_pos)
            else self.thumb_color
        )
        pygame.draw.rect(surface, color, thumb_rect)


@dataclass(slots=True)
class Slider:
    rect: pygame.Rect
    min_value: int = 0
    max_value: int = 100
    value: int = 0
    dragging: bool = False
    track_color: tuple[int, int, int] = LINE
    handle_color: tuple[int, int, int] = CYAN   # 懲罰滑桿在呼叫端設 handle_color=RED
    handle_radius: int | None = None
    show_value: bool = True

    def _handle_radius(self) -> int:
        return self.handle_radius or self.rect.height

    def _hit_rect(self) -> pygame.Rect:
        radius = self._handle_radius()
        return self.rect.inflate(radius * 2, radius * 2)

    def _value_to_x(self) -> int:
        span = self.max_value - self.min_value
        ratio = 0.0 if span == 0 else (self.value - self.min_value) / span
        return int(self.rect.x + ratio * self.rect.width)

    def _x_to_value(self, x: int) -> int:
        span = self.max_value - self.min_value
        ratio = max(0.0, min(1.0, (x - self.rect.x) / self.rect.width))
        return int(round(self.min_value + ratio * span))

    def handle_event(self, event: pygame.event.Event) -> bool:
        if (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self._hit_rect().collidepoint(event.pos)
        ):
            self.dragging = True
            self.value = self._x_to_value(event.pos[0])
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was_dragging = self.dragging
            self.dragging = False
            return was_dragging
        if event.type == pygame.MOUSEMOTION and self.dragging:
            self.value = self._x_to_value(event.pos[0])
            return True
        return False

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        # 遙測軌道：暗底 + 細框
        pygame.draw.rect(surface, FIELD, self.rect)
        pygame.draw.rect(surface, self.track_color, self.rect, 1)
        handle_x = self._value_to_x()
        # 已填滿：主色
        filled = pygame.Rect(self.rect.x, self.rect.y, max(0, handle_x - self.rect.x), self.rect.height)
        if filled.width > 0:
            pygame.draw.rect(surface, self.handle_color, filled)
        # 把手：雪佛龍/菱形
        cy = self.rect.centery
        h = self._handle_radius()
        chevron = [
            (handle_x - 5, cy - h), (handle_x + 5, cy - h),
            (handle_x + 5, cy + h - 4), (handle_x, cy + h),
            (handle_x - 5, cy + h - 4),
        ]
        pygame.draw.polygon(surface, self.handle_color, chevron)
        if self.show_value:
            rendered = font.render(str(self.value), True, INK)
            surface.blit(rendered, (self.rect.right + 12, self.rect.y))
