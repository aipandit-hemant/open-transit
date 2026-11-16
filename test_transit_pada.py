"""Tests for the nakshatra-pada transit CSVs: generation, reading rule, queries.

Fixture data (UTC):

12 Nov 2026, 00:00
    Sun and Mercury        - Conjunct              - Tula rashi
    Ketu and Jupiter       - Conjunction           - Simha rashi
    Rahu and Jupiter       - Aspecting each other  - Jupiter Simha, Rahu Kumbha
    Venus and Saturn       - Aspecting each other  - Venus Kanya, Saturn Meena
    Venus and Mercury      - Occupying each other's house - Venus Kanya, Mercury Tula

31 Dec 2026, 00:00
    Mars and Jupiter       - Conjunction in Simha rashi
    Sun and Mercury        - Conjunction in Dhanu rashi
    Sun and Jupiter        - Occupy each other's house - Sun Dhanu, Jupiter Simha
    Moon and Saturn        - Aspecting each other - Moon Kanya, Saturn Meena
"""
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from chart import (FIVE_SAMBANDHAS, NakshatraId, RashiId, SambandhaType, ketu_pada,
                   pada_in_nakshatra, pada_nakshatra, pada_rashi)
from transit import GRAHA_TO_TRANSIT_CODE
from transit_dataframe import transit_dataframe, transit_relationships_at
from transit_pada import (MOON_CSV_COLUMNS, PLANET_CSV_COLUMNS, generate_pada_transit_csvs,
                          is_combust, is_retrograde, pada_at)
from transit_pada_query import (ALL_CODES, PLANET_CODES, POSITIONAL_TRANSITS, coverage,
                                detect_relationships, load_moon_transits, load_planet_transits,
                                pada_placements, padas_for_nakshatra, padas_for_rashi,
                                relationship_periods, relationships_on, resolve_nakshatra,
                                resolve_rashi, row_at,
                                rows_in_nakshatra, rows_in_rashi, sky_at, status_periods,
                                transits_between)

DATA = Path(__file__).resolve().parent / 'data'
PLANETS_CSV = DATA / 'transit_pada_planets_2026-11.csv'
MOON_CSV = DATA / 'transit_pada_moon_2026-11.csv'

NOV_12_2026 = datetime(2026, 11, 12, tzinfo=timezone.utc)
DEC_31_2026 = datetime(2026, 12, 31, tzinfo=timezone.utc)
BOUNDARY_MARGIN = timedelta(seconds=5)  # ephemeris/rounding tolerance around a transit

EXPECTED_NOV_12 = [
    (SambandhaType.CONJUNCTION, {('SUN', RashiId.TULA), ('MER', RashiId.TULA)}),
    (SambandhaType.CONJUNCTION, {('KET', RashiId.SIMHA), ('JUP', RashiId.SIMHA)}),
    (SambandhaType.MUTUAL_ASPECT, {('RAH', RashiId.KUMBHA), ('JUP', RashiId.SIMHA)}),
    (SambandhaType.MUTUAL_ASPECT, {('VEN', RashiId.KANYA), ('SAT', RashiId.MEENA)}),
    (SambandhaType.EXCHANGE, {('VEN', RashiId.KANYA), ('MER', RashiId.TULA)}),
]
EXPECTED_DEC_31 = [
    (SambandhaType.CONJUNCTION, {('MAR', RashiId.SIMHA), ('JUP', RashiId.SIMHA)}),
    (SambandhaType.CONJUNCTION, {('SUN', RashiId.DHANU), ('MER', RashiId.DHANU)}),
    (SambandhaType.EXCHANGE, {('SUN', RashiId.DHANU), ('JUP', RashiId.SIMHA)}),
    (SambandhaType.MUTUAL_ASPECT, {('MON', RashiId.KANYA), ('SAT', RashiId.MEENA)}),
]


@pytest.fixture(scope='module')
def planets() -> pd.DataFrame:
    return load_planet_transits(PLANETS_CSV)


@pytest.fixture(scope='module')
def moon() -> pd.DataFrame:
    return load_moon_transits(MOON_CSV)


@pytest.fixture(scope='module')
def late_2026(tmp_path_factory):
    """Pada CSVs generated on the fly for 15 Sep - 31 Dec 2026.

    Covers every kind of status transit (Venus and Mercury go retrograde, enter
    and leave combustion; Saturn goes direct, Jupiter retrograde) and the
    31 Dec 2026 fixture.
    """
    planets_path, moon_path = generate_pada_transit_csvs(
        datetime(2026, 9, 15, tzinfo=timezone.utc), datetime(2027, 1, 1, tzinfo=timezone.utc),
        tmp_path_factory.mktemp('pada'), label='late-2026')
    return load_planet_transits(planets_path), load_moon_transits(moon_path)


def _pair_keys(relationships):
    return {(rel.type, frozenset({(GRAHA_TO_TRANSIT_CODE[rel.source], rel.source_rashi),
                                  (GRAHA_TO_TRANSIT_CODE[rel.target], rel.target_rashi)}))
            for rel in relationships}


def _random_instants(count, start, end, change_points, seed=7):
    """Random instants in [start, end) kept clear of every recorded transit."""
    rng, picked = random.Random(seed), []
    changes = sorted(change_points)
    while len(picked) < count:
        moment = start + (end - start) * rng.random()
        if all(abs(moment - change) > BOUNDARY_MARGIN for change in changes):
            picked.append(moment)
    return picked


# --- Generated November 2026 files --------------------------------------------

def test_generated_files_have_requested_columns():
    assert list(pd.read_csv(PLANETS_CSV, nrows=0).columns) == [
        'start_date', 'start_time', 'transit_planet', 'transit_type',
        'SUN', 'MAR', 'MER', 'JUP', 'VEN', 'SAT', 'RAH', 'timezone']
    assert list(pd.read_csv(PLANETS_CSV, nrows=0).columns) == PLANET_CSV_COLUMNS
    assert list(pd.read_csv(MOON_CSV, nrows=0).columns) == MOON_CSV_COLUMNS


def test_files_cover_november_2026_with_window_markers(planets, moon):
    for frame in (planets, moon):
        first, end = coverage(frame)
        assert first == pd.Timestamp('2026-11-01', tz='UTC')
        assert end == pd.Timestamp('2026-12-01', tz='UTC')
        assert frame['transit_type'].iloc[0] == 'window_start'
        assert frame['start_at'].is_monotonic_increasing
    assert set(planets['transit_type'].iloc[1:-1]) <= {
        'rashi', 'nakshatra', 'pada', 'retrograde', 'direct', 'combust', 'uncombust'}
    # The Moon is never retrograde or combust: only positional rows, ~every 6 hours.
    assert set(moon['transit_type'].iloc[1:-1]) <= set(POSITIONAL_TRANSITS)
    assert 110 <= len(moon) - 2 <= 125


def test_ketu_is_not_stored_but_derived_from_rahu(planets):
    raw = pd.read_csv(PLANETS_CSV)
    assert 'KET' not in raw.columns and 'KET' not in set(raw['transit_planet'])
    assert (planets['KET'] == planets['RAH'].map(ketu_pada)).all()
    rahu_rows = planets[planets['transit_planet'] == 'RAH']
    ketu_rows = planets[planets['transit_planet'] == 'KET']
    assert list(ketu_rows['start_at']) == list(rahu_rows['start_at'])
    assert planets['KET_retrograde'].iloc[-1] and not planets['KET_combust'].any()


def test_window_opens_by_restating_statuses_in_force(planets):
    opening = planets[planets['start_at'] == coverage(planets)[0]]
    restated = set(zip(opening['transit_planet'], opening['transit_type']))
    # 1 Nov 2026: Mercury retrograde and combust; Venus, Saturn, and the nodes retrograde.
    assert restated == {('ALL', 'window_start'), ('MER', 'retrograde'), ('MER', 'combust'),
                        ('VEN', 'retrograde'), ('SAT', 'retrograde'),
                        ('RAH', 'retrograde'), ('KET', 'retrograde')}
    listed = transits_between(planets, date(2026, 11, 1), date(2026, 12, 1), transit_type='motion')
    assert list(zip(listed['transit_planet'], listed['transit_type'])) == [('MER', 'direct'), ('VEN', 'direct')]


def test_each_row_changes_only_its_own_position(planets, moon):
    for frame, codes in ((planets, PLANET_CODES), (moon, ['MON'])):
        for position in range(1, len(frame) - 1):
            row = frame.iloc[position]
            if row['start_at'] == frame['start_at'].iloc[0]:
                continue  # opening block restates statuses
            before = {code: _pada_before(frame, row['start_at'], code) for code in codes}
            changed = [code for code in codes if row[code] != before[code]]
            if row['transit_type'] in POSITIONAL_TRANSITS:
                assert row['transit_planet'] in changed
                assert set(changed) <= {row['transit_planet'], 'RAH', 'KET'}  # nodes move together
            else:
                assert changed == []  # motion / combustion rows move nobody


def test_transit_type_names_the_coarsest_boundary(planets, moon):
    for frame in (planets, moon):
        for _, row in frame[frame['transit_type'].isin(POSITIONAL_TRANSITS)].iterrows():
            code = row['transit_planet']
            before, after = _pada_before(frame, row['start_at'], code), int(row[code])
            if pada_rashi(before) != pada_rashi(after):
                assert row['transit_type'] == 'rashi'
            elif pada_nakshatra(before) != pada_nakshatra(after):
                assert row['transit_type'] == 'nakshatra'
            else:
                assert row['transit_type'] == 'pada'


def _pada_before(frame, moment, code):
    position = int(frame['start_at'].searchsorted(moment, side='left')) - 1
    return int(frame.iloc[max(position, 0)][code])


# --- Reading rule: a row holds until the next row --------------------------------

def test_row_positions_hold_until_next_row(planets, moon):
    """At random instants the row in force equals the live ephemeris padas."""
    start, end = datetime(2026, 11, 1, tzinfo=timezone.utc), datetime(2026, 12, 1, tzinfo=timezone.utc)
    changes = [t.to_pydatetime() for t in pd.concat([planets['start_at'], moon['start_at']])]
    for moment in _random_instants(60, start, end, changes):
        sky = sky_at(moment, planets, moon).iloc[0]
        for code in ALL_CODES:
            assert sky[code] == pada_at(code, moment), (code, moment)
            assert (code in sky['retrograde']) == is_retrograde(code, moment), (code, moment)
            assert (code in sky['combust']) == is_combust(code, moment), (code, moment)


def test_between_two_rows_the_first_row_is_returned(planets):
    distinct = planets.drop_duplicates('start_at', keep='last')  # last row of each instant
    first, second = distinct.iloc[3], distinct.iloc[4]
    halfway = first['start_at'] + (second['start_at'] - first['start_at']) / 2
    assert row_at(planets, halfway).equals(first)
    assert row_at(planets, second['start_at'] - timedelta(seconds=1)).equals(first)
    assert row_at(planets, second['start_at']).equals(second)


def test_queries_outside_coverage_are_rejected(planets):
    with pytest.raises(ValueError):
        row_at(planets, datetime(2026, 10, 31, 23, 59, 59, tzinfo=timezone.utc))
    with pytest.raises(ValueError):
        row_at(planets, datetime(2026, 12, 1, tzinfo=timezone.utc))


def test_padas_agree_with_transit_v3_rashi_and_nakshatra(planets, moon):
    """Independent cross-check against the existing transit_v3.csv."""
    v3 = transit_dataframe()
    start, end = datetime(2026, 11, 1, tzinfo=timezone.utc), datetime(2026, 12, 1, tzinfo=timezone.utc)
    changes = [t.to_pydatetime() for t in pd.concat([planets['start_at'], moon['start_at']])]
    changes += [t.to_pydatetime() for t in v3.loc[(v3.start_at >= start) & (v3.start_at < end), 'start_at']]
    for moment in _random_instants(40, start, end, changes, seed=11):
        placements = pada_placements(sky_at(moment, planets, moon))
        active = v3[(v3.start_at <= moment) & (v3.end_at > moment)]
        for row in active.itertuples(index=False):
            placement = placements[row.planet_name]
            assert int(placement.rashi) == row.rashi, (row.planet_name, moment)
            assert int(placement.nakshatra) == row.nakshatra, (row.planet_name, moment)
            assert placement.retrograde == bool(row.retro_status), (row.planet_name, moment)
            assert placement.combust == bool(row.combustion_status), (row.planet_name, moment)


# --- Pada utilities ---------------------------------------------------------------

def test_every_pada_maps_to_one_rashi_and_nakshatra():
    for pada in range(1, 109):
        assert pada in padas_for_rashi(pada_rashi(pada))
        assert pada in padas_for_nakshatra(pada_nakshatra(pada))
        assert list(padas_for_nakshatra(pada_nakshatra(pada), pada_in_nakshatra(pada))) == [pada]
    assert sorted(p for r in RashiId for p in padas_for_rashi(r)) == list(range(1, 109))
    assert sorted(p for n in NakshatraId for p in padas_for_nakshatra(n)) == list(range(1, 109))


def test_rashi_and_nakshatra_names_resolve_to_padas():
    assert list(padas_for_rashi('Simha')) == list(padas_for_rashi('Leo')) == list(range(37, 46))
    assert list(padas_for_rashi(12)) == list(range(100, 109))
    assert list(padas_for_nakshatra('Magha')) == [37, 38, 39, 40]
    assert list(padas_for_nakshatra('Purva Phalguni', quarter=2)) == [42]
    assert resolve_rashi('tula') is RashiId.LIBRA
    assert resolve_nakshatra('Uttara Bhadrapada') is NakshatraId.UTTARA_BHADRAPADA


def test_rows_filtered_by_rashi_and_nakshatra(planets, moon):
    assert len(rows_in_rashi(planets, 'JUP', 'Simha')) == len(planets) - 1  # all November
    assert rows_in_rashi(planets, 'MAR', 'Simha')['start_at'].min() == \
        pd.Timestamp('2026-11-12 15:01:29', tz='UTC')
    jyeshtha = rows_in_nakshatra(moon, 'MON', 'Jyeshtha')
    assert set(jyeshtha['MON']) == {69, 70, 71, 72}


# --- Relationships from padas (fixture data) ------------------------------------

def test_sky_at_returns_one_row_with_all_nine_padas(planets, moon):
    sky = sky_at(NOV_12_2026, planets, moon)
    assert len(sky) == 1
    assert set(ALL_CODES) <= set(sky.columns)
    placements = pada_placements(sky)
    assert str(placements['JUP']) == 'JUP in Leo, Magha pada 1 (#37)'
    assert placements['SAT'].rashi is RashiId.MEENA


def test_relationships_on_12_nov_2026_match_fixture(planets, moon):
    detected = _pair_keys(detect_relationships(sky_at(NOV_12_2026, planets, moon)))
    for sambandha, pair in EXPECTED_NOV_12:
        assert (sambandha, frozenset(pair)) in detected, f'missing {sambandha} for {sorted(pair)}'


def test_relationships_on_31_dec_2026_match_fixture_including_moon(late_2026):
    planets, moon = late_2026
    detected = _pair_keys(detect_relationships(sky_at(DEC_31_2026, planets, moon)))
    for sambandha, pair in EXPECTED_DEC_31:
        assert (sambandha, frozenset(pair)) in detected, f'missing {sambandha} for {sorted(pair)}'


@pytest.mark.parametrize('instant', [NOV_12_2026, datetime(2026, 11, 20, 6, 30, tzinfo=timezone.utc)])
def test_pada_relationships_agree_with_transit_v3_column(planets, moon, instant):
    """Without the Moon, pada-based detection equals the recorded v3 relationships."""
    from_padas = {rel for rel in detect_relationships(sky_at(instant, planets, moon))
                  if not any(GRAHA_TO_TRANSIT_CODE[g] == 'MON' for g in (rel.source, rel.target))}
    from_v3 = {rel for rel in transit_relationships_at(instant) if rel.type in FIVE_SAMBANDHAS}
    assert _pair_keys(from_padas) == _pair_keys(from_v3)


def test_only_five_sambandha_types_by_default(planets, moon):
    sky = sky_at(NOV_12_2026, planets, moon)
    assert {rel.type for rel in detect_relationships(sky)} <= set(FIVE_SAMBANDHAS)
    assert SambandhaType.DISPOSITOR in {rel.type for rel in detect_relationships(sky, types=None)}


def test_relationships_during_12_nov_2026_include_mars_entering_simha(planets, moon):
    windows = relationships_on(date(2026, 11, 12), planets, moon)
    mars_jupiter = [w for w in windows if _pair_keys([w.relationship]) ==
                    {(SambandhaType.CONJUNCTION, frozenset({('MAR', RashiId.SIMHA), ('JUP', RashiId.SIMHA)}))}]
    assert len(mars_jupiter) == 1
    assert mars_jupiter[0].start == pd.Timestamp('2026-11-12 15:01:29', tz='UTC')
    assert mars_jupiter[0].end == pd.Timestamp('2026-11-13', tz='UTC')
    whole_day = [w for w in windows if w.start == pd.Timestamp('2026-11-12', tz='UTC')
                 and w.end == pd.Timestamp('2026-11-13', tz='UTC')]
    assert _pair_keys(w.relationship for w in whole_day) >= {
        (s, frozenset(p)) for s, p in EXPECTED_NOV_12}


# --- Simultaneous transits and timezones ------------------------------------------

def test_rahu_and_ketu_transit_together(late_2026):
    """5 Dec 2026: Rahu enters Makara mid-Dhanishta; Ketu enters Karka leaving Magha."""
    planets, _ = late_2026
    nodes = transits_between(planets, date(2026, 12, 5), date(2026, 12, 6), transit_type='pada')
    nodes = nodes[nodes['transit_planet'].isin(['RAH', 'KET'])]
    assert list(nodes['transit_planet']) == ['RAH', 'KET']
    assert nodes['start_at'].nunique() == 1
    assert nodes[['RAH', 'KET']].drop_duplicates().shape[0] == 1  # one consistent snapshot
    assert set(nodes['transit_type']) == {'rashi'}
    assert pada_rashi(int(nodes['KET'].iloc[0])) is RashiId.KARKA
    nakshatra_changes = transits_between(planets, date(2026, 12, 5), date(2026, 12, 6),
                                         transit_type='nakshatra')
    assert 'KET' in set(nakshatra_changes['transit_planet'])
    assert 'RAH' not in set(nakshatra_changes['transit_planet'])


def test_ketu_transit_type_is_derived_from_its_own_padas(tmp_path):
    """1 Aug 2026: Rahu changes nakshatra (pada 93 -> 92); Ketu only changes pada in Magha."""
    planets_path, _ = generate_pada_transit_csvs(date(2026, 8, 1), date(2026, 8, 2), tmp_path)
    planets = load_planet_transits(planets_path)
    nodes = transits_between(planets, date(2026, 8, 1), date(2026, 8, 2), transit_type='pada')
    nodes = nodes[nodes['transit_planet'].isin(['RAH', 'KET'])]
    assert list(zip(nodes['transit_planet'], nodes['transit_type'], nodes['RAH'], nodes['KET'])) == [
        ('RAH', 'nakshatra', 92, 38), ('KET', 'pada', 92, 38)]
    assert pada_nakshatra(38) is NakshatraId.MAGHA


# --- Motion and combustion transits -----------------------------------------------

def test_status_transits_match_transit_v3(late_2026):
    """Every retro/combust change in transit_v3.csv appears within seconds, and nothing else."""
    planets, _ = late_2026
    v3 = transit_dataframe()
    window = v3[(v3.start_at > pd.Timestamp('2026-09-15', tz='UTC'))
                & (v3.start_at < pd.Timestamp('2027-01-01', tz='UTC'))]
    expected = []
    for row in window[window.changed.fillna('').str.contains('retro_status')].itertuples():
        expected.append((row.planet_name, 'retrograde' if row.retro_status else 'direct', row.start_at))
    for row in window[window.changed.fillna('').str.contains('combustion_status')].itertuples():
        expected.append((row.planet_name, 'combust' if row.combustion_status else 'uncombust', row.start_at))
    recorded = transits_between(planets, date(2026, 9, 15), date(2027, 1, 1), transit_type='motion')
    recorded = pd.concat([recorded, transits_between(planets, date(2026, 9, 15), date(2027, 1, 1),
                                                     transit_type='combustion')])
    recorded = sorted(zip(recorded['transit_planet'], recorded['transit_type'], recorded['start_at']),
                      key=lambda item: item[2])
    expected.sort(key=lambda item: item[2])
    assert {(p, t) for p, t, _ in recorded} >= {('VEN', 'retrograde'), ('VEN', 'combust'),
                                                ('MER', 'combust'), ('SAT', 'direct'), ('JUP', 'retrograde')}
    assert [(p, t) for p, t, _ in recorded] == [(p, t) for p, t, _ in expected]
    for (_, _, ours), (_, _, theirs) in zip(recorded, expected):
        assert abs(ours - theirs) <= BOUNDARY_MARGIN


def test_status_periods_within_the_window(planets):
    assert status_periods(planets, 'MER', 'retrograde') == [
        (pd.Timestamp('2026-11-01', tz='UTC'), pd.Timestamp('2026-11-13 15:53:57', tz='UTC'))]
    assert status_periods(planets, 'MER', 'combust') == [
        (pd.Timestamp('2026-11-01', tz='UTC'), pd.Timestamp('2026-11-11 18:24:13', tz='UTC'))]
    assert status_periods(planets, 'KET', 'retrograde') == [
        (pd.Timestamp('2026-11-01', tz='UTC'), pd.Timestamp('2026-12-01', tz='UTC'))]
    assert status_periods(planets, 'JUP', 'combust') == []


def test_placements_report_motion_and_combustion(planets, moon):
    before = pada_placements(sky_at(datetime(2026, 11, 11, 18, 0, tzinfo=timezone.utc), planets, moon))
    after = pada_placements(sky_at(datetime(2026, 11, 11, 19, 0, tzinfo=timezone.utc), planets, moon))
    assert str(before['MER']) == 'MER in Libra, Swati pada 2 (#58), retrograde, combust'
    assert str(after['MER']) == 'MER in Libra, Swati pada 2 (#58), retrograde'
    assert not before['SUN'].retrograde and not before['MON'].combust


def test_local_timezone_files_describe_the_same_sky(tmp_path, planets, moon):
    kolkata = generate_pada_transit_csvs(date(2026, 11, 10), date(2026, 11, 14), tmp_path,
                                         tz_name='Asia/Kolkata')
    local_planets, local_moon = load_planet_transits(kolkata[0]), load_moon_transits(kolkata[1])
    assert set(local_planets['timezone']) == {'Asia/Kolkata'}
    assert local_planets['start_time'].iloc[0] == '05:30:00'
    for moment in [NOV_12_2026, datetime(2026, 11, 13, 9, 15, tzinfo=timezone.utc)]:
        columns = [*ALL_CODES, 'retrograde', 'combust']
        assert sky_at(moment, local_planets, local_moon)[columns].equals(
            sky_at(moment, planets, moon)[columns])


def test_repeated_local_times_at_dst_fall_back_are_ordered(tmp_path):
    """US clocks repeat 01:00-02:00 on 1 Nov 2026; the loader keeps rows chronological."""
    csv = tmp_path / 'moon_new_york.csv'
    csv.write_text(
        'start_date,start_time,transit_planet,transit_type,MON,timezone\n'
        '2026-11-01,00:00:00,ALL,window_start,28,America/New_York\n'
        '2026-11-01,01:30:00,MON,pada,29,America/New_York\n'   # first pass (EDT)
        '2026-11-01,01:10:00,MON,pada,30,America/New_York\n'   # second pass (EST)
        '2026-11-01,03:00:00,ALL,window_end,30,America/New_York\n')
    frame = load_moon_transits(csv)
    assert list(frame['start_at']) == [pd.Timestamp('2026-11-01 04:00', tz='UTC'),
                                       pd.Timestamp('2026-11-01 05:30', tz='UTC'),
                                       pd.Timestamp('2026-11-01 06:10', tz='UTC'),
                                       pd.Timestamp('2026-11-01 08:00', tz='UTC')]


# --- Relationship periods of a planet pair (MAR-JUP during 2026) ------------------

MULTI_YEAR_PLANETS_CSV = DATA / 'transit_pada_planets_2025-2027.csv'
MULTI_YEAR_MOON_CSV = DATA / 'transit_pada_moon_2025-2027.csv'
YEAR_2026 = (date(2026, 1, 1), date(2027, 1, 1))


@pytest.fixture(scope='module')
def years_2025_2027():
    return load_planet_transits(MULTI_YEAR_PLANETS_CSV), load_moon_transits(MULTI_YEAR_MOON_CSV)


@pytest.fixture(scope='module')
def mars_jupiter_2026(years_2025_2027):
    return relationship_periods('MAR', 'JUP', *years_2025_2027, *YEAR_2026)


def _mars_jupiter_in_v3(moment):
    return {rel.type for rel in transit_relationships_at(moment)
            if {GRAHA_TO_TRANSIT_CODE[rel.source], GRAHA_TO_TRANSIT_CODE[rel.target]} == {'MAR', 'JUP'}
            and rel.type in FIVE_SAMBANDHAS}


def _types_in_periods(periods, moment):
    return {p.relationship.type for p in periods if p.start <= moment < p.end}


def test_mars_jupiter_periods_in_2026(mars_jupiter_2026):
    spans = sorted({(p.start, p.end) for p in mars_jupiter_2026})
    assert [(s.date(), e.date()) for s, e in spans] == [
        (date(2025, 12, 7), date(2026, 1, 15)),   # Mars Dhanu opposite Jupiter Mithuna
        (date(2026, 4, 2), date(2026, 5, 11)),    # Mars Meena aspects its lord Jupiter
        (date(2026, 9, 18), date(2026, 10, 31)),  # conjunction in Karka
        (date(2026, 11, 12), date(2027, 1, 24)),  # conjunction in Simha
    ]
    assert {p.relationship.type for p in mars_jupiter_2026 if p.start.year == 2025} == {
        SambandhaType.MUTUAL_ASPECT, SambandhaType.OCCUPIES_AND_ASPECTS_LORD,
        SambandhaType.OCCUPIES_AND_RECEIVES_LORD_ASPECT}
    assert not any(p.starts_before_coverage or p.ends_after_coverage for p in mars_jupiter_2026)


def test_mars_jupiter_periods_agree_with_transit_v3(mars_jupiter_2026):
    """Around every boundary and at random 2026 instants the periods match the v3 column."""
    probe = [edge + offset for p in mars_jupiter_2026 for edge in (p.start, p.end)
             for offset in (-BOUNDARY_MARGIN, BOUNDARY_MARGIN)]
    edges = [edge.to_pydatetime() for p in mars_jupiter_2026 for edge in (p.start, p.end)]
    probe += [pd.Timestamp(t) for t in _random_instants(
        80, datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2027, 1, 1, tzinfo=timezone.utc), edges, seed=3)]
    for moment in probe:
        assert _types_in_periods(mars_jupiter_2026, moment) == _mars_jupiter_in_v3(moment), moment


def test_periods_cut_by_the_data_are_flagged(planets, moon):
    november_only = relationship_periods('JUP', 'MAR', planets, moon, date(2026, 11, 1), date(2026, 12, 1))
    assert [(p.relationship.type, p.start, p.end, p.ends_after_coverage) for p in november_only] == [
        (SambandhaType.CONJUNCTION, pd.Timestamp('2026-11-12 15:01:29', tz='UTC'),
         pd.Timestamp('2026-12-01', tz='UTC'), True)]


def test_relationship_periods_validate_the_pair(planets, moon):
    for pair in (('MAR', 'MAR'), ('MAR', 'PLUTO')):
        with pytest.raises(ValueError):
            relationship_periods(*pair, planets, moon, *YEAR_2026)


def test_periods_with_the_moon_use_moon_transits(planets, moon):
    moon_mars = relationship_periods('MON', 'MAR', planets, moon, date(2026, 11, 12), date(2026, 11, 13))
    exchange = [p for p in moon_mars if p.relationship.type is SambandhaType.EXCHANGE]
    assert len(exchange) == 1 and exchange[0].end == pd.Timestamp('2026-11-12 08:49:49', tz='UTC')
