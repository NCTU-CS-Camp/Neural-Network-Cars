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
class TextInput:
    rect: pygame.Rect
    text: str = ""
    active: bool = False
    max_length: int = 24
    fill_color: tuple[int, int, int] = (30, 30, 30)
    text_color: tuple[int, int, int] = (255, 255, 255)
    border_color: tuple[int, int, int] = (90, 90, 90)
    active_border_color: tuple[int, int, int] = (120, 170, 255)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN:
            was_active = self.active
            self.active = self.rect.collidepoint(event.pos)
            if self.active and not was_active:
                pygame.key.start_text_input()
            elif not self.active and was_active:
                pygame.key.stop_text_input()
            return self.active

        if not self.active:
            return False

        if event.type == pygame.TEXTINPUT:
            if len(self.text) < self.max_length:
                self.text += event.text
            return True

        if event.type == pygame.KEYDOWN and event.key == pygame.K_BACKSPACE:
            self.text = self.text[:-1]
            return True

        return False

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        pygame.draw.rect(surface, self.fill_color, self.rect)
        border = self.active_border_color if self.active else self.border_color
        pygame.draw.rect(surface, border, self.rect, 2)
        rendered = font.render(self.text, True, self.text_color)
        text_rect = rendered.get_rect(midleft=(self.rect.x + 8, self.rect.centery))
        surface.blit(rendered, text_rect)


@dataclass(slots=True)
class Slider:
    rect: pygame.Rect
    min_value: int = 0
    max_value: int = 100
    value: int = 0
    dragging: bool = False
    track_color: tuple[int, int, int] = (90, 90, 90)
    handle_color: tuple[int, int, int] = (200, 200, 200)

    def _value_to_x(self) -> int:
        span = self.max_value - self.min_value
        ratio = 0.0 if span == 0 else (self.value - self.min_value) / span
        return int(self.rect.x + ratio * self.rect.width)

    def _x_to_value(self, x: int) -> int:
        span = self.max_value - self.min_value
        ratio = max(0.0, min(1.0, (x - self.rect.x) / self.rect.width))
        return int(round(self.min_value + ratio * span))

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and self.rect.collidepoint(event.pos):
            self.dragging = True
            self.value = self._x_to_value(event.pos[0])
            return True
        if event.type == pygame.MOUSEBUTTONUP:
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
            surface, self.handle_color, (handle_x, self.rect.centery), self.rect.height
        )
        rendered = font.render(str(self.value), True, (255, 255, 255))
        surface.blit(rendered, (self.rect.right + 12, self.rect.y))

