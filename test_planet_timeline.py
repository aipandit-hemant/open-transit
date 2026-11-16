"""Tests for the event timeline (planet_timeline.py): TimeRange, the
TimelineEvent protocol, DashaEvent / TransitEvent, and EventTimeline.

Test native: 24 Jun 1982, 00:45 IST, Betul (MP). Natal Moon in Pushya (lord
Saturn); running Venus Mahadasha / Jupiter Antardasha in Nov 2026.

Known dasha boundaries for this native (UTC):
    Venus MD        13 Sep 2014 21:54:08 -> 13 Sep 2034 21:54:08
    Venus/Jupiter   13 Nov 2024 06:54:08 -> 15 Jul 2027 06:54:08
    Venus/Saturn    15 Jul 2027 06:54:08 -> ...
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from chart import GrahaId, PadaTransitKind, RashiId
from planet_timeline import (DashaEvent, EventTimeline, TimeRange, TimelineEvent, TransitEvent,
                             build_event_timeline, dasha_events, transit_events)
from transit_pada import generate_pada_transit_csvs, sidereal_longitude
from transit_pada_query import load_planet_transits
from vimsottari import Vimsottari, VimsottariLevel

DATA = Path(__file__).resolve().parent / 'data'
PLANETS_2026_CSV = DATA / 'transit_pada_planets_2026-05-01_2026-12-31.csv'
PLANETS_2025_2027_CSV = DATA / 'transit_pada_planets_2025-2027.csv'

BIRTH = datetime(1982, 6, 24, 0, 45, tzinfo=ZoneInfo('Asia/Kolkata'))
MAY_TO_DEC_2026 = (date(2026, 5, 1), date(2027, 1, 1))
JUPITER_TO_SATURN_AD = datetime(2027, 7, 15, 6, 54, 8, 271257, tzinfo=timezone.utc)


def _utc(*parts) -> datetime:
    return datetime(*parts, tzinfo=timezone.utc)


@pytest.fixture(scope='module')
def native() -> Vimsottari:
    return Vimsottari(sidereal_longitude('MON', BIRTH), BIRTH)


@pytest.fixture
def timeline_2026(native) -> EventTimeline:
    return build_event_timeline(native, load_planet_transits(PLANETS_2026_CSV), *MAY_TO_DEC_2026)


@pytest.fixture(scope='module')
def timeline_2027(native) -> EventTimeline:
    return build_event_timeline(native, load_planet_transits(PLANETS_2025_2027_CSV),
                                date(2027, 1, 1), date(2028, 1, 1))


# --- TimeRange ----------------------------------------------------------------

def test_time_range_is_half_open_utc():
    span = TimeRange(datetime(2026, 1, 1, 5, 30, tzinfo=ZoneInfo('Asia/Kolkata')), date(2026, 1, 2))
    assert span.start == _utc(2026, 1, 1) and span.end == _utc(2026, 1, 2)
    assert span.contains(_utc(2026, 1, 1)) and not span.contains(_utc(2026, 1, 2))
    assert span.duration == timedelta(days=1)
    with pytest.raises(ValueError):
        TimeRange(_utc(2026, 1, 2), _utc(2026, 1, 1))


def test_time_range_clip_flags_the_cut_sides():
    window = TimeRange(_utc(2026, 5, 1), _utc(2027, 1, 1))
    clipped = TimeRange(_utc(2024, 11, 13), _utc(2027, 7, 15)).clip(window)
    assert (clipped.start, clipped.end) == (window.start, window.end)
    assert clipped.starts_before and clipped.ends_after
    inside = TimeRange(_utc(2026, 6, 1), _utc(2026, 7, 1)).clip(window)
    assert not inside.starts_before and not inside.ends_after


# --- Protocol and events ----------------------------------------------------

def test_dasha_and_transit_events_satisfy_the_timeline_event_protocol(timeline_2026):
    assert {type(event) for event in timeline_2026} == {DashaEvent, TransitEvent}
    assert all(isinstance(event, TimelineEvent) for event in timeline_2026)


def test_event_timeline_accepts_any_timeline_event_and_rejects_others():
    @dataclass(frozen=True)
    class EclipseEvent:                       # a new kind needs no timeline change
        time_range: TimeRange

        def get_details(self) -> dict:
            return {'event': 'eclipse', 'start': self.time_range.start}

    eclipse = EclipseEvent(TimeRange(_utc(2026, 8, 12), _utc(2026, 8, 13)))
    assert EventTimeline([eclipse]).get_next() is eclipse
    with pytest.raises(TypeError):
        EventTimeline(['not an event'])


def test_native_runs_venus_jupiter_in_november_2026(native):
    md, ad = native.at(_utc(2026, 11, 15), levels=2)
    assert (md.lord, ad.lord) == (GrahaId.VENUS, GrahaId.JUPITER)
    assert native.first_lord == GrahaId.SATURN                  # Pushya


def test_dasha_running_at_the_window_start_is_recorded_and_clipped(timeline_2026):
    [dasha] = timeline_2026.of_type(DashaEvent)
    assert (dasha.md, dasha.ad, dasha.changed) == (GrahaId.VENUS, GrahaId.JUPITER, None)
    assert (dasha.time_range.start, dasha.time_range.end) == (_utc(2026, 5, 1), _utc(2027, 1, 1))
    assert dasha.time_range.starts_before and dasha.time_range.ends_after
    assert timeline_2026.peek() is dasha


def test_transits_are_rashi_changes_only_and_never_the_moon(timeline_2026):
    transits = timeline_2026.of_type(TransitEvent)
    assert len(transits) == 34
    assert {t.changed for t in transits} == {PadaTransitKind.RASHI}
    assert GrahaId.MOON not in {t.planet for t in transits}
    assert all(t.from_rashi != t.to_rashi for t in transits)


def test_transit_events_match_the_known_ingresses(timeline_2026):
    by_key = {(t.planet, t.to_rashi): t for t in timeline_2026.of_type(TransitEvent)}
    jupiter_cancer = by_key[(GrahaId.JUPITER, RashiId.CANCER)].time_range
    assert (jupiter_cancer.start, jupiter_cancer.end) == (_utc(2026, 6, 1, 20, 54, 34), _utc(2026, 10, 31, 7, 20, 15))
    mars_leo = by_key[(GrahaId.MARS, RashiId.LEO)].time_range
    assert mars_leo.start == _utc(2026, 11, 12, 15, 1, 29) and mars_leo.ends_after
    rahu, ketu = by_key[(GrahaId.RAHU, RashiId.CAPRICORN)], by_key[(GrahaId.KETU, RashiId.CANCER)]
    assert rahu.time_range.start == ketu.time_range.start and rahu.retrograde and ketu.retrograde
    events = list(timeline_2026)
    assert events.index(ketu) == events.index(rahu) + 1          # same instant: file order SUN..RAH, KET


# --- EventTimeline cursor and queries -----------------------------------------

def test_get_next_walks_every_event_in_time_order(timeline_2026):
    walked = []
    while timeline_2026.has_next():
        walked.append(timeline_2026.get_next())
    assert walked == list(timeline_2026) and len(walked) == len(timeline_2026) == 35
    assert [e.time_range.start for e in walked] == sorted(e.time_range.start for e in walked)
    assert timeline_2026.get_next() is None and timeline_2026.cursor == 35
    timeline_2026.reset()
    assert timeline_2026.cursor == 0 and timeline_2026.get_next() is walked[0]


def test_add_merges_events_after_the_cursor_and_keeps_consumed_ones_consumed(timeline_2026):
    consumed = timeline_2026.get_next()
    upcoming = timeline_2026.peek()
    extra = DashaEvent(TimeRange(_utc(2026, 5, 2), _utc(2026, 5, 3)), GrahaId.SUN, GrahaId.SUN)
    timeline_2026.add([extra])
    assert timeline_2026.peek() is extra and timeline_2026.get_next() is extra
    assert timeline_2026.get_next() is upcoming
    earlier = DashaEvent(TimeRange(_utc(2026, 4, 1), _utc(2026, 4, 2)), GrahaId.SUN, GrahaId.SUN)
    timeline_2026.add([earlier])                                  # before what was consumed: not replayed
    assert timeline_2026.events[0] is earlier and timeline_2026.events[1] is consumed
    assert timeline_2026.peek() is not earlier


def test_active_at_relates_transits_to_the_running_dasha(timeline_2027):
    for transit in timeline_2027.of_type(TransitEvent):
        [running] = timeline_2027.active_at(transit.time_range.start, DashaEvent)
        assert running.ad == (GrahaId.JUPITER if transit.time_range.start < JUPITER_TO_SATURN_AD
                              else GrahaId.SATURN)


def test_antardasha_change_is_recorded(timeline_2027):
    first, second = timeline_2027.of_type(DashaEvent)
    assert (first.changed, first.ad, first.time_range.end) == (None, GrahaId.JUPITER, JUPITER_TO_SATURN_AD)
    assert (second.changed, second.md, second.ad, second.time_range.start) == (
        VimsottariLevel.ANTARDASHA, GrahaId.VENUS, GrahaId.SATURN, JUPITER_TO_SATURN_AD)


def test_mahadasha_change_is_recorded_as_mahadasha(native, tmp_path):
    planets_csv, _ = generate_pada_transit_csvs(date(2034, 9, 1), date(2034, 10, 1), tmp_path)
    timeline = build_event_timeline(native, load_planet_transits(planets_csv),
                                    date(2034, 9, 1), date(2034, 10, 1))
    before, after = timeline.of_type(DashaEvent)
    assert (before.md, before.ad, before.changed) == (GrahaId.VENUS, GrahaId.KETU, None)
    assert (after.md, after.ad, after.changed) == (GrahaId.SUN, GrahaId.SUN, VimsottariLevel.MAHADASHA)
    assert after.time_range.start == datetime(2034, 9, 13, 21, 54, 8, 271257, tzinfo=timezone.utc)


def test_an_ad_starting_on_the_window_start_is_a_change(native):
    [event] = dasha_events(native, JUPITER_TO_SATURN_AD, JUPITER_TO_SATURN_AD + timedelta(days=1))
    assert event.changed == VimsottariLevel.ANTARDASHA and not event.time_range.starts_before


def test_window_must_lie_inside_the_transit_file(native):
    planets = load_planet_transits(PLANETS_2026_CSV)
    with pytest.raises(ValueError):
        transit_events(planets, date(2026, 4, 1), date(2026, 6, 1))
    with pytest.raises(ValueError):
        build_event_timeline(native, planets, date(2026, 6, 1), date(2026, 6, 1))


def test_to_frame_has_one_row_of_details_per_event(timeline_2026):
    frame = timeline_2026.to_frame()
    assert len(frame) == 35
    assert list(frame.columns[:4]) == ['event', 'start', 'end', 'changed']
    assert list(frame['event'].iloc[:2]) == ['dasha', 'transit']
    assert set(frame['changed'].iloc[1:]) == {'rashi'}
