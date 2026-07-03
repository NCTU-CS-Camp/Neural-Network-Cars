import pygame

from game_engine.frontend.shop import catalog
from game_engine.frontend.shop.config import (
    GUARANTEE_TIERS,
    TIER_PROBABILITIES,
    TIERS,
)
from game_engine.frontend.shop.renderer import surfaces_for


def test_ssr_is_removed_from_the_shop() -> None:
    assert "SSR" not in TIERS
    assert "SSR" not in TIER_PROBABILITIES
    assert "SSR" not in GUARANTEE_TIERS
    assert all(skin.tier != "SSR" for skin in catalog.all_skins())
    assert sum(TIER_PROBABILITIES.values()) == 1.0


def test_f1_mercedes_renders_nose_up_at_standard_car_size() -> None:
    pygame.init()
    pygame.display.set_mode((1, 1))

    mercedes = surfaces_for(14)
    ferrari = surfaces_for(12)

    assert mercedes["small"].get_height() > mercedes["small"].get_width()
    assert mercedes["big"].get_height() > mercedes["big"].get_width()
    assert mercedes["small"].get_height() == ferrari["small"].get_height()
    assert mercedes["big"].get_height() == ferrari["big"].get_height()
