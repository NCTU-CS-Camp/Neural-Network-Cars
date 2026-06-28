from __future__ import annotations

from dataclasses import dataclass

import pygame


@dataclass(slots=True)
class Label:
    text: str
    position: tuple[int, int]
    color: tuple[int, int, int] = (255, 255, 255)

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        rendered = font.render(self.text, True, self.color)
        surface.blit(rendered, self.position)


@dataclass(slots=True)
class Button:
    text: str
    rect: pygame.Rect
    fill_color: tuple[int, int, int] = (30, 30, 30)
    hover_color: tuple[int, int, int] = (55, 55, 55)
    text_color: tuple[int, int, int] = (255, 255, 255)
    border_color: tuple[int, int, int] = (90, 90, 90)
    hovered: bool = False

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        fill = self.hover_color if self.hovered else self.fill_color
        pygame.draw.rect(surface, fill, self.rect)
        pygame.draw.rect(surface, self.border_color, self.rect, 2)
        rendered = font.render(self.text, True, self.text_color)
        text_rect = rendered.get_rect(center=self.rect.center)
        surface.blit(rendered, text_rect)

    def contains(self, position: tuple[int, int]) -> bool:
        return self.rect.collidepoint(position)

    def update_hover(self, position: tuple[int, int]) -> None:
        self.hovered = self.contains(position)


@dataclass(slots=True)
class Dropdown:
    rect: pygame.Rect
    options: tuple[str, ...]
    placeholder: str = "Select"
    selected: str | None = None
    is_open: bool = False
    fill_color: tuple[int, int, int] = (30, 30, 30)
    hover_color: tuple[int, int, int] = (55, 55, 55)
    text_color: tuple[int, int, int] = (255, 255, 255)
    border_color: tuple[int, int, int] = (90, 90, 90)

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
        pygame.draw.rect(surface, self.border_color, self.rect, 2)

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
        pygame.draw.polygon(surface, self.text_color, arrow_points)

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
    fill_color: tuple[int, int, int] = (30, 30, 30)
    text_color: tuple[int, int, int] = (255, 255, 255)
    border_color: tuple[int, int, int] = (90, 90, 90)
    active_border_color: tuple[int, int, int] = (120, 170, 255)
    composing_color: tuple[int, int, int] = (255, 220, 0)
    allowed_characters: str | None = None
    clear_on_focus: bool = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN:
            was_active = self.active
            self.active = self.rect.collidepoint(event.pos)
            if self.active and not was_active:
                if self.clear_on_focus:
                    self.text = ""
                pygame.key.start_text_input()
            elif not self.active and was_active:
                pygame.key.stop_text_input()
                self.composing = ""
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

        if event.type == pygame.KEYDOWN and event.key == pygame.K_BACKSPACE:
            if self.composing:
                self.composing = ""
            else:
                self.text = self.text[:-1]
            return True

        return False

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        pygame.draw.rect(surface, self.fill_color, self.rect)
        border = self.active_border_color if self.active else self.border_color
        pygame.draw.rect(surface, border, self.rect, 2)

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
class Slider:
    rect: pygame.Rect
    min_value: int = 0
    max_value: int = 100
    value: int = 0
    dragging: bool = False
    track_color: tuple[int, int, int] = (90, 90, 90)
    handle_color: tuple[int, int, int] = (200, 200, 200)
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
        pygame.draw.rect(surface, self.track_color, self.rect, border_radius=4)
        handle_x = self._value_to_x()
        pygame.draw.circle(
            surface,
            self.handle_color,
            (handle_x, self.rect.centery),
            self._handle_radius(),
        )
        if self.show_value:
            rendered = font.render(str(self.value), True, (255, 255, 255))
            surface.blit(rendered, (self.rect.right + 12, self.rect.y))
