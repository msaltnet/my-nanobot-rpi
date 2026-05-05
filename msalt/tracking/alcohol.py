"""Alcohol drink profiles and pure-alcohol conversion helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final


ALCOHOL_DENSITY_G_PER_ML: Final = 0.789


@dataclass(frozen=True)
class AlcoholProfile:
    drink_type: str
    unit: str
    serving_ml: float
    abv_percent: float
    aliases: tuple[str, ...] = ()


DEFAULT_ALCOHOL_PROFILES: Final[tuple[AlcoholProfile, ...]] = (
    AlcoholProfile("소주", "병", 360, 17, ("참이슬", "처음처럼", "새로")),
    AlcoholProfile("맥주", "캔", 500, 5, ("beer", "생맥주")),
    AlcoholProfile("막걸리", "병", 750, 6, ("탁주",)),
    AlcoholProfile("와인", "잔", 150, 13, ("wine", "레드와인", "화이트와인")),
    AlcoholProfile("위스키", "잔", 45, 40, ("whisky", "whiskey", "버번")),
    AlcoholProfile("하이볼", "잔", 350, 7, ("highball",)),
    AlcoholProfile("칵테일", "잔", 150, 15, ("cocktail",)),
)


def calculate_alcohol_g(
    amount: float,
    serving_ml: float,
    abv_percent: float,
) -> float:
    """Return grams of pure alcohol, rounded to one decimal place."""
    alcohol_g = amount * serving_ml * (abv_percent / 100) * ALCOHOL_DENSITY_G_PER_ML
    return round(alcohol_g, 1)


def alcohol_profiles_for_prompt() -> list[dict[str, object]]:
    """Small JSON-ready view used to ground the LLM parser."""
    return [
        {
            "drink_type": p.drink_type,
            "unit": p.unit,
            "serving_ml": p.serving_ml,
            "abv_percent": p.abv_percent,
            "aliases": list(p.aliases),
        }
        for p in DEFAULT_ALCOHOL_PROFILES
    ]


def find_alcohol_profile(drink_type: str) -> AlcoholProfile | None:
    needle = drink_type.strip().casefold()
    for profile in DEFAULT_ALCOHOL_PROFILES:
        names = (profile.drink_type, *profile.aliases)
        if needle in {name.casefold() for name in names}:
            return profile
    return None
