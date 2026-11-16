"""Sample queries over the nakshatra-pada transit CSVs (November 2026).

    python3 transit_pada_samples.py

Query A - Which relationships are in force on 12 Nov 2026 (00:00 UTC)?
          Walks through the five steps one by one.
Query B - Which relationships are in force at any time on 12 Nov 2026,
          and during which hours?
Query C - Rashi/nakshatra questions answered through pada indexes:
          when is the Moon in Jyeshtha, where is Jupiter, which ingresses occur?
Query D - Motion and combustion: stations and combustion changes in November,
          which planets are retrograde or combust at a moment, and for how long.
"""
from datetime import date, datetime, timezone
from pathlib import Path

from transit_pada_query import (detect_relationships, load_moon_transits, load_planet_transits,
                                pada_placements, padas_for_nakshatra, padas_for_rashi,
                                relationships_on, rows_in_nakshatra, rows_in_rashi, sky_at,
                                status_periods, transits_between)

DATA = Path(__file__).resolve().parent / 'data'
PLANETS_CSV = DATA / 'transit_pada_planets_2026-11.csv'
MOON_CSV = DATA / 'transit_pada_moon_2026-11.csv'

TWELFTH_NOVEMBER_2026 = date(2026, 11, 12)
MIDNIGHT_UTC_12_NOV_2026 = datetime(2026, 11, 12, 0, 0, tzinfo=timezone.utc)


def describe(relationship) -> str:
    facts = relationship.to_dict()
    return (f"{facts['relationship']:<34} {facts['source_planet']} ({facts['source_rashi_name']})"
            f" & {facts['target_planet']} ({facts['target_rashi_name']})")


def query_a_relationships_at_midnight():
    print('Query A: relationships in force on 12 Nov 2026, 00:00 UTC')

    # 1. Read the eight-planet CSV into a DataFrame.
    eight_planets = load_planet_transits(PLANETS_CSV)
    # 2. Read the Moon CSV into a DataFrame.
    moon = load_moon_transits(MOON_CSV)
    # 3. One DataFrame row holding all nine padas in force at that moment.
    sky = sky_at(MIDNIGHT_UTC_12_NOV_2026, eight_planets, moon)
    print(sky.to_string(index=False))
    # 4. Each pada (1..108) mapped to its rashi and nakshatra ...
    for placement in pada_placements(sky).values():
        print('   ', placement)
    # ... and the five sambandhas among all nine planets decided from them.
    relationships = detect_relationships(sky)
    # 5. Return the detected relationships.
    for relationship in relationships:
        print('   ', describe(relationship))
    return relationships


def query_b_relationships_during_the_day():
    print('\nQuery B: every relationship in force at some time on 12 Nov 2026 (UTC day)')
    eight_planets, moon = load_planet_transits(PLANETS_CSV), load_moon_transits(MOON_CSV)
    windows = relationships_on(TWELFTH_NOVEMBER_2026, eight_planets, moon, tz_name='UTC')
    for window in windows:
        print(f'    {window.start:%d %b %H:%M:%S} -> {window.end:%d %b %H:%M:%S}  {describe(window.relationship)}')
    return windows


def query_c_rashi_and_nakshatra_lookups():
    print('\nQuery C: rashi / nakshatra questions answered through pada indexes')
    eight_planets, moon = load_planet_transits(PLANETS_CSV), load_moon_transits(MOON_CSV)

    print(f"    Simha spans padas {list(padas_for_rashi('Simha'))}; "
          f"Jyeshtha spans padas {list(padas_for_nakshatra('Jyeshtha'))}")

    moon_in_jyeshtha = rows_in_nakshatra(moon, 'MON', 'Jyeshtha')
    print('    Moon enters a Jyeshtha pada at:',
          ', '.join(f'{t:%d %b %H:%M}' for t in moon_in_jyeshtha['start_at']))

    jupiter_in_simha = rows_in_rashi(eight_planets, 'JUP', 'Simha')
    print(f'    Jupiter stands in Simha in {len(jupiter_in_simha)} of '
          f'{len(eight_planets) - 1} recorded November states')

    ingresses = transits_between(eight_planets, date(2026, 11, 1), date(2026, 12, 1), transit_type='rashi')
    for ingress in ingresses.itertuples():
        entered = pada_placements(eight_planets.loc[ingress.Index])[ingress.transit_planet]
        print(f'    {ingress.start_at:%d %b %Y %H:%M:%S} UTC  {entered}')
    return moon_in_jyeshtha, jupiter_in_simha, ingresses


def query_d_motion_and_combustion():
    print('\nQuery D: retrograde / direct stations and combustion in November 2026')
    eight_planets, moon = load_planet_transits(PLANETS_CSV), load_moon_transits(MOON_CSV)

    november = (date(2026, 11, 1), date(2026, 12, 1))
    for kind in ('motion', 'combustion'):
        for change in transits_between(eight_planets, *november, transit_type=kind).itertuples():
            print(f'    {change.start_at:%d %b %Y %H:%M:%S} UTC  {change.transit_planet} turns {change.transit_type}')

    sky = sky_at(MIDNIGHT_UTC_12_NOV_2026, eight_planets, moon)
    print(f"    On 12 Nov 00:00 UTC retrograde: {', '.join(sky['retrograde'].iloc[0]) or 'none'}; "
          f"combust: {', '.join(sky['combust'].iloc[0]) or 'none'}")

    for planet in ('MER', 'VEN'):
        for since, until in status_periods(eight_planets, planet, 'retrograde'):
            print(f'    {planet} retrograde {since:%d %b %H:%M} -> {until:%d %b %H:%M} (within this file)')
    for since, until in status_periods(eight_planets, 'MER', 'combust'):
        print(f'    MER combust {since:%d %b %H:%M} -> {until:%d %b %H:%M} (within this file)')


if __name__ == '__main__':
    query_a_relationships_at_midnight()
    query_b_relationships_during_the_day()
    query_c_rashi_and_nakshatra_lookups()
    query_d_motion_and_combustion()
