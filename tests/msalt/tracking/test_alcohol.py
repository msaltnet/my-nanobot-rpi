from msalt.tracking.alcohol import (
    alcohol_profiles_for_prompt,
    calculate_alcohol_g,
    find_alcohol_profile,
)


def test_calculate_alcohol_g_for_common_drinks():
    assert calculate_alcohol_g(amount=1, serving_ml=360, abv_percent=17) == 48.3
    assert calculate_alcohol_g(amount=1, serving_ml=500, abv_percent=5) == 19.7
    assert calculate_alcohol_g(amount=2, serving_ml=150, abv_percent=13) == 30.8
    assert calculate_alcohol_g(amount=2, serving_ml=45, abv_percent=40) == 28.4


def test_find_alcohol_profile_by_name_and_alias():
    assert find_alcohol_profile("맥주").serving_ml == 500
    assert find_alcohol_profile("beer").drink_type == "맥주"
    assert find_alcohol_profile("없는술") is None


def test_alcohol_profiles_for_prompt_contains_defaults():
    profiles = alcohol_profiles_for_prompt()
    by_type = {p["drink_type"]: p for p in profiles}
    assert by_type["소주"]["unit"] == "병"
    assert by_type["맥주"]["abv_percent"] == 5
    assert by_type["와인"]["serving_ml"] == 150
    assert by_type["위스키"]["serving_ml"] == 45
