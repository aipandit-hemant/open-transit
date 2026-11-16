"""Correctness of the unified dasha + transit timeline, 1 Jun - 31 Aug 2026 (IST).

Native: 24 Jun 1982, 00:45 IST, Betul (MP). Expected (dates in IST):

    01 Jun  Jupiter Mithuna, Mars Mesha,     MD Venus, AD Jupiter   (first row)
    02 Jun  Jupiter -> Karka, Mars Mesha,    MD Venus, AD Jupiter
    21 Jun  Mars -> Vrishabha, Jupiter Karka, MD Venus, AD Jupiter
    02 Aug  Mars -> Mithuna, Jupiter Karka,  MD Venus, AD Jupiter
    31 Aug  Mars Mithuna, Jupiter Karka,     MD Venus, AD Jupiter   (last row)

No dasha change falls inside the window, so every transit carries Venus/Jupiter.
In UTC, Mars enters Vrishabha on 20 Jun (18:38), so these dates hold in IST only.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from chart import GrahaId, RashiId
from planet_timeline import DashaEvent, TimeRange, TransitEvent
from sample_transit_queries.query_unified_timeline_jun_aug_2026 import (
    IST, flattened_antardasha, merge_by_start, rashi_change_transits, unified_timeline)


@pytest.fixture(scope='module')
def rows():
    return unified_timeline()


def _transit_row(rows, planet: GrahaId, to_rashi: RashiId):
    [row] = [r for r in rows if isinstance(r.event, TransitEvent)
             and (r.event.planet, r.event.to_rashi) == (planet, to_rashi)]
    return row


def _assert_row(row, day: date, jupiter: RashiId, mars: RashiId):
    assert row.at.tzinfo == IST and row.at.date() == day
    assert (row.rashis[GrahaId.JUPITER], row.rashis[GrahaId.MARS]) == (jupiter, mars)
    assert (row.md, row.ad) == (GrahaId.VENUS, GrahaId.JUPITER)


# --- Step 1 and 2 on their own --------------------------------------------------

def test_flattened_antardasha_is_one_venus_jupiter_period_covering_the_window():
    [period] = flattened_antardasha()
    assert (period.md, period.ad, period.changed) == (GrahaId.VENUS, GrahaId.JUPITER, None)
    assert period.time_range.start == datetime(2026, 6, 1, tzinfo=IST)
    assert period.time_range.end == datetime(2026, 9, 1, tzinfo=IST)
    assert period.time_range.starts_before and period.time_range.ends_after


def test_rashi_change_transits_are_every_planet_ingress_without_the_moon():
    transits = rashi_change_transits()
    assert len(transits) == 13
    assert GrahaId.MOON not in {t.planet for t in transits}
    assert [t.time_range.start for t in transits] == sorted(t.time_range.start for t in transits)
    mars = [(t.time_range.start.astimezone(IST).date(), t.to_rashi) for t in transits if t.planet == GrahaId.MARS]
    assert mars == [(date(2026, 6, 21), RashiId.TAURUS), (date(2026, 8, 2), RashiId.GEMINI)]


# --- Step 3: merge sort ---------------------------------------------------------

def test_merge_by_start_interleaves_two_sorted_lists_dasha_first_on_ties():
    def at(day):
        return datetime(2026, 6, day, tzinfo=timezone.utc)

    def dasha(day):
        return DashaEvent(TimeRange(at(day), at(day) + timedelta(days=1)), GrahaId.VENUS, GrahaId.JUPITER)

    def transit(day):
        return TransitEvent(TimeRange(at(day), at(day) + timedelta(days=1)), GrahaId.MARS,
                            RashiId.ARIES, RashiId.TAURUS)

    d1, d5 = dasha(1), dasha(5)
    t2, t5, t9 = transit(2), transit(5), transit(9)
    assert merge_by_start([d1, d5], [t2, t5, t9]) == [d1, t2, d5, t5, t9]
    assert merge_by_start([], [t2]) == [t2] and merge_by_start([d1], []) == [d1]


# --- The unified timeline: the expected rows --------------------------------------

def test_first_row_is_venus_jupiter_running_with_jupiter_mithuna_mars_mesha(rows):
    first = rows[0]
    assert isinstance(first.event, DashaEvent) and first.event.changed is None
    assert first.at == datetime(2026, 6, 1, tzinfo=IST)
    _assert_row(first, date(2026, 6, 1), jupiter=RashiId.GEMINI, mars=RashiId.ARIES)


def test_2_june_jupiter_enters_karka_mars_in_mesha(rows):
    _assert_row(_transit_row(rows, GrahaId.JUPITER, RashiId.CANCER), date(2026, 6, 2),
                jupiter=RashiId.CANCER, mars=RashiId.ARIES)


def test_21_june_mars_enters_vrishabha_jupiter_in_karka(rows):
    _assert_row(_transit_row(rows, GrahaId.MARS, RashiId.TAURUS), date(2026, 6, 21),
                jupiter=RashiId.CANCER, mars=RashiId.TAURUS)


def test_2_august_mars_enters_mithuna_jupiter_in_karka(rows):
    _assert_row(_transit_row(rows, GrahaId.MARS, RashiId.GEMINI), date(2026, 8, 2),
                jupiter=RashiId.CANCER, mars=RashiId.GEMINI)


def test_last_row_is_31_august_venus_jupiter_mars_mithuna_jupiter_karka(rows):
    last = rows[-1]
    assert last.event is None                                      # the window-end state
    _assert_row(last, date(2026, 8, 31), jupiter=RashiId.CANCER, mars=RashiId.GEMINI)


def test_every_transit_falls_inside_the_one_venus_jupiter_period(rows):
    assert len(rows) == 1 + 13 + 1                                 # opening dasha, transits, window end
    assert sum(isinstance(row.event, DashaEvent) for row in rows) == 1
    assert all((row.md, row.ad) == (GrahaId.VENUS, GrahaId.JUPITER) for row in rows)
    assert [row.at for row in rows] == sorted(row.at for row in rows)
    for row in rows:
        if isinstance(row.event, TransitEvent):
            assert row.rashis[row.event.planet] == row.event.to_rashi
