import pygame

from game_engine.frontend.widgets import Dropdown, Slider, TextInput


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


def test_numeric_text_input_filters_non_digits_and_limits_length() -> None:
    input_value = TextInput(
        pygame.Rect(10, 20, 80, 30),
        active=True,
        max_length=3,
        allowed_characters="0123456789",
    )

    input_value.handle_event(
        pygame.event.Event(pygame.TEXTINPUT, {"text": "12a34"})
    )

    assert input_value.text == "123"


def test_text_input_can_replace_existing_numeric_value_on_focus() -> None:
    input_value = TextInput(
        pygame.Rect(10, 20, 80, 30),
        text="50",
        clear_on_focus=True,
    )

    input_value.handle_event(_left_click(input_value.rect.center))

    assert input_value.active
    assert input_value.text == ""


def test_slider_large_handle_area_is_draggable() -> None:
    slider = Slider(
        pygame.Rect(20, 40, 200, 12),
        handle_radius=18,
        show_value=False,
    )
    click_above_track = pygame.event.Event(
        pygame.MOUSEBUTTONDOWN,
        {"button": 1, "pos": (120, 28)},
    )

    assert slider.handle_event(click_above_track)
    assert slider.dragging
    assert slider.value == 50
