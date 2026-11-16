"""Generate nakshatra-pada transit CSVs with motion and combustion transits.

Two files are produced per window:

* planets CSV: ``start_date,start_time,transit_planet,transit_type,SUN,MAR,MER,JUP,VEN,SAT,RAH,timezone``
* moon CSV:    ``start_date,start_time,transit_planet,transit_type,MON,timezone``

Ketu is not stored: it is always opposite Rahu (Rahu's pada + 54), so
transit_pada_query derives its column and transits from Rahu.

Each row is one moment at which ``transit_planet`` makes a transit of
``transit_type``:

===============  ================================================================
``rashi``        enters a new rashi (coarsest boundary crossed, see below)
``nakshatra``    enters a new nakshatra within the same rashi
``pada``         enters a new pada within the same nakshatra
``retrograde``   stations retrograde (apparent geocentric speed turns negative)
``direct``       stations direct (speed turns positive)
``combust``      comes within its combustion orb of the Sun
``uncombust``    leaves its combustion orb
===============  ================================================================

The pada columns give every planet's zodiac-wide pada (1..108) from that
moment on, so a row's positions hold until the next row. Motion and
combustion status hold from their transit row until the planet's opposite
transit row.

The file opens with a ``window_start`` row (``transit_planet`` = ``ALL``),
followed at the same timestamp by one ``retrograde`` / ``combust`` row for each
planet that is already retrograde / combust when the window opens (absence means
direct / not combust). It closes with a ``window_end`` row. Dates and times are
local to ``timezone``.

Positions, stations, and combustion follow transit_v3.csv: Swiss Ephemeris,
LAHIRI_VP285, mean ayanamsa, apparent tropical minus ayanamsa, mean nodes;
stations from the apparent tropical speed; chart.COMBUSTION_ORBS.

Run::

    python3 transit_pada.py --start 2026-11-01 --end 2026-12-01 --timezone UTC --label 2026-11
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Hashable, Iterable, Sequence
from zoneinfo import ZoneInfo

import pandas as pd
import swisseph as swe

try:
    from domain.core.chart import (COMBUSTION_ORBS, is_combust_by_longitude,
                                   pada_from_longitude, pada_transit_kind)
    from domain.core.transit import TRANSIT_PLANET_CODES
except ImportError:  # Flat module layout (tests, standalone tooling)
    from chart import COMBUSTION_ORBS, is_combust_by_longitude, pada_from_longitude, pada_transit_kind
    from transit import TRANSIT_PLANET_CODES


PLANET_CODES: tuple[str, ...] = ('SUN', 'MAR', 'MER', 'JUP', 'VEN', 'SAT', 'RAH')
MOON_CODES: tuple[str, ...] = ('MON',)
PLANET_CSV_COLUMNS = ['start_date', 'start_time', 'transit_planet', 'transit_type',
                      *PLANET_CODES, 'timezone']
MOON_CSV_COLUMNS = ['start_date', 'start_time', 'transit_planet', 'transit_type',
                    *MOON_CODES, 'timezone']

WINDOW_START, WINDOW_END, ALL_PLANETS = 'window_start', 'window_end', 'ALL'
RETROGRADE, DIRECT = 'retrograde', 'direct'
COMBUST, UNCOMBUST = 'combust', 'uncombust'

EPHEMERIS_SOURCE = ('Swiss Ephemeris; LAHIRI_VP285; mean ayanamsa; '
                    'apparent tropical minus ayanamsa; mean nodes')

_SWISS_BODIES = {'SUN': swe.SUN, 'MON': swe.MOON, 'MAR': swe.MARS, 'MER': swe.MERCURY,
                 'JUP': swe.JUPITER, 'VEN': swe.VENUS, 'SAT': swe.SATURN, 'RAH': swe.MEAN_NODE}
_SCAN_STEP = timedelta(hours=1)        # far below the quickest change (Moon pada, ~6 h)
_RESOLUTION = timedelta(milliseconds=50)

swe.set_sid_mode(swe.SIDM_LAHIRI_VP285)


# --- Ephemeris ----------------------------------------------------------------

def _julian_day_ut(moment: datetime) -> float:
    moment = moment.astimezone(timezone.utc)
    hours = (moment.hour + moment.minute / 60 + moment.second / 3600
             + moment.microsecond / 3_600_000_000)
    return swe.julday(moment.year, moment.month, moment.day, hours)


def _apparent_tropical(code: str, jd_ut: float) -> tuple[float, float]:
    """(longitude, daily speed) in the apparent geocentric tropical frame."""
    position = swe.calc_ut(jd_ut, _SWISS_BODIES[code], swe.FLG_MOSEPH | swe.FLG_SPEED)[0]
    return position[0], position[3]


def sidereal_longitude(code: str, moment: datetime) -> float:
    """Apparent tropical longitude minus mean Lahiri (VP285) ayanamsa."""
    if code == 'KET':
        return (sidereal_longitude('RAH', moment) + 180.0) % 360.0
    jd_ut = _julian_day_ut(moment)
    return (_apparent_tropical(code, jd_ut)[0] - swe.get_ayanamsa_ut(jd_ut)) % 360.0


def pada_at(code: str, moment: datetime) -> int:
    return pada_from_longitude(sidereal_longitude(code, moment))


def is_retrograde(code: str, moment: datetime) -> bool:
    """Apparent geocentric motion is backwards (the mean nodes always are)."""
    return _apparent_tropical('RAH' if code == 'KET' else code, _julian_day_ut(moment))[1] < 0


def is_combust(code: str, moment: datetime) -> bool:
    graha = TRANSIT_PLANET_CODES[code]
    if graha not in COMBUSTION_ORBS:
        return False
    return is_combust_by_longitude(graha, sidereal_longitude(code, moment),
                                   sidereal_longitude('SUN', moment))


# --- Transit search -----------------------------------------------------------

@dataclass(frozen=True)
class PlanetTransit:
    """``planet`` makes a transit of ``transit_type`` at ``moment`` (UTC).

    ``to_pada`` is set for positional transits (rashi / nakshatra / pada).
    """
    moment: datetime
    planet: str
    transit_type: str
    to_pada: int | None = None


def _state_changes(state_at: Callable[[datetime], Hashable], start: datetime, end: datetime
                   ) -> list[tuple[datetime, Hashable, Hashable]]:
    """Every (moment, old, new) change of a piecewise-constant state in [start, end).

    Samples hourly and bisects each interval whose end-points differ, splitting
    further when several changes fall inside one interval. Moments are rounded
    to the second.
    """
    changes: list[tuple[datetime, Hashable, Hashable]] = []

    def refine(t0: datetime, s0: Hashable, t1: datetime, s1: Hashable) -> None:
        if s0 == s1:
            return
        if t1 - t0 <= _RESOLUTION:
            moment = _round_to_second(t1)
            if start <= moment < end:
                changes.append((moment, s0, s1))
            return
        mid = t0 + (t1 - t0) / 2
        s_mid = state_at(mid)
        refine(t0, s0, mid, s_mid)
        refine(mid, s_mid, t1, s1)

    t0, s0 = start, state_at(start)
    while t0 < end:
        t1 = min(t0 + _SCAN_STEP, end)
        s1 = state_at(t1)
        refine(t0, s0, t1, s1)
        t0, s0 = t1, s1
    return changes


def find_pada_transits(code: str, start: datetime, end: datetime) -> list[PlanetTransit]:
    """Every pada entry of one planet, typed by the coarsest boundary crossed."""
    return [PlanetTransit(moment, code, pada_transit_kind(old, new).value, new)
            for moment, old, new in _state_changes(lambda t: pada_at(code, t), start, end)]


def find_motion_transits(code: str, start: datetime, end: datetime) -> list[PlanetTransit]:
    """Every retrograde / direct station of one planet."""
    return [PlanetTransit(moment, code, RETROGRADE if now_retrograde else DIRECT)
            for moment, _, now_retrograde in _state_changes(lambda t: is_retrograde(code, t), start, end)]


def find_combustion_transits(code: str, start: datetime, end: datetime) -> list[PlanetTransit]:
    """Every entry into and exit from the Sun's combustion orb for one planet."""
    if TRANSIT_PLANET_CODES[code] not in COMBUSTION_ORBS:
        return []
    return [PlanetTransit(moment, code, COMBUST if now_combust else UNCOMBUST)
            for moment, _, now_combust in _state_changes(lambda t: is_combust(code, t), start, end)]


def find_transits(code: str, start: datetime, end: datetime) -> list[PlanetTransit]:
    return (find_pada_transits(code, start, end) + find_motion_transits(code, start, end)
            + find_combustion_transits(code, start, end))


def _round_to_second(moment: datetime) -> datetime:
    return (moment + timedelta(microseconds=500_000)).replace(microsecond=0)


# --- Row building ---------------------------------------------------------------

def _local_fields(moment: datetime, zone: ZoneInfo) -> tuple[str, str]:
    local = moment.astimezone(zone)
    return local.date().isoformat(), local.strftime('%H:%M:%S')


def _status_rows(codes: Sequence[str], moment: datetime) -> list[tuple[str, str]]:
    """(planet, transit_type) restating the non-default status of each planet."""
    rows = []
    for code in codes:
        if is_retrograde(code, moment):
            rows.append((code, RETROGRADE))
        if is_combust(code, moment):
            rows.append((code, COMBUST))
    return rows


def build_pada_transit_frame(codes: Sequence[str], start: datetime, end: datetime,
                             tz_name: str = 'UTC') -> pd.DataFrame:
    """Rows of pada, motion, and combustion transits for ``codes`` over [start, end).

    Transits sharing one instant each get a row that already carries every pada
    change of that instant, so any row is a consistent snapshot of positions.
    """
    start, end = _as_utc(start), _as_utc(end)
    if start >= end:
        raise ValueError('Generation window must have start < end')
    codes = tuple(codes)
    zone = ZoneInfo(tz_name)
    columns = ['start_date', 'start_time', 'transit_planet', 'transit_type', *codes, 'timezone']

    padas = {code: pada_at(code, start) for code in codes}
    opening = _local_fields(start, zone)
    rows = [[*opening, ALL_PLANETS, WINDOW_START, *padas.values(), tz_name]]
    rows += [[*opening, code, status, *padas.values(), tz_name] for code, status in _status_rows(codes, start)]

    transits = sorted((t for code in codes for t in find_transits(code, start, end)),
                      key=lambda t: (t.moment, codes.index(t.planet)))
    for moment, group in _group_by_moment(transits):
        for transit in group:
            if transit.to_pada is not None:
                padas[transit.planet] = transit.to_pada
        for transit in group:
            rows.append([*_local_fields(moment, zone), transit.planet, transit.transit_type,
                         *padas.values(), tz_name])

    _verify_final_state(codes, end, padas, transits, start)
    rows.append([*_local_fields(end, zone), ALL_PLANETS, WINDOW_END, *padas.values(), tz_name])
    return pd.DataFrame(rows, columns=columns)


def _verify_final_state(codes, end, padas, transits, start) -> None:
    """Replay every transit and compare with the ephemeris at the window end."""
    if [pada_at(code, end) for code in codes] != list(padas.values()):
        raise RuntimeError('Pada scan missed a transit; final positions do not match the ephemeris')
    for code in codes:
        retrograde, combust = is_retrograde(code, start), is_combust(code, start)
        for transit in (t for t in transits if t.planet == code):
            retrograde = {RETROGRADE: True, DIRECT: False}.get(transit.transit_type, retrograde)
            combust = {COMBUST: True, UNCOMBUST: False}.get(transit.transit_type, combust)
        if (retrograde, combust) != (is_retrograde(code, end), is_combust(code, end)):
            raise RuntimeError(f'Status scan missed a {code} transit before {end.isoformat()}')


def _group_by_moment(transits: Iterable[PlanetTransit]):
    group: list[PlanetTransit] = []
    for transit in transits:
        if group and transit.moment != group[0].moment:
            yield group[0].moment, group
            group = []
        group.append(transit)
    if group:
        yield group[0].moment, group


def _as_utc(moment: date | datetime) -> datetime:
    if not isinstance(moment, datetime):
        moment = datetime(moment.year, moment.month, moment.day)
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment.astimezone(timezone.utc)


def generate_pada_transit_csvs(start: date | datetime, end: date | datetime, out_dir: Path | str,
                               *, tz_name: str = 'UTC', label: str | None = None) -> tuple[Path, Path]:
    """Write the planets and the Moon pada CSVs for [start, end); returns both paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    label = label or f'{_as_utc(start):%Y-%m-%d}_{_as_utc(end):%Y-%m-%d}'
    planets_path = out_dir / f'transit_pada_planets_{label}.csv'
    moon_path = out_dir / f'transit_pada_moon_{label}.csv'
    build_pada_transit_frame(PLANET_CODES, start, end, tz_name).to_csv(planets_path, index=False)
    build_pada_transit_frame(MOON_CODES, start, end, tz_name).to_csv(moon_path, index=False)
    return planets_path, moon_path


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description='Generate nakshatra-pada transit CSVs.')
    parser.add_argument('--start', required=True, type=date.fromisoformat, help='UTC start date (inclusive)')
    parser.add_argument('--end', required=True, type=date.fromisoformat, help='UTC end date (exclusive)')
    parser.add_argument('--timezone', default='UTC', help='IANA zone for start_date/start_time')
    parser.add_argument('--out-dir', default=Path(__file__).resolve().parent / 'data', type=Path)
    parser.add_argument('--label', default=None, help='File name suffix, e.g. 2026-11')
    args = parser.parse_args(argv)
    for path in generate_pada_transit_csvs(args.start, args.end, args.out_dir,
                                           tz_name=args.timezone, label=args.label):
        print(f'Wrote {sum(1 for _ in open(path)) - 1} rows to {path}')


if __name__ == '__main__':
    main()
