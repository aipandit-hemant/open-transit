"""Query the nakshatra-pada transit CSVs produced by transit_pada.py.

Reading rules
-------------
* Positions: a row's padas hold from its start until the next row, so the sky
  at any moment is the *last row starting at or before* that moment.
* Motion / combustion: a planet's ``retrograde`` / ``combust`` row holds until
  its ``direct`` / ``uncombust`` row. Loading replays these rows into
  ``<PLANET>_retrograde`` / ``<PLANET>_combust`` columns, so every loaded row is
  again a complete snapshot.
* Ketu: not stored in the file. Loading derives the ``KET`` column (Rahu's pada
  + 54) and Ketu's transit rows from Rahu's rows.

Typical use::

    planets = load_planet_transits(PLANETS_CSV)            # 1. SUN..RAH (+ derived KET)
    moon = load_moon_transits(MOON_CSV)                     # 2. Moon
    sky = sky_at(datetime(2026, 11, 12, tzinfo=UTC), planets, moon)   # 3. one row
    placements = pada_placements(sky)                       # 4. pada -> rashi/nakshatra
    relationships = detect_relationships(sky)               # 5. sambandhas

Astrological rules stay in chart.py (pada geometry, Ketu from Rahu,
sambandhas); this module only loads, filters, and maps CSV codes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

try:
    from domain.core.chart import (DignityType, FIVE_SAMBANDHAS, GrahaDignity, GrahaId, NakshatraId,
                                   PadaTransitKind, RashiId, SambandhaType, graha_dignity, ketu_pada,
                                   nakshatra_pada_index, nakshatra_padas, pada_in_nakshatra,
                                   pada_nakshatra, pada_rashi, pada_sambandhas, pada_transit_kind,
                                   rashi_padas)
    from domain.core.transit import TRANSIT_PLANET_CODES, TransitRelationship
except ImportError:  # Flat module layout (tests, standalone tooling)
    from chart import (DignityType, FIVE_SAMBANDHAS, GrahaDignity, GrahaId, NakshatraId,
                       PadaTransitKind, RashiId, SambandhaType, graha_dignity, ketu_pada,
                       nakshatra_pada_index, nakshatra_padas, pada_in_nakshatra, pada_nakshatra,
                       pada_rashi, pada_sambandhas, pada_transit_kind, rashi_padas)
    from transit import TRANSIT_PLANET_CODES, TransitRelationship


#: Pada columns stored in each file; Ketu is derived from Rahu on load.
PLANET_FILE_CODES: tuple[str, ...] = ('SUN', 'MAR', 'MER', 'JUP', 'VEN', 'SAT', 'RAH')
PLANET_CODES: tuple[str, ...] = ('SUN', 'MAR', 'MER', 'JUP', 'VEN', 'SAT', 'RAH', 'KET')
MOON_CODES: tuple[str, ...] = ('MON',)
ALL_CODES: tuple[str, ...] = ('SUN', 'MON', 'MAR', 'MER', 'JUP', 'VEN', 'SAT', 'RAH', 'KET')
_LEADING_COLUMNS = ['start_date', 'start_time', 'transit_planet', 'transit_type']

WINDOW_START, WINDOW_END = 'window_start', 'window_end'
RETROGRADE, DIRECT, COMBUST, UNCOMBUST = 'retrograde', 'direct', 'combust', 'uncombust'
POSITIONAL_TRANSITS = tuple(kind.value for kind in PadaTransitKind)   # rashi, nakshatra, pada
MOTION_TRANSITS = (RETROGRADE, DIRECT)
COMBUSTION_TRANSITS = (COMBUST, UNCOMBUST)


# =============================================================================
# Loading (steps 1 and 2)
# =============================================================================

def load_planet_transits(csv_path: Path | str, *, include_ketu: bool = True) -> pd.DataFrame:
    """Step 1: load the planets pada CSV (SUN..RAH) into a DataFrame.

    Adds the derived ``KET`` pada column and status columns; with
    ``include_ketu`` Ketu's transit rows are derived from Rahu's as well.
    """
    frame = _load_pada_csv(csv_path, PLANET_FILE_CODES)
    frame.insert(frame.columns.get_loc('RAH') + 1, 'KET',
                 frame['RAH'].map(ketu_pada).astype('int16'))
    if include_ketu:
        frame = _with_ketu_transits(frame)
    return _with_statuses(frame, PLANET_CODES)


def load_moon_transits(csv_path: Path | str) -> pd.DataFrame:
    """Step 2: load the Moon pada CSV (MON) into a DataFrame."""
    return _with_statuses(_load_pada_csv(csv_path, MOON_CODES), MOON_CODES)


def _load_pada_csv(csv_path: Path | str, codes: Sequence[str]) -> pd.DataFrame:
    expected = [*_LEADING_COLUMNS, *codes, 'timezone']
    frame = pd.read_csv(csv_path, dtype={**{c: 'string' for c in _LEADING_COLUMNS},
                                         **{code: 'int16' for code in codes}, 'timezone': 'string'})
    if list(frame.columns) != expected:
        raise ValueError(f'{csv_path}: expected columns {expected}, found {list(frame.columns)}')
    if frame.empty:
        raise ValueError(f'{csv_path}: no transit rows')
    for code in codes:
        if not frame[code].between(1, 108).all():
            raise ValueError(f'{csv_path}: {code} pada indexes must lie in 1..108')
    known = {WINDOW_START, WINDOW_END, *POSITIONAL_TRANSITS, *MOTION_TRANSITS, *COMBUSTION_TRANSITS}
    unknown = set(frame['transit_type']) - known
    if unknown:
        raise ValueError(f'{csv_path}: unknown transit_type values {sorted(unknown)}')
    frame['start_at'] = _start_instants(frame)
    if not frame['start_at'].is_monotonic_increasing:
        raise ValueError(f'{csv_path}: rows must be in chronological order')
    return frame


def _with_ketu_transits(frame: pd.DataFrame) -> pd.DataFrame:
    """Mirror each Rahu row as a Ketu row at the same moment.

    Ketu shares Rahu's motion and rashi ingresses, but never its nakshatra
    changes, so positional rows are re-typed from Ketu's own padas.
    """
    rahu = frame[frame['transit_planet'] == 'RAH']
    if rahu.empty:
        return frame
    ketu = rahu.copy()
    ketu['transit_planet'] = 'KET'
    for label, row in ketu[ketu['transit_type'].isin(POSITIONAL_TRANSITS)].iterrows():
        before = _pada_before(frame, row['start_at'], 'KET')
        ketu.loc[label, 'transit_type'] = pada_transit_kind(before, int(row['KET'])).value
    order = pd.Series(np.arange(len(frame), dtype=float), index=frame.index)
    ketu_order = order.loc[ketu.index] + 0.5           # directly after the matching Rahu row
    combined = pd.concat([frame, ketu])
    combined['_order'] = np.concatenate([order.to_numpy(), ketu_order.to_numpy()])
    return combined.sort_values('_order', kind='stable').drop(columns='_order').reset_index(drop=True)


def _with_statuses(frame: pd.DataFrame, codes: Sequence[str]) -> pd.DataFrame:
    """Replay motion/combustion rows into per-planet boolean status columns."""
    for code in codes:
        own = frame['transit_planet'] == code
        for column, on, off in ((f'{code}_retrograde', RETROGRADE, DIRECT),
                                (f'{code}_combust', COMBUST, UNCOMBUST)):
            events = frame['transit_type'].where(own).map({on: True, off: False})
            frame[column] = events.astype('boolean').ffill().fillna(False).astype(bool)
    return frame


def _pada_before(frame: pd.DataFrame, moment: pd.Timestamp, code: str) -> int:
    """``code``'s pada in force just before ``moment`` (or at it, for the first row)."""
    position = int(frame['start_at'].searchsorted(moment, side='left')) - 1
    return int(frame.iloc[max(position, 0)][code])


def _start_instants(frame: pd.DataFrame) -> pd.Series:
    """UTC instants of local start_date/start_time, resolving DST fall-back repeats."""
    naive = pd.to_datetime(frame['start_date'] + ' ' + frame['start_time'], format='%Y-%m-%d %H:%M:%S')
    instants = pd.Series(pd.NaT, index=frame.index, dtype='datetime64[ns, UTC]')
    for zone_name, rows in frame.groupby('timezone', sort=False).groups.items():
        local = naive.loc[rows]
        as_dst = local.dt.tz_localize(zone_name, ambiguous=np.ones(len(local), dtype=bool)).dt.tz_convert('UTC')
        as_std = local.dt.tz_localize(zone_name, ambiguous=np.zeros(len(local), dtype=bool)).dt.tz_convert('UTC')
        resolved = as_dst.dt.tz_localize(None).to_numpy(dtype='datetime64[ns]').copy()
        standard = as_std.dt.tz_localize(None).to_numpy(dtype='datetime64[ns]')
        # A repeated wall-clock time is its first (DST) pass unless that would run backwards.
        for position in np.flatnonzero(resolved != standard):
            if position > 0 and resolved[position] < resolved[position - 1]:
                resolved[position] = standard[position]
        instants.loc[rows] = pd.DatetimeIndex(resolved).tz_localize('UTC')
    return instants


# =============================================================================
# Pada <-> rashi / nakshatra utilities
# =============================================================================

def resolve_rashi(rashi: RashiId | int | str) -> RashiId:
    """Accept RashiId, 1..12, or an English/Sanskrit name ('Leo', 'Simha')."""
    if isinstance(rashi, str):
        return RashiId[rashi.strip().upper().replace(' ', '_')]
    return RashiId(int(rashi))


def resolve_nakshatra(nakshatra: NakshatraId | int | str) -> NakshatraId:
    """Accept NakshatraId, 1..27, or a name ('Magha', 'Purva Phalguni')."""
    if isinstance(nakshatra, str):
        return NakshatraId[nakshatra.strip().upper().replace(' ', '_').replace('-', '_')]
    return NakshatraId(int(nakshatra))


def padas_for_rashi(rashi: RashiId | int | str) -> range:
    """Zodiac-wide padas (1..108) of a rashi: padas_for_rashi('Simha') -> 37..45."""
    return rashi_padas(resolve_rashi(rashi))


def padas_for_nakshatra(nakshatra: NakshatraId | int | str, quarter: int | None = None) -> range:
    """Zodiac-wide padas of a nakshatra, or of one of its quarters (1..4)."""
    nakshatra = resolve_nakshatra(nakshatra)
    if quarter is None:
        return nakshatra_padas(nakshatra)
    pada = nakshatra_pada_index(nakshatra, quarter)
    return range(pada, pada + 1)


@dataclass(frozen=True)
class PadaPlacement:
    """Where one planet stands, described from its zodiac-wide pada."""
    planet: str
    pada: int
    retrograde: bool = False
    combust: bool = False

    @property
    def rashi(self) -> RashiId:
        return pada_rashi(self.pada)

    @property
    def nakshatra(self) -> NakshatraId:
        return pada_nakshatra(self.pada)

    @property
    def nakshatra_pada(self) -> int:
        return pada_in_nakshatra(self.pada)

    def to_dict(self) -> dict:
        return {'planet': self.planet, 'pada': self.pada,
                'rashi': int(self.rashi), 'rashi_name': self.rashi.name.title(),
                'nakshatra': int(self.nakshatra), 'nakshatra_name': self.nakshatra.nakshatra_name,
                'nakshatra_pada': self.nakshatra_pada,
                'retrograde': self.retrograde, 'combust': self.combust}

    def __str__(self) -> str:
        status = ''.join(f', {flag}' for flag, on in (('retrograde', self.retrograde),
                                                      ('combust', self.combust)) if on)
        return (f'{self.planet} in {self.rashi.name.title()}, {self.nakshatra.nakshatra_name} '
                f'pada {self.nakshatra_pada} (#{self.pada}){status}')


def place(planet: str, pada: int, *, retrograde: bool = False, combust: bool = False) -> PadaPlacement:
    return PadaPlacement(planet, int(pada), bool(retrograde), bool(combust))


# =============================================================================
# DataFrame queries
# =============================================================================

def _to_utc(moment: date | datetime) -> pd.Timestamp:
    if not isinstance(moment, datetime):
        moment = datetime.combine(moment, time())
    stamp = pd.Timestamp(moment)
    return stamp.tz_localize('UTC') if stamp.tzinfo is None else stamp.tz_convert('UTC')


def coverage(frame: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp | None]:
    """[first start, window end) of a loaded file; end is None without a window_end row."""
    last = frame.iloc[-1]
    return frame['start_at'].iloc[0], (last['start_at'] if last['transit_type'] == WINDOW_END else None)


def row_at(frame: pd.DataFrame, moment: date | datetime) -> pd.Series:
    """The row in force at ``moment``: the last row starting at or before it.

    Naive datetimes are read as UTC. Raises ValueError outside the file's coverage.
    """
    when = _to_utc(moment)
    first, end = coverage(frame)
    if when < first or (end is not None and when >= end):
        raise ValueError(f'{when.isoformat()} is outside the covered window '
                         f'[{first.isoformat()}, {end.isoformat() if end is not None else "..."})')
    position = int(frame['start_at'].searchsorted(when, side='right')) - 1
    return frame.iloc[position]


def sky_at(moment: date | datetime, planets: pd.DataFrame, moon: pd.DataFrame) -> pd.DataFrame:
    """Step 3: one-row DataFrame with all nine padas in force at ``moment``.

    Combines the row in force from the planets file with the row in force from
    the Moon file. ``retrograde`` / ``combust`` list the planets in that state;
    ``planets_since`` / ``moon_since`` are the two rows' starts.
    """
    when = _to_utc(moment)
    planet_row, moon_row = row_at(planets, when), row_at(moon, when)
    rows = {**{code: planet_row for code in PLANET_CODES}, **{code: moon_row for code in MOON_CODES}}
    record = {'at': when,
              **{code: int(rows[code][code]) for code in ALL_CODES},
              'retrograde': tuple(code for code in ALL_CODES if rows[code][f'{code}_retrograde']),
              'combust': tuple(code for code in ALL_CODES if rows[code][f'{code}_combust']),
              'planets_since': planet_row['start_at'], 'moon_since': moon_row['start_at']}
    return pd.DataFrame([record], columns=['at', *ALL_CODES, 'retrograde', 'combust',
                                           'planets_since', 'moon_since'])


def transits_between(frame: pd.DataFrame, start: date | datetime, end: date | datetime, *,
                     planet: str | None = None, transit_type: str | None = None) -> pd.DataFrame:
    """Recorded transits starting in [start, end), optionally for one planet/type.

    ``transit_type`` may be any CSV value (rashi, nakshatra, pada, retrograde,
    direct, combust, uncombust) or a group: ``'motion'`` (retrograde + direct),
    ``'combustion'`` (combust + uncombust). ``'nakshatra'`` also returns rashi
    ingresses that change nakshatra and ``'pada'`` every positional transit,
    because coarser transits include finer ones. The status rows restated when
    the window opens are not transits and are never returned.
    """
    opening = coverage(frame)[0]
    rows = frame[(frame['start_at'] >= _to_utc(start)) & (frame['start_at'] < _to_utc(end))
                 & (frame['start_at'] > opening) & (frame['transit_type'] != WINDOW_END)]
    if planet is not None:
        rows = rows[rows['transit_planet'] == planet]
    if transit_type is None:
        return rows
    if transit_type == 'nakshatra':
        return rows[rows['transit_type'].isin(['rashi', 'nakshatra']) & _changes_nakshatra(frame, rows)]
    groups = {'pada': POSITIONAL_TRANSITS, 'motion': MOTION_TRANSITS, 'combustion': COMBUSTION_TRANSITS,
              **{kind: (kind,) for kind in ('rashi', *MOTION_TRANSITS, *COMBUSTION_TRANSITS)}}
    if transit_type not in groups:
        raise ValueError(f'transit_type must be one of {sorted(groups)} or None')
    return rows[rows['transit_type'].isin(groups[transit_type])]


def status_periods(frame: pd.DataFrame, planet: str, status: str) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Spans during which ``planet`` is ``'retrograde'`` or ``'combust'`` within the file.

    Spans already running when the window opens start at the window start;
    spans still running at the window end stop there.
    """
    if status not in (RETROGRADE, COMBUST):
        raise ValueError("status must be 'retrograde' or 'combust'")
    flags = frame[f'{planet}_{status}']
    first, end = coverage(frame)
    periods, since = [], None
    for moment, on in frame.groupby('start_at', sort=True)[flags.name].last().items():
        if on and since is None:
            since = moment
        elif not on and since is not None:
            periods.append((since, moment))
            since = None
    if since is not None:
        periods.append((since, end if end is not None else frame['start_at'].iloc[-1]))
    return periods


def rashi_transits(frame: pd.DataFrame, start: date | datetime, end: date | datetime, *,
                   planets: Sequence[str] = PLANET_CODES) -> pd.DataFrame:
    """Rashi ingresses starting in [start, end), one row per planet ingress.

    Only ``transit_type == 'rashi'`` rows are used; the Moon is never included
    (pass the planets file). Columns: ``planet``, ``start_at``, ``end_at``
    (the planet's next rashi ingress, or the file's end -- then ``open_ended``
    is True: the planet is still in that rashi when the data stops), ``from_rashi``,
    ``to_rashi`` (rashi numbers 1..12; RashiId values), and ``retrograde`` at the ingress.
    """
    codes = [code for code in planets if code not in MOON_CODES]
    unknown = set(codes) - set(PLANET_CODES)
    if unknown:
        raise ValueError(f'rashi_transits takes planets out of {PLANET_CODES}; got {sorted(unknown)}')
    all_ingresses = frame[(frame['transit_type'] == PadaTransitKind.RASHI.value)
                          & frame['transit_planet'].isin(codes)]
    file_end = coverage(frame)[1] or frame['start_at'].iloc[-1]
    records = []
    for _, row in transits_between(frame, start, end, transit_type='rashi').iterrows():
        code = row['transit_planet']
        if code not in codes:
            continue
        later = all_ingresses.loc[(all_ingresses['transit_planet'] == code)
                                  & (all_ingresses['start_at'] > row['start_at']), 'start_at']
        records.append({'planet': code, 'start_at': row['start_at'],
                        'end_at': later.iloc[0] if not later.empty else file_end,
                        'open_ended': later.empty,
                        'from_rashi': pada_rashi(_pada_before(frame, row['start_at'], code)),
                        'to_rashi': pada_rashi(int(row[code])),
                        'retrograde': bool(row[f'{code}_retrograde'])})
    return pd.DataFrame(records, columns=['planet', 'start_at', 'end_at', 'open_ended', 'from_rashi',
                                          'to_rashi', 'retrograde'])


def _changes_nakshatra(frame: pd.DataFrame, rows: pd.DataFrame) -> pd.Series:
    """Does each transit row move its planet into another nakshatra?

    Compares with the sky before the row's instant: simultaneous rows (Rahu and
    Ketu) already carry each other's change.
    """
    flags = [pada_nakshatra(_pada_before(frame, row['start_at'], row['transit_planet']))
             != pada_nakshatra(int(row[row['transit_planet']]))
             for _, row in rows.iterrows()]
    return pd.Series(flags, index=rows.index, dtype=bool)


def rows_in_rashi(frame: pd.DataFrame, planet: str, rashi: RashiId | int | str) -> pd.DataFrame:
    """Rows during which ``planet`` stands in ``rashi`` (e.g. JUP in 'Simha')."""
    padas = padas_for_rashi(rashi)
    return frame[frame[planet].between(padas.start, padas.stop - 1)
                 & (frame['transit_type'] != WINDOW_END)]


def rows_in_nakshatra(frame: pd.DataFrame, planet: str, nakshatra: NakshatraId | int | str,
                      quarter: int | None = None) -> pd.DataFrame:
    """Rows during which ``planet`` stands in ``nakshatra`` (optionally one quarter)."""
    padas = padas_for_nakshatra(nakshatra, quarter)
    return frame[frame[planet].between(padas.start, padas.stop - 1)
                 & (frame['transit_type'] != WINDOW_END)]


# =============================================================================
# Relationships (steps 4 and 5)
# =============================================================================

def pada_placements(sky: pd.DataFrame | pd.Series) -> dict[str, PadaPlacement]:
    """Step 4a: each planet's pada mapped to its rashi and nakshatra, with its status.

    Works on a sky_at() snapshot (all nine planets) or any single CSV row.
    """
    row = sky.iloc[0] if isinstance(sky, pd.DataFrame) else sky
    return {code: place(code, row[code], retrograde=_has_status(row, code, RETROGRADE),
                        combust=_has_status(row, code, COMBUST))
            for code in ALL_CODES if code in row.index}


def _has_status(row: pd.Series, code: str, status: str) -> bool:
    if f'{code}_{status}' in row.index:          # a loaded CSV row
        return bool(row[f'{code}_{status}'])
    return status in row.index and code in row[status]   # a sky_at() snapshot


def detect_relationships(sky: pd.DataFrame | pd.Series, *,
                         types: Sequence[SambandhaType] | None = FIVE_SAMBANDHAS
                         ) -> list[TransitRelationship]:
    """Steps 4b and 5: sambandhas among all nine planets of one sky snapshot.

    Padas become rashi/nakshatra placements and chart.pada_sambandhas decides the
    relationships: by default the five sambandhas (exchange, conjunction, mutual
    aspect, occupies-and-aspects-lord, occupies-and-receives-lord-aspect); pass
    ``types=None`` to add Rahu/Ketu dispositors. Symmetric pairs appear once.
    """
    placements = pada_placements(sky)
    missing = [code for code in ALL_CODES if code not in placements]
    if missing:
        raise ValueError(f'Relationships need all nine planets; missing {missing} (use sky_at)')
    graha_padas = {TRANSIT_PLANET_CODES[code]: placement.pada for code, placement in placements.items()}
    found = {TransitRelationship(kind, source, pada_rashi(graha_padas[source]),
                                 target, pada_rashi(graha_padas[target])).canonical()
             for kind, source, target in pada_sambandhas(graha_padas, types=types)}
    return sorted(found, key=lambda relationship: relationship.sort_key)


@dataclass(frozen=True)
class RelationshipWindow:
    """A relationship and the span during which it holds.

    ``starts_before_coverage`` / ``ends_after_coverage`` flag spans cut by the
    loaded data: the relationship was already in force when the data begins or
    still in force when it ends, so the true start/end lies beyond the files.
    """
    relationship: TransitRelationship
    start: pd.Timestamp
    end: pd.Timestamp
    starts_before_coverage: bool = False
    ends_after_coverage: bool = False

    @property
    def duration(self) -> pd.Timedelta:
        return self.end - self.start

    def to_dict(self) -> dict:
        return {**self.relationship.to_dict(), 'from': self.start.isoformat(), 'until': self.end.isoformat(),
                'starts_before_coverage': self.starts_before_coverage,
                'ends_after_coverage': self.ends_after_coverage}


def _track_windows(planets: pd.DataFrame, moon: pd.DataFrame, moments: Sequence[pd.Timestamp],
                   until: pd.Timestamp, types: Sequence[SambandhaType] | None,
                   keep=lambda relationship: True) -> list[RelationshipWindow]:
    """Open and close relationship windows across consecutive sky snapshots."""
    open_windows: dict[TransitRelationship, pd.Timestamp] = {}
    closed: list[RelationshipWindow] = []
    for segment_start in moments:
        current = {relationship for relationship in
                   detect_relationships(sky_at(segment_start, planets, moon), types=types)
                   if keep(relationship)}
        for relationship in [r for r in open_windows if r not in current]:
            closed.append(RelationshipWindow(relationship, open_windows.pop(relationship), segment_start))
        for relationship in current:
            open_windows.setdefault(relationship, segment_start)
    closed.extend(RelationshipWindow(r, since, until) for r, since in open_windows.items())
    return sorted(closed, key=lambda window: (window.start, window.relationship.sort_key))


def relationships_on(day: date, planets: pd.DataFrame, moon: pd.DataFrame, *,
                     tz_name: str = 'UTC',
                     types: Sequence[SambandhaType] | None = FIVE_SAMBANDHAS) -> list[RelationshipWindow]:
    """Every relationship in force at any time on ``day`` (midnight to midnight in tz_name),
    each with the span of that day during which it holds."""
    zone = ZoneInfo(tz_name)
    day_start = _to_utc(datetime.combine(day, time(), zone))
    day_end = _to_utc(datetime.combine(day + timedelta(days=1), time(), zone))
    changes = pd.concat([planets['start_at'], moon['start_at']])
    moments = sorted({day_start, *changes[(changes > day_start) & (changes < day_end)]})
    return _track_windows(planets, moon, moments, day_end, types)


def relationship_periods(first_planet: str, second_planet: str, planets: pd.DataFrame,
                         moon: pd.DataFrame, start: date | datetime, end: date | datetime, *,
                         types: Sequence[SambandhaType] | None = FIVE_SAMBANDHAS) -> list[RelationshipWindow]:
    """Every period in which two planets are in a relationship at some time in [start, end).

    Periods carry their full start and end, also when these fall outside
    [start, end), as far as the loaded files reach (see the coverage flags).
    A planet pair may hold several relationship types at once; each type, with
    the rashis involved, is its own period.
    """
    codes = {first_planet, second_planet}
    if len(codes) != 2 or not codes <= set(ALL_CODES):
        raise ValueError(f'Need two different planets out of {ALL_CODES}')
    pair = {TRANSIT_PLANET_CODES[code] for code in codes}
    (planets_first, planets_end), (moon_first, moon_end) = coverage(planets), coverage(moon)
    data_start = max(planets_first, moon_first)
    data_end = min(e if e is not None else f['start_at'].iloc[-1]
                   for e, f in ((planets_end, planets), (moon_end, moon)))
    # A pair's sambandhas depend only on the pair's own placements, so only their
    # positional transits can open or close a period.
    changes = pd.concat([frame.loc[frame['transit_planet'].isin(codes)
                                   & frame['transit_type'].isin(POSITIONAL_TRANSITS), 'start_at']
                         for frame in (planets, moon)])
    moments = sorted({data_start, *changes[(changes > data_start) & (changes < data_end)]})
    windows = _track_windows(planets, moon, moments, data_end, types,
                             keep=lambda relationship: {relationship.source, relationship.target} == pair)
    query_start, query_end = _to_utc(start), _to_utc(end)
    return [RelationshipWindow(w.relationship, w.start, w.end,
                               starts_before_coverage=w.start == data_start,
                               ends_after_coverage=w.end == data_end)
            for w in windows if w.start < query_end and w.end > query_start]


# =============================================================================
# Planet states: exaltation, debilitation, own sign, Moolatrikona, Vargottama,
# and the Panchadha Maitri relation (Adhi Mitra .. Adhi Shatru)
# =============================================================================

@dataclass(frozen=True)
class DignityWindow:
    """One planet's sign-dignity and the span during which it holds.

    ``vargottama`` is independent of ``dignity`` (it can combine with any of
    them). ``starts_before_coverage`` / ``ends_after_coverage`` flag spans cut
    by the loaded data, as in RelationshipWindow.
    """
    planet: str
    dignity: DignityType
    rashi: RashiId
    vargottama: bool
    start: pd.Timestamp
    end: pd.Timestamp
    starts_before_coverage: bool = False
    ends_after_coverage: bool = False

    @property
    def duration(self) -> pd.Timedelta:
        return self.end - self.start

    def to_dict(self) -> dict:
        return {'planet': self.planet, 'dignity': self.dignity.value,
                'rashi': int(self.rashi), 'rashi_name': self.rashi.name.title(),
                'vargottama': self.vargottama, 'from': self.start.isoformat(),
                'until': self.end.isoformat(), 'starts_before_coverage': self.starts_before_coverage,
                'ends_after_coverage': self.ends_after_coverage}

    def __str__(self) -> str:
        tag = ', vargottama' if self.vargottama else ''
        return (f'{self.planet} {self.dignity.value} in {self.rashi.name.title()}{tag}: '
                f'{self.start.isoformat()} -> {self.end.isoformat()}')


def _graha_padas_at(moment: pd.Timestamp, planets: pd.DataFrame, moon: pd.DataFrame
                    ) -> dict[GrahaId, int]:
    row = sky_at(moment, planets, moon).iloc[0]
    return {TRANSIT_PLANET_CODES[code]: int(row[code]) for code in ALL_CODES}


def dignity_at(planet: str, moment: date | datetime, planets: pd.DataFrame,
               moon: pd.DataFrame) -> GrahaDignity:
    """``planet``'s sign dignity (see chart.graha_dignity) at one moment."""
    if planet not in ALL_CODES:
        raise ValueError(f'planet must be one of {ALL_CODES}')
    padas = _graha_padas_at(_to_utc(moment), planets, moon)
    return graha_dignity(TRANSIT_PLANET_CODES[planet], padas[TRANSIT_PLANET_CODES[planet]], padas)


def dignity_periods(planet: str, planets: pd.DataFrame, moon: pd.DataFrame,
                    start: date | datetime, end: date | datetime) -> list[DignityWindow]:
    """Every dignity window of ``planet`` touching [start, end).

    A window ends either because ``planet`` itself crosses into another rashi,
    or -- when its dignity is the Panchadha Maitri relation with its rashi's
    lord, rather than exaltation/debilitation/own-sign -- because that lord
    moves into a different rashi of its own. Both kinds of rashi change (of
    any of the nine grahas) are tracked so no dignity change is missed.
    """
    if planet not in ALL_CODES:
        raise ValueError(f'planet must be one of {ALL_CODES}')
    graha = TRANSIT_PLANET_CODES[planet]
    (planets_first, planets_end), (moon_first, moon_end) = coverage(planets), coverage(moon)
    data_start = max(planets_first, moon_first)
    data_end = min(e if e is not None else f['start_at'].iloc[-1]
                   for e, f in ((planets_end, planets), (moon_end, moon)))
    # Vargottama needs every sub-rashi move of ``planet`` itself (it tracks its
    # pada, not just its rashi); the rest of the dignity only needs rashi
    # changes -- its own, to re-rate exaltation/debilitation/own-sign/lord, or
    # the current lord's, to re-rate a Panchadha Maitri relation.
    own_frame = moon if planet in MOON_CODES else planets
    own_changes = own_frame.loc[(own_frame['transit_planet'] == planet)
                                & own_frame['transit_type'].isin(POSITIONAL_TRANSITS), 'start_at']
    lord_changes = pd.concat([frame.loc[frame['transit_type'] == 'rashi', 'start_at']
                              for frame in (planets, moon)])
    changes = pd.concat([own_changes, lord_changes])
    moments = sorted({data_start, *changes[(changes > data_start) & (changes < data_end)]})

    windows: list[DignityWindow] = []
    state: tuple | None = None
    since: pd.Timestamp | None = None
    for moment in moments:
        padas = _graha_padas_at(moment, planets, moon)
        dignity = graha_dignity(graha, padas[graha], padas)
        new_state = (dignity.type, pada_rashi(padas[graha]), dignity.is_vargottama)
        if new_state != state:
            if state is not None:
                windows.append(DignityWindow(planet, *state, since, moment))
            state, since = new_state, moment
    windows.append(DignityWindow(planet, *state, since, data_end))

    query_start, query_end = _to_utc(start), _to_utc(end)
    return [DignityWindow(w.planet, w.dignity, w.rashi, w.vargottama, w.start, w.end,
                          starts_before_coverage=w.start == data_start,
                          ends_after_coverage=w.end == data_end)
            for w in windows if w.start < query_end and w.end > query_start]


def filter_dignities(windows: Iterable[DignityWindow],
                     dignities: Sequence[DignityType]) -> list[DignityWindow]:
    """Keep only the windows whose dignity is one of ``dignities``."""
    wanted = set(dignities)
    return [window for window in windows if window.dignity in wanted]


# =============================================================================
# Interval algebra: combine RelationshipWindow / DignityWindow spans
# =============================================================================

def _as_period(window) -> tuple[pd.Timestamp, pd.Timestamp]:
    return window.start, window.end


def intersect_periods(first: Iterable, second: Iterable) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Every maximal span covered by both ``first`` and ``second``'s windows.

    Each argument is any iterable of objects with ``.start``/``.end`` (a
    RelationshipWindow or DignityWindow list, typically). Inputs need not be
    sorted or non-overlapping; the result is sorted and merged.
    """
    first_periods = sorted(_as_period(w) for w in first)
    second_periods = sorted(_as_period(w) for w in second)
    overlaps = []
    i = j = 0
    while i < len(first_periods) and j < len(second_periods):
        a_start, a_end = first_periods[i]
        b_start, b_end = second_periods[j]
        start, end = max(a_start, b_start), min(a_end, b_end)
        if start < end:
            overlaps.append((start, end))
        if a_end < b_end:
            i += 1
        else:
            j += 1
    return overlaps


def merge_touching(periods: Iterable[tuple[pd.Timestamp, pd.Timestamp]]
                   ) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Join spans that touch or overlap, e.g. after filtering away a finer detail
    (``dignity_periods`` also splits on Vargottama, which ``filter_dignities``
    does not care about) so consecutive same-kind windows read as one span."""
    merged: list[list[pd.Timestamp]] = []
    for start, end in sorted(periods):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def subtract_periods(first: Iterable, second: Iterable) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Every span covered by ``first``'s windows but by none of ``second``'s."""
    second_periods = sorted(_as_period(w) for w in second)
    remaining = []
    for start, end in sorted(_as_period(w) for w in first):
        cursor = start
        for b_start, b_end in second_periods:
            if b_end <= cursor or b_start >= end:
                continue
            if b_start > cursor:
                remaining.append((cursor, min(b_start, end)))
            cursor = max(cursor, b_end)
            if cursor >= end:
                break
        if cursor < end:
            remaining.append((cursor, end))
    return remaining
