import pygame

from game_engine.frontend.widgets import Dropdown


def _left_click(position: tuple[int, int]) -> pygame.event.Event:
    return pygame.event.Event(
        pygame.MOUSEBUTTONDOWN,
        {"button": 1, "pos": position},
    )


def test_dropdown_opens_and_returns_selected_option() -> None:
    dropdown = Dropdown(
        pygame.Rect(10, 20, 160, 30),
        ("balanced_v1", "safe_finish_v1"),
    )

    assert dropdown.handle_event(_left_click(dropdown.rect.center)) is None
    assert dropdown.is_open

    second_option_position = (dropdown.rect.centerx, dropdown.rect.bottom + 45)
    assert (
        dropdown.handle_event(_left_click(second_option_position)) == "safe_finish_v1"
    )
    assert dropdown.selected == "safe_finish_v1"
    assert not dropdown.is_open


def test_dropdown_closes_when_clicking_outside() -> None:
    dropdown = Dropdown(pygame.Rect(10, 20, 160, 30), ("balanced_v1",))
    dropdown.is_open = True

    assert dropdown.handle_event(_left_click((400, 400))) is None
    assert not dropdown.is_open


def test_dropdown_reports_expanded_hit_area_only_when_requested() -> None:
    dropdown = Dropdown(pygame.Rect(10, 20, 160, 30), ("balanced_v1",))
    option_position = (dropdown.rect.centerx, dropdown.rect.bottom + 15)

    assert not dropdown.contains(option_position)
    assert dropdown.contains(option_position, include_options=True)
