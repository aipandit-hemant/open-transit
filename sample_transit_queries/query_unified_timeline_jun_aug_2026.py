"""Query: one unified dasha + transit timeline, 1 Jun 2026 - 31 Aug 2026.

    python3 sample_transit_queries/query_unified_timeline_jun_aug_2026.py

Native: 24 Jun 1982, 00:45 IST, Betul (MP) -- Venus MD / Jupiter AD now.
Times are shown in IST (the native's zone); the window is 1 Jun 00:00 IST
through the whole of 31 Aug IST.

Three steps, each its own function:

1. flattened_antardasha()  MD/AD periods in the window (clipped to it)
2. rashi_change_transits() every planet's rashi ingress in the window (no Moon)
3. merge_by_start()        merge-sort of the two start-sorted lists

unified_timeline() turns the merged list into rows that each carry the
running MD/AD and every planet's rashi at that moment, and closes with a row
for the state at the end of 31 Aug.
"""
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chart import GrahaId, RashiId, pada_rashi
from planet_timeline import DashaEvent, TimelineEvent, TransitEvent, dasha_events, transit_events
from transit import TRANSIT_PLANET_CODES
from transit_pada import sidereal_longitude
from transit_pada_query import PLANET_CODES, load_planet_transits, row_at
from vimsottari import Vimsottari

DATA = Path(__file__).resolve().parent.parent / 'data'
PLANETS_CSV = DATA / 'transit_pada_planets_2026-05-01_2026-12-31.csv'

IST = ZoneInfo('Asia/Kolkata')
BIRTH = datetime(1982, 6, 24, 0, 45, tzinfo=IST)                       # Betul, MP
WINDOW_START = datetime(2026, 6, 1, tzinfo=IST)                       # 1 Jun 2026 00:00 IST
WINDOW_END = datetime(2026, 9, 1, tzinfo=IST)                         # exclusive: all of 31 Aug IST

#: Sanskrit rashi names (RashiId's own aliases), e.g. RashiId.GEMINI -> 'Mithuna'.
RASHI_NAMES = {rashi: next(name for name, member in RashiId.__members__.items()
                           if member is rashi and name != rashi.name).title()
               for rashi in RashiId}


def native_vimsottari() -> Vimsottari:
    return Vimsottari(sidereal_longitude('MON', BIRTH), BIRTH)


# --- 1. Flattened Antardasha periods -------------------------------------------

def flattened_antardasha(start: datetime = WINDOW_START, end: datetime = WINDOW_END) -> list[DashaEvent]:
    """Every MD/AD period overlapping [start, end), clipped to it, in start order."""
    return dasha_events(native_vimsottari(), start, end)


# --- 2. Transits selected by rashi change -------------------------------------

def rashi_change_transits(start: datetime = WINDOW_START, end: datetime = WINDOW_END, *,
                          planets_csv: Path = PLANETS_CSV) -> list[TransitEvent]:
    """Every planet's rashi ingress in [start, end) (Moon excluded), in start order."""
    return transit_events(load_planet_transits(planets_csv), start, end)


# --- 3. Merge sort by start date ------------------------------------------------

def merge_by_start(dasha: list[TimelineEvent], transits: list[TimelineEvent]) -> list[TimelineEvent]:
    """Merge step of merge sort: two start-sorted lists into one start-sorted list.

    On an equal start the dasha event comes first, so a dasha change is listed
    before the transits of the same instant.
    """
    merged, i, j = [], 0, 0
    while i < len(dasha) and j < len(transits):
        if dasha[i].time_range.start <= transits[j].time_range.start:
            merged.append(dasha[i])
            i += 1
        else:
            merged.append(transits[j])
            j += 1
    merged.extend(dasha[i:])
    merged.extend(transits[j:])
    return merged


# --- Unified timeline rows -----------------------------------------------------

@dataclass(frozen=True)
class TimelineRow:
    """The sky and the dasha at one moment of the unified timeline.

    ``event`` is what happened at ``at``: the DashaEvent (a dasha starts or is
    already running), the TransitEvent (a rashi ingress), or None for the
    closing row that records the state at the end of the window.
    """
    at: datetime
    event: TimelineEvent | None
    md: GrahaId
    ad: GrahaId
    rashis: dict[GrahaId, RashiId]

    def what(self) -> str:
        if isinstance(self.event, DashaEvent):
            change = self.event.changed.value if self.event.changed is not None else 'running'
            return f'dasha {change}: MD {self.md.value}, AD {self.ad.value}'
        if isinstance(self.event, TransitEvent):
            motion = ' (retrograde)' if self.event.retrograde else ''
            return (f'{self.event.planet.value} {RASHI_NAMES[self.event.from_rashi]} -> '
                    f'{RASHI_NAMES[self.event.to_rashi]}{motion}')
        return 'window end'

    def __str__(self) -> str:
        sky = ', '.join(f'{planet.value} {RASHI_NAMES[rashi]}' for planet, rashi in self.rashis.items())
        return (f'{self.at:%d %b %Y %H:%M:%S} IST | MD {self.md.value:<7} AD {self.ad.value:<7} | '
                f'{self.what():<40} | {sky}')


def _rashis_at(planets, moment: datetime) -> dict[GrahaId, RashiId]:
    row = row_at(planets, moment)
    return {TRANSIT_PLANET_CODES[code]: pada_rashi(int(row[code])) for code in PLANET_CODES}


def unified_timeline(start: datetime = WINDOW_START, end: datetime = WINDOW_END, *,
                     planets_csv: Path = PLANETS_CSV) -> list[TimelineRow]:
    """Merged dasha + transit rows over [start, end), closed by the state at its end.

    ``planets_csv`` must cover the window (default: the May-Dec 2026 file).
    """
    planets = load_planet_transits(planets_csv)
    merged = merge_by_start(flattened_antardasha(start, end),
                            rashi_change_transits(start, end, planets_csv=planets_csv))
    rows, running = [], None
    for event in merged:
        if isinstance(event, DashaEvent):
            running = event
        at = event.time_range.start.astimezone(IST)
        rows.append(TimelineRow(at, event, running.md, running.ad, _rashis_at(planets, at)))
    last_moment = (end - timedelta(seconds=1)).astimezone(IST)            # 31 Aug 23:59:59 IST
    rows.append(TimelineRow(last_moment, None, running.md, running.ad, _rashis_at(planets, last_moment)))
    return rows


if __name__ == '__main__':
    dasha = flattened_antardasha()
    transits = rashi_change_transits()
    print(f'1. Flattened Antardasha, {WINDOW_START:%d %b %Y} - 31 Aug 2026 (IST)')
    for event in dasha:
        print(f'    {event.time_range.start.astimezone(IST):%d %b %Y %H:%M} -> '
              f'{event.time_range.end.astimezone(IST):%d %b %Y %H:%M}  MD {event.md.value}, AD {event.ad.value}'
              f'{"  (running since before)" if event.time_range.starts_before else ""}'
              f'{"  (continues after)" if event.time_range.ends_after else ""}')
    print(f'\n2. Rashi-change transits ({len(transits)})')
    for event in transits:
        print(f'    {event.time_range.start.astimezone(IST):%d %b %Y %H:%M}  {event.planet.value:<8}'
              f'{RASHI_NAMES[event.from_rashi]} -> {RASHI_NAMES[event.to_rashi]}'
              f'{" (retrograde)" if event.retrograde else ""}')
    print('\n3. Unified timeline (merge-sorted by start)')
    for row in unified_timeline():
        print(f'    {row}')
