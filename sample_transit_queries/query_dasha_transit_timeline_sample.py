"""Query: merged Mahadasha/Antardasha + planet rashi-transit timeline for a native.

    python3 sample_transit_queries/query_dasha_transit_timeline_sample.py

Test native: born 24 Jun 1982, 00:45 IST, Betul (Madhya Pradesh). The natal
Moon (Pushya, lord Saturn) is taken from the same ephemeris/ayanamsa that built
the transit files (transit_pada.sidereal_longitude). As of Nov 2026 the native
runs Venus Mahadasha / Jupiter Antardasha.

Two windows are printed:

1. 1 May 2026 - 31 Dec 2026 (data/transit_pada_planets_2026-05-01_2026-12-31.csv):
   Venus/Jupiter runs through the whole window, so the only dasha entry is the
   one carried in, followed by every rashi ingress.
2. 1 Jan 2027 - 1 Jan 2028 (data/transit_pada_planets_2025-2027.csv): shows an
   Antardasha change, Jupiter -> Saturn on 15 Jul 2027.

The Moon's transits are never used.
"""
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from planet_timeline import DashaEvent, EventTimeline, TransitEvent, build_event_timeline
from transit_pada import sidereal_longitude
from transit_pada_query import load_planet_transits
from vimsottari import Vimsottari

DATA = Path(__file__).resolve().parent.parent / 'data'
PLANETS_2026_CSV = DATA / 'transit_pada_planets_2026-05-01_2026-12-31.csv'
PLANETS_2025_2027_CSV = DATA / 'transit_pada_planets_2025-2027.csv'

BIRTH = datetime(1982, 6, 24, 0, 45, tzinfo=ZoneInfo('Asia/Kolkata'))   # Betul, MP (IST)


def native_vimsottari(birth: datetime = BIRTH) -> Vimsottari:
    """Vimshottari of a native from the natal Moon's sidereal longitude."""
    return Vimsottari(sidereal_longitude('MON', birth), birth)


def dasha_transit_timeline(planets_csv: Path, start: date, end: date) -> EventTimeline:
    """Merged MD/AD + rashi-transit EventTimeline of the test native over [start, end)."""
    return build_event_timeline(native_vimsottari(), load_planet_transits(planets_csv), start, end)


def print_report(title: str, timeline: EventTimeline) -> None:
    print(f'{title} (times in UTC)\n')
    timeline.reset()
    while timeline.has_next():
        event = timeline.get_next()                  # a DashaEvent or a TransitEvent
        line = str(event)
        if isinstance(event, TransitEvent):
            # Transits know nothing about dashas; the timeline relates them.
            [running] = timeline.active_at(event.time_range.start, DashaEvent)
            line += f'   [MD {running.md.value} / AD {running.ad.value}]'
        if event.time_range.starts_before:
            line += '   (running since before the window)'
        elif event.time_range.ends_after:
            line += '   (continues after the window)'
        print(line)
    print(f'\n{len(timeline.of_type(DashaEvent))} dasha events, '
          f'{len(timeline.of_type(TransitEvent))} rashi transits\n')


if __name__ == '__main__':
    print_report('Dasha + transit timeline, 1 May 2026 - 31 Dec 2026',
                 dasha_transit_timeline(PLANETS_2026_CSV, date(2026, 5, 1), date(2027, 1, 1)))
    print_report('Dasha + transit timeline, 2027',
                 dasha_transit_timeline(PLANETS_2025_2027_CSV, date(2027, 1, 1), date(2028, 1, 1)))
