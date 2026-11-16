"""Tests for the planet-state (dignity) queries: exaltation, debilitation,
own sign, Moolatrikona, Vargottama, and the Panchadha Maitri relation
(Adhi Mitra .. Adhi Shatru) a planet has with the current lord of its sign.

``chart.graha_dignity`` / ``chart.navamsa_rashi`` / ``chart.compound_relation``
are pure, pada/rashi-only functions (no birth chart); ``dignity_periods`` in
transit_pada_query turns them into flattened windows over a loaded transit
file, matching the style of ``relationship_periods`` / ``status_periods``.

Mars-Jupiter dates below are cross-checked against
test_transit_pada.test_mars_jupiter_periods_in_2026, which reads the same
2025-2027 fixture files independently through relationship_periods.
"""
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from chart import (DignityType, GrahaId, RashiId, SambandhaType, compound_relation,
                   graha_dignity, navamsa_rashi, rashi_padas)
from transit_pada_query import (dignity_periods, filter_dignities, intersect_periods,
                                load_moon_transits, load_planet_transits, merge_touching,
                                relationship_periods, subtract_periods)

DATA = Path(__file__).resolve().parent / 'data'
MULTI_YEAR_PLANETS_CSV = DATA / 'transit_pada_planets_2025-2027.csv'
MULTI_YEAR_MOON_CSV = DATA / 'transit_pada_moon_2025-2027.csv'
YEAR_2026 = (date(2026, 1, 1), date(2027, 1, 1))


# =============================================================================
# Pure geometry / tables: chart.graha_dignity, navamsa_rashi, compound_relation
# =============================================================================

def _first_pada(rashi: RashiId) -> int:
    return rashi_padas(rashi).start


def test_exaltation_and_debilitation_take_priority():
    assert graha_dignity(GrahaId.JUPITER, _first_pada(RashiId.CANCER), {}).type == DignityType.EXALTED
    assert graha_dignity(GrahaId.MARS, _first_pada(RashiId.CANCER), {}).type == DignityType.DEBILITATED
    assert graha_dignity(GrahaId.RAHU, _first_pada(RashiId.GEMINI), {}).type == DignityType.EXALTED
    assert graha_dignity(GrahaId.KETU, _first_pada(RashiId.GEMINI), {}).type == DignityType.DEBILITATED


def test_moolatrikona_sign_outranks_plain_own_sign():
    # Mars owns both Aries and Scorpio; only Aries is its Moolatrikona sign.
    assert graha_dignity(GrahaId.MARS, _first_pada(RashiId.ARIES), {}).type == DignityType.MOOLATRIKONA
    assert graha_dignity(GrahaId.MARS, _first_pada(RashiId.SCORPIO), {}).type == DignityType.SWARASHI
    # Sun owns only Leo, which is also its Moolatrikona sign.
    sun = graha_dignity(GrahaId.SUN, _first_pada(RashiId.LEO), {})
    assert sun.type == DignityType.MOOLATRIKONA and sun.is_swarashi and sun.is_moolatrikona


def test_vargottama_is_independent_of_the_sign_dignity():
    # Pada 1 is Aries' first navamsa -- itself Aries -- so it is vargottama too.
    vargottama_moolatrikona = graha_dignity(GrahaId.MARS, 1, {})
    assert vargottama_moolatrikona.type == DignityType.MOOLATRIKONA and vargottama_moolatrikona.is_vargottama
    # Pada 2 (still Aries) is a different navamsa (Taurus), so not vargottama.
    plain_moolatrikona = graha_dignity(GrahaId.MARS, 2, {})
    assert plain_moolatrikona.type == DignityType.MOOLATRIKONA and not plain_moolatrikona.is_vargottama


@pytest.mark.parametrize('pada, expected', [
    (1, RashiId.ARIES), (5, RashiId.LEO), (9, RashiId.SAGITTARIUS),     # fire starts at Aries
    (10, RashiId.CAPRICORN), (18, RashiId.VIRGO),                      # earth starts at Capricorn
    (19, RashiId.LIBRA), (27, RashiId.GEMINI),                         # air starts at Libra
    (28, RashiId.CANCER), (36, RashiId.PISCES),                        # water starts at Cancer
])
def test_navamsa_rashi_of_each_elements_first_and_last_pada(pada, expected):
    assert navamsa_rashi(pada) == expected


@pytest.mark.parametrize('graha, other, graha_rashi, other_rashi, expected', [
    # Mercury's natural friend is the Sun; friendly house (2nd) -> Adhi Mitra.
    (GrahaId.MERCURY, GrahaId.SUN, RashiId.LEO, RashiId.VIRGO, DignityType.ADHI_MITRA),
    # Same pair conjunct (1st house) is temporally hostile -> friend+enemy = Sama.
    (GrahaId.MERCURY, GrahaId.SUN, RashiId.LEO, RashiId.LEO, DignityType.SAMA),
    # Moon and Mars are natural neutrals; friendly house -> Mitra, hostile -> Shatru.
    (GrahaId.MOON, GrahaId.MARS, RashiId.CANCER, RashiId.LEO, DignityType.MITRA),
    (GrahaId.MOON, GrahaId.MARS, RashiId.CANCER, RashiId.SCORPIO, DignityType.SHATRU),
    # Saturn and Mars are natural enemies; hostile (conjunct) -> Adhi Shatru, friendly -> Sama.
    (GrahaId.SATURN, GrahaId.MARS, RashiId.SCORPIO, RashiId.SCORPIO, DignityType.ADHI_SHATRU),
    (GrahaId.SATURN, GrahaId.MARS, RashiId.AQUARIUS, RashiId.PISCES, DignityType.SAMA),
])
def test_compound_relation_panchadha_maitri_table(graha, other, graha_rashi, other_rashi, expected):
    assert compound_relation(graha, other, graha_rashi, other_rashi) == expected


def test_graha_dignity_falls_back_to_compound_relation_with_the_sign_lord():
    # Mercury in Leo (Sun's sign); Sun itself sits in friendly Virgo -> Adhi Mitra.
    padas = {GrahaId.SUN: _first_pada(RashiId.VIRGO)}
    dignity = graha_dignity(GrahaId.MERCURY, _first_pada(RashiId.LEO), padas)
    assert dignity.type == DignityType.ADHI_MITRA and not dignity.is_own_or_exalted


def test_graha_dignity_needs_the_sign_lords_pada_when_not_in_its_own_sign():
    with pytest.raises(ValueError):
        graha_dignity(GrahaId.MERCURY, _first_pada(RashiId.LEO), {})


# =============================================================================
# dignity_periods over a loaded transit file
# =============================================================================

@pytest.fixture(scope='module')
def years_2025_2027():
    return load_planet_transits(MULTI_YEAR_PLANETS_CSV), load_moon_transits(MULTI_YEAR_MOON_CSV)


def test_jupiter_exaltation_periods_in_2026(years_2025_2027):
    windows = dignity_periods('JUP', *years_2025_2027, *YEAR_2026)
    exalted = merge_touching((w.start, w.end) for w in filter_dignities(windows, [DignityType.EXALTED]))
    assert [(s.date(), e.date()) for s, e in exalted] == [(date(2026, 6, 1), date(2026, 10, 31))]
    assert all(w.rashi == RashiId.CANCER for w in windows if w.dignity == DignityType.EXALTED)


def test_mars_debilitation_periods_in_2026(years_2025_2027):
    windows = dignity_periods('MAR', *years_2025_2027, *YEAR_2026)
    debilitated = merge_touching(
        (w.start, w.end) for w in filter_dignities(windows, [DignityType.DEBILITATED]))
    assert [(s.date(), e.date()) for s, e in debilitated] == [(date(2026, 9, 18), date(2026, 11, 12))]
    assert all(w.rashi == RashiId.CANCER for w in windows if w.dignity == DignityType.DEBILITATED)


def test_mars_jupiter_conjunction_while_mars_not_debilitated(years_2025_2027):
    """The Karka (Cancer) conjunction is dropped because Mars is debilitated there;
    the later Simha (Leo) conjunction survives -- matching the known Mars-Jupiter
    conjunction windows of test_transit_pada.test_mars_jupiter_periods_in_2026.
    """
    conjunctions = relationship_periods('MAR', 'JUP', *years_2025_2027, *YEAR_2026,
                                        types=[SambandhaType.CONJUNCTION])
    assert [(p.start.date(), p.end.date()) for p in sorted(conjunctions, key=lambda p: p.start)] == [
        (date(2026, 9, 18), date(2026, 10, 31)), (date(2026, 11, 12), date(2027, 1, 24))]
    debilitated = filter_dignities(dignity_periods('MAR', *years_2025_2027, *YEAR_2026),
                                   [DignityType.DEBILITATED])
    remaining = merge_touching(subtract_periods(conjunctions, debilitated))
    assert [(s.date(), e.date()) for s, e in remaining] == [(date(2026, 11, 12), date(2027, 1, 24))]


def test_dignity_periods_validate_the_planet(years_2025_2027):
    with pytest.raises(ValueError):
        dignity_periods('PLUTO', *years_2025_2027, *YEAR_2026)


# =============================================================================
# Interval algebra helpers
# =============================================================================

def _ts(text):
    return pd.Timestamp(text, tz='UTC')


def test_intersect_periods_keeps_only_the_overlap():
    class Window:
        def __init__(self, start, end):
            self.start, self.end = _ts(start), _ts(end)

    first = [Window('2026-01-01', '2026-01-10'), Window('2026-02-01', '2026-02-10')]
    second = [Window('2026-01-05', '2026-01-20')]
    assert intersect_periods(first, second) == [(_ts('2026-01-05'), _ts('2026-01-10'))]


def test_subtract_periods_removes_covered_spans():
    class Window:
        def __init__(self, start, end):
            self.start, self.end = _ts(start), _ts(end)

    first = [Window('2026-01-01', '2026-01-31')]
    second = [Window('2026-01-10', '2026-01-20')]
    assert subtract_periods(first, second) == [
        (_ts('2026-01-01'), _ts('2026-01-10')), (_ts('2026-01-20'), _ts('2026-01-31'))]


def test_merge_touching_joins_adjacent_spans():
    periods = [(_ts('2026-01-01'), _ts('2026-01-10')), (_ts('2026-01-10'), _ts('2026-01-20')),
              (_ts('2026-02-01'), _ts('2026-02-05'))]
    assert merge_touching(periods) == [(_ts('2026-01-01'), _ts('2026-01-20')),
                                       (_ts('2026-02-01'), _ts('2026-02-05'))]
