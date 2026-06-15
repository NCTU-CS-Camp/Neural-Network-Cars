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
    text_color: tuple[int, int, int] = (255, 255, 255)
    border_color: tuple[int, int, int] = (90, 90, 90)

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        pygame.draw.rect(surface, self.fill_color, self.rect)
        pygame.draw.rect(surface, self.border_color, self.rect, 2)
        rendered = font.render(self.text, True, self.text_color)
        text_rect = rendered.get_rect(center=self.rect.center)
        surface.blit(rendered, text_rect)

    def contains(self, position: tuple[int, int]) -> bool:
        return self.rect.collidepoint(position)

