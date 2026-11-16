"""Unified dasha + transit timeline across Antardasha changes, 1 Jun 2021 - 31 Aug 2026 (IST).

Native: 24 Jun 1982, 00:45 IST, Betul (MP), all inside Venus Mahadasha:

    Venus / Mars      running at 1 Jun 2021 (began 13 Sep 2020)
    Venus / Rahu      13 Nov 2021 18:24:08 IST   <- Antardasha change
    Venus / Jupiter   13 Nov 2024 12:24:08 IST   <- Antardasha change (runs past the window)

The merged view must agree with each list viewed on its own: the dasha
periods and the rashi transits appear unchanged and in order inside it, every
row carries the MD/AD the Vimshottari itself gives for that instant, and the
planets' rashis agree with the ephemeris.

Transit data: data/transit_pada_planets_2021-05-31_2026-09-01.csv, generated with
    python transit_pada.py --start 2021-05-31 --end 2026-09-02 --timezone UTC --label 2021-05-31_2026-09-01
"""
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from chart import GrahaId, RashiId, pada_rashi
from planet_timeline import DashaEvent, TransitEvent
from transit_pada import pada_at
from transit import TRANSIT_PLANET_CODES
from transit_pada_query import PLANET_CODES
from vimsottari import VimsottariLevel
from sample_transit_queries.query_unified_timeline_jun_aug_2026 import (
    IST, flattened_antardasha, native_vimsottari, rashi_change_transits, unified_timeline)

DATA = Path(__file__).resolve().parent / 'data'
PLANETS_2021_2026_CSV = DATA / 'transit_pada_planets_2021-05-31_2026-09-01.csv'
PLANETS_2025_2027_CSV = DATA / 'transit_pada_planets_2025-2027.csv'

START = datetime(2021, 6, 1, tzinfo=IST)
END = datetime(2026, 9, 1, tzinfo=IST)                                # exclusive: all of 31 Aug 2026
MARS_TO_RAHU = datetime(2021, 11, 13, 18, 24, 8, 271257, tzinfo=IST)
RAHU_TO_JUPITER = datetime(2024, 11, 13, 12, 24, 8, 271257, tzinfo=IST)


@pytest.fixture(scope='module')
def dasha():
    return flattened_antardasha(START, END)


@pytest.fixture(scope='module')
def transits():
    return rashi_change_transits(START, END, planets_csv=PLANETS_2021_2026_CSV)


@pytest.fixture(scope='module')
def rows():
    return unified_timeline(START, END, planets_csv=PLANETS_2021_2026_CSV)


# --- Dasha on its own ---------------------------------------------------------

def test_dasha_viewed_alone_has_the_two_antardasha_changes(dasha):
    assert [(d.md, d.ad, d.changed) for d in dasha] == [
        (GrahaId.VENUS, GrahaId.MARS, None),                              # carried in
        (GrahaId.VENUS, GrahaId.RAHU, VimsottariLevel.ANTARDASHA),
        (GrahaId.VENUS, GrahaId.JUPITER, VimsottariLevel.ANTARDASHA)]
    mars, rahu, jupiter = (d.time_range for d in dasha)
    assert (mars.start, mars.end) == (START, MARS_TO_RAHU)
    assert (rahu.start, rahu.end) == (MARS_TO_RAHU, RAHU_TO_JUPITER)
    assert (jupiter.start, jupiter.end) == (RAHU_TO_JUPITER, END)
    assert mars.starts_before and not mars.ends_after
    assert not rahu.starts_before and not rahu.ends_after
    assert not jupiter.starts_before and jupiter.ends_after             # Jupiter AD runs to Jul 2027


def test_dasha_periods_tile_the_window_without_gaps(dasha):
    assert dasha[0].time_range.start == START and dasha[-1].time_range.end == END
    for before, after in zip(dasha, dasha[1:]):
        assert before.time_range.end == after.time_range.start


# --- Transits on their own ------------------------------------------------------

def test_transits_viewed_alone_are_sorted_rashi_changes_without_the_moon(transits):
    assert len(transits) == 267
    assert [t.time_range.start for t in transits] == sorted(t.time_range.start for t in transits)
    assert GrahaId.MOON not in {t.planet for t in transits}
    assert all(t.from_rashi != t.to_rashi for t in transits)
    assert all(START <= t.time_range.start < END for t in transits)


def test_transits_agree_with_the_separately_generated_2025_2027_file(transits):
    overlap = (datetime(2025, 1, 2, tzinfo=IST), END)
    other = rashi_change_transits(*overlap, planets_csv=PLANETS_2025_2027_CSV)
    ours = [t for t in transits if overlap[0] <= t.time_range.start < overlap[1]]
    assert [(t.planet, t.from_rashi, t.to_rashi) for t in ours] == [
        (t.planet, t.from_rashi, t.to_rashi) for t in other]
    for mine, theirs in zip(ours, other):
        assert abs(mine.time_range.start - theirs.time_range.start) <= timedelta(seconds=5)


# --- Merged vs independent -------------------------------------------------------

def test_merged_timeline_holds_both_lists_unchanged_and_in_order(rows, dasha, transits):
    events = [row.event for row in rows[:-1]]
    assert rows[-1].event is None and len(rows) == len(dasha) + len(transits) + 1
    assert [e for e in events if isinstance(e, DashaEvent)] == dasha
    assert [e for e in events if isinstance(e, TransitEvent)] == transits
    assert [row.at for row in rows] == sorted(row.at for row in rows)
    # Merging must not move anything: each row sits at its own event's start.
    assert all(row.at == row.event.time_range.start for row in rows[:-1])
    assert rows[-1].at == END - timedelta(seconds=1)


def test_every_row_carries_the_md_ad_the_vimshottari_gives_for_that_instant(rows):
    vimsottari = native_vimsottari()
    for row in rows:
        md, ad = vimsottari.at(row.at, levels=2)
        assert (row.md, row.ad) == (md.lord, ad.lord), row


def test_every_row_has_the_planets_rashis_the_ephemeris_gives(rows):
    for row in rows:
        moment = row.at + timedelta(seconds=2)                       # clear of the rounded ingress second
        expected = {TRANSIT_PLANET_CODES[code]: pada_rashi(pada_at(code, moment)) for code in PLANET_CODES}
        assert row.rashis == expected, row


def test_transit_rows_flip_dasha_exactly_at_the_antardasha_changes(rows):
    for change, before_ad, after_ad in ((MARS_TO_RAHU, GrahaId.MARS, GrahaId.RAHU),
                                        (RAHU_TO_JUPITER, GrahaId.RAHU, GrahaId.JUPITER)):
        [index] = [i for i, row in enumerate(rows) if row.at == change]
        assert isinstance(rows[index].event, DashaEvent) and rows[index].event.changed == VimsottariLevel.ANTARDASHA
        assert isinstance(rows[index - 1].event, TransitEvent) and rows[index - 1].ad == before_ad
        assert isinstance(rows[index + 1].event, TransitEvent) and rows[index + 1].ad == after_ad
        assert all(row.ad == before_ad for row in rows[:index] if row.at >= change - timedelta(days=365))
        assert all(row.ad == after_ad for row in rows[index:] if row.at < change + timedelta(days=365))


def test_rows_around_the_changes(rows):
    def row_at(moment):
        [row] = [r for r in rows if r.at == moment]
        return row

    first = rows[0]
    assert (first.at, first.md, first.ad) == (START, GrahaId.VENUS, GrahaId.MARS)
    assert isinstance(first.event, DashaEvent) and first.event.changed is None
    rahu = row_at(MARS_TO_RAHU)
    assert (rahu.md, rahu.ad, rahu.rashis[GrahaId.JUPITER]) == (GrahaId.VENUS, GrahaId.RAHU, RashiId.CAPRICORN)
    jupiter = row_at(RAHU_TO_JUPITER)
    assert (jupiter.md, jupiter.ad, jupiter.rashis[GrahaId.JUPITER]) == (
        GrahaId.VENUS, GrahaId.JUPITER, RashiId.TAURUS)
    last = rows[-1]
    assert last.at.date() == date(2026, 8, 31) and (last.md, last.ad) == (GrahaId.VENUS, GrahaId.JUPITER)
    assert (last.rashis[GrahaId.JUPITER], last.rashis[GrahaId.MARS]) == (RashiId.CANCER, RashiId.GEMINI)


def test_jun_aug_2026_slice_matches_the_short_window_timeline(rows):
    """The same months built from the May-Dec 2026 file give the same transit rows."""
    short = unified_timeline()                                      # 1 Jun - 31 Aug 2026, other file
    slice_start = datetime(2026, 6, 1, tzinfo=IST)
    long_transits = [r for r in rows if isinstance(r.event, TransitEvent) and r.at >= slice_start]
    short_transits = [r for r in short if isinstance(r.event, TransitEvent)]
    assert [(r.event.planet, r.event.to_rashi, r.md, r.ad, r.rashis) for r in long_transits] == [
        (r.event.planet, r.event.to_rashi, r.md, r.ad, r.rashis) for r in short_transits]
    for mine, theirs in zip(long_transits, short_transits):
        assert abs(mine.at - theirs.at) <= timedelta(seconds=5)
    assert (rows[-1].md, rows[-1].ad, rows[-1].rashis) == (short[-1].md, short[-1].ad, short[-1].rashis)

