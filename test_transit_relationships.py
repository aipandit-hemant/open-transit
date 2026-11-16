"""Fixture-driven tests for the transit relationship column and its APIs.

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
    Moon and Saturn        - Aspecting each other (skipped: Moon relationships
                             are not recorded in the transit CSV)
"""
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from chart import GrahaId, RashiId, SambandhaType, rashi_sambandhas
from transit import (GRAHA_TO_TRANSIT_CODE, TransitFilter, TransitRelationship,
                     derive_relationships, format_relationships, parse_relationships)
from transit_dataframe import transit_relationships_at
from transit_repository import CsvTransitRepository

TRANSIT_CSV = Path(__file__).resolve().parent / 'transit_v3.csv'

NOV_12_2026 = datetime(2026, 11, 12, 0, 0, tzinfo=timezone.utc)
DEC_31_2026 = datetime(2026, 12, 31, 0, 0, tzinfo=timezone.utc)

# Each expectation: (sambandha, {(planet, rashi), (planet, rashi)}) -- direction-free.
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
]

FIXTURES = [
    pytest.param(NOV_12_2026, EXPECTED_NOV_12, id='2026-11-12T00:00Z'),
    pytest.param(DEC_31_2026, EXPECTED_DEC_31, id='2026-12-31T00:00Z'),
]


@pytest.fixture(scope='module')
def repository() -> CsvTransitRepository:
    return CsvTransitRepository(TRANSIT_CSV)


def _pair_keys_from_dicts(records):
    return {(SambandhaType(r['relationship']),
             frozenset({(r['source'], RashiId(r['source_rashi'])),
                        (r['target'], RashiId(r['target_rashi']))}))
            for r in records}


def _pair_keys_from_relationships(relationships):
    return {(rel.type,
             frozenset({(GRAHA_TO_TRANSIT_CODE[rel.source], rel.source_rashi),
                        (GRAHA_TO_TRANSIT_CODE[rel.target], rel.target_rashi)}))
            for rel in relationships}


# --- CSV content -------------------------------------------------------------

def test_csv_has_relationship_column_for_every_row():
    frame = pd.read_csv(TRANSIT_CSV, low_memory=False)
    assert 'relationship' in frame.columns
    assert len(frame.columns) == 16
    # Every non-Moon cell must parse back into structured relationships.
    for value in frame.loc[frame.planet_name != 'MON', 'relationship'].dropna():
        for relationship in parse_relationships(value):
            assert isinstance(relationship, TransitRelationship)


def test_moon_rows_and_moon_relationships_are_skipped():
    frame = pd.read_csv(TRANSIT_CSV, low_memory=False)
    moon_cells = frame.loc[frame.planet_name == 'MON', 'relationship']
    assert (moon_cells.isna() | (moon_cells.astype(str).str.strip() == '')).all()
    sample = frame.loc[frame.planet_name != 'MON', 'relationship'].dropna().head(2000)
    for value in sample:
        for relationship in parse_relationships(value):
            assert not relationship.involves(GrahaId.MOON)


def test_relationship_cells_round_trip():
    frame = pd.read_csv(TRANSIT_CSV, low_memory=False)
    sample = frame.loc[frame.planet_name != 'MON', 'relationship'].dropna().head(500)
    for value in sample:
        assert format_relationships(parse_relationships(value)) == value


# --- Repository API (client-facing) ------------------------------------------

@pytest.mark.parametrize('instant, expected', FIXTURES)
def test_repository_relationships_match_fixture(repository, instant, expected):
    derived = _pair_keys_from_dicts(repository.get_relationships_at(instant))
    for sambandha, pair in expected:
        assert (sambandha, frozenset(pair)) in derived, f'missing {sambandha} for {sorted(pair)}'


@pytest.mark.parametrize('instant, expected', FIXTURES)
def test_dataframe_relationships_match_fixture(instant, expected):
    derived = _pair_keys_from_relationships(transit_relationships_at(instant))
    for sambandha, pair in expected:
        assert (sambandha, frozenset(pair)) in derived, f'missing {sambandha} for {sorted(pair)}'


def test_moon_saturn_aspect_not_recorded_on_dec_31(repository):
    """Moon-Saturn aspect each other on 31 Dec 2026 but Moon is skipped for now."""
    records = repository.get_relationships_at(DEC_31_2026)
    assert all('MON' not in (record['source'], record['target']) for record in records)


@pytest.mark.parametrize('instant', [NOV_12_2026, DEC_31_2026])
def test_derived_relationships_match_chart_detection(repository, instant):
    """The recorded column reproduces exactly what chart.py detects live."""
    frame = pd.read_csv(TRANSIT_CSV, low_memory=False)
    frame['start_at'] = pd.to_datetime(frame['start_at'], format='ISO8601', utc=True)
    frame['end_at'] = pd.to_datetime(frame['end_at'], format='ISO8601', utc=True)
    when = pd.Timestamp(instant)
    active = frame[(frame.start_at <= when) & (frame.end_at > when)]
    code_to_graha = {code: graha for graha, code in GRAHA_TO_TRANSIT_CODE.items()}
    sign_by_graha = {code_to_graha[row.planet_name]: RashiId(int(row.rashi))
                     for row in active.itertuples(index=False)}
    live = {(stype, frozenset({(GRAHA_TO_TRANSIT_CODE[a], sign_by_graha[a]),
                               (GRAHA_TO_TRANSIT_CODE[b], sign_by_graha[b])}))
            for stype, a, b in rashi_sambandhas(sign_by_graha, exclude=[GrahaId.MOON])}
    recorded = _pair_keys_from_dicts(repository.get_relationships_at(instant))
    assert recorded == live


# --- Listing APIs keep working with the new column ----------------------------

def test_transit_rows_include_relationship_details(repository):
    filters = TransitFilter(start_date=NOV_12_2026.date(), end_date=NOV_12_2026.date(),
                            planet_names=['VEN'])
    page = repository.get_transit_rows(filters)
    assert page['count'] >= 1
    record = page['transits'][0]
    assert 'relationship' in record and 'relationships' in record
    entries = {(r['relationship'], r['source'], r['target']) for r in record['relationships']}
    assert ('EXCHANGE', 'VEN', 'MER') in entries or ('EXCHANGE', 'MER', 'VEN') in entries
    assert {'source_rashi_name', 'target_rashi_name'} <= set(record['relationships'][0])


def test_derive_relationships_prefers_later_starting_row():
    """A stale entry on an older row must not leak into the derived instant."""
    stale = TransitRelationship(SambandhaType.CONJUNCTION, GrahaId.SUN, RashiId.TULA,
                                GrahaId.MERCURY, RashiId.TULA)
    fresh = TransitRelationship(SambandhaType.EXCHANGE, GrahaId.MERCURY, RashiId.VRISCHIKA,
                                GrahaId.VENUS, RashiId.MEENA)  # placeholder signs
    older = {'start_at': pd.Timestamp('2026-01-01', tz='UTC'),
             'relationship': format_relationships([stale])}
    newer = {'start_at': pd.Timestamp('2026-01-10', tz='UTC'),
             'relationship': format_relationships([fresh])}
    derived = derive_relationships({'SUN': older, 'MER': newer, 'VEN': older})
    assert fresh.canonical() in derived
    assert stale.canonical() not in derived
