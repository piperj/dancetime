import re

from ranking.models import DanceResult


SKILL_OFFSETS = {
    "newcomer": -100,
    "bronze": -60,
    "full bronze": -50,
    "silver": -20,
    "full silver": 0,
    "gold": 30,
    "full gold": 40,
    "novice": 50,
    "pre-champ": 70,
    "prechamp": 70,
    "championship": 90,
    "open": 100,
}

AGE_OFFSETS = {
    "youth": -60,
    "junior": -50,
    "teen": -40,
    "pre-teen": -50,
    "adult": 0,
    "a1": 10,
    "a2": 20,
    "senior": -30,
    "senior 1": -30,
    "senior 2": -35,
    "senior 3": -40,
    "senior i": -30,
    "senior ii": -35,
    "senior iii": -40,
}


def parse_skill_category(event_name: str) -> str | None:
    name = event_name.lower()
    for skill in sorted(SKILL_OFFSETS, key=len, reverse=True):
        if skill in name:
            return skill
    return None


def parse_age_division(event_name: str) -> str | None:
    name = event_name.lower()
    for age in sorted(AGE_OFFSETS, key=len, reverse=True):
        if age in name:
            return age
    return None


def get_initial_ratings(
    results: list[DanceResult],
    prior_ratings: dict[str, dict],
    base: float = 1500.0,
) -> dict[str, float]:
    ratings: dict[str, float] = {}
    competitors = {c for r in results for c in r.competitors}

    for competitor in competitors:
        if competitor in prior_ratings:
            ratings[competitor] = prior_ratings[competitor]["elo"]
        else:
            offset = _skill_offset(results, competitor) + _age_offset(results, competitor)
            ratings[competitor] = base + offset
    return ratings


def _skill_offset(results: list[DanceResult], competitor: str) -> float:
    for r in results:
        if competitor in r.competitors:
            skill = parse_skill_category(r.event_name)
            if skill:
                return SKILL_OFFSETS[skill]
    return 0.0


def _age_offset(results: list[DanceResult], competitor: str) -> float:
    for r in results:
        if competitor in r.competitors:
            age = parse_age_division(r.event_name)
            if age:
                return AGE_OFFSETS[age]
    return 0.0
