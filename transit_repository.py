"""CSV readers for transit listings and Moon-transit lookup."""
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
import pandas as pd

try:
    from domain.core.transit import TransitFilter, derive_relationships, parse_relationships
except ImportError:  # Flat module layout (tests, standalone tooling)
    from transit import TransitFilter, derive_relationships, parse_relationships

class CsvMoonTransitRepository:

    def __init__(self, transit_csv_path: Path):
        df = pd.read_csv(transit_csv_path, dtype={'relationship': 'string'})
        df['start_dt'] = pd.to_datetime(df['start_date'] + ' ' + df['time'])
        self.transit_df = df

    def _build_filtered_df(self, changed_filter):
        df = self.transit_df
        if changed_filter == 'rashi':
            df = df[df['changed'].fillna('').str.contains('rashi')]
        elif changed_filter == 'nakshatra':
            df = df[df['changed'].fillna('').str.contains('nakshatra')]
        df = df.copy()
        df['end_dt'] = df['start_dt'].shift(-1)
        if not df.empty and df['end_dt'].isna().any():
            last_idx = df['end_dt'].isna()
            df.loc[last_idx, 'end_dt'] = pd.to_datetime(df.loc[last_idx, 'end_date']) + pd.Timedelta(hours=23, minutes=59, seconds=59)
        return df

    def get_transit_at(self, utc_dt, changed_filter='both'):
        if self.transit_df.empty:
            return None
        if changed_filter not in ('both', 'rashi', 'nakshatra'):
            raise ValueError("changed_filter must be 'both', 'rashi', or 'nakshatra'")
        df = self._build_filtered_df(changed_filter)
        mask = (df['start_dt'] <= utc_dt) & (df['end_dt'] > utc_dt)
        match = df[mask].head(1)
        if match.empty:
            return None
        row = match.iloc[0]
        return {'rashi': int(row['rashi']), 'start_dt': row['start_dt'].to_pydatetime(), 'end_dt': row['end_dt'].to_pydatetime()}

    def get_transit_for_local_date(self, local_date, tz_offset, changed_filter='both'):
        local_dt = local_date.replace(hour=0, minute=0, second=0, microsecond=0)
        utc_dt = local_dt - timedelta(hours=tz_offset)
        return self.get_transit_at(utc_dt, changed_filter=changed_filter)

class CsvTransitRepository:
    def __init__(self, csv_path: Path):
        self._dataframe = self._load_dataframe(csv_path)

    @staticmethod
    def _parse_iso_date(value: str) -> date:
        return datetime.strptime(value, '%Y-%m-%d').date()

    @staticmethod
    def _load_dataframe(csv_path: Path) -> pd.DataFrame:
        df = pd.read_csv(csv_path, dtype={'relationship': 'string'})
        df['planet_name'] = df['planet_name'].astype(str).str.upper()
        df['start_date'] = pd.to_datetime(df['start_date']).dt.date
        df['end_date'] = pd.to_datetime(df['end_date']).dt.date
        df['time'] = df['time'].astype(str)
        if 'start_at' in df.columns and 'end_at' in df.columns:
            df['start_at'] = pd.to_datetime(df['start_at'], format='ISO8601', utc=True)
            df['end_at'] = pd.to_datetime(df['end_at'], format='ISO8601', utc=True)
        return df
    @staticmethod
    def _to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for row in df.to_dict(orient='records'):
            relationship = row.get('relationship')
            if relationship is not None and pd.isna(relationship):
                relationship = None
            records.append({'planet_name': row.get('planet_name'), 'start_date': row.get('start_date').isoformat() if row.get('start_date') else None, 'end_date': row.get('end_date').isoformat() if row.get('end_date') else None, 'time': row.get('time'), 'rashi': int(row.get('rashi')) if row.get('rashi') is not None else None, 'nakshatra': int(row.get('nakshatra')) if row.get('nakshatra') is not None else None, 'retro_status': int(row.get('retro_status')) if row.get('retro_status') is not None else None, 'combustion_status': int(row.get('combustion_status')) if row.get('combustion_status') is not None else None, 'changed': row.get('changed'), 'relationship': relationship, 'relationships': [rel.to_dict() for rel in parse_relationships(relationship)]})
        return records

    def get_relationships_at(self, utc_dt: datetime) -> list[dict[str, Any]]:
        """Relationships among all transiting planets at one instant (Moon skipped).

        Reconstructed from the recorded relationship column of the rows active
        at ``utc_dt`` via transit.derive_relationships.
        """
        df = self._dataframe
        if 'start_at' not in df.columns or 'relationship' not in df.columns:
            raise ValueError('Transit CSV lacks start_at/relationship columns')
        when = pd.Timestamp(utc_dt)
        when = when.tz_localize('UTC') if when.tzinfo is None else when.tz_convert('UTC')
        active = df[(df['start_at'] <= when) & (df['end_at'] > when)]
        active_rows = {row['planet_name']: {'start_at': row['start_at'], 'relationship': row['relationship']}
                       for row in active.to_dict(orient='records')}
        return [rel.to_dict() for rel in derive_relationships(active_rows)]
    def get_transit_rows(self, filters: TransitFilter, skip: int=0, limit: int=100) -> dict[str, Any]:
        df = self._dataframe
        overlap_mask = (df['start_date'] <= filters.end_date) & (df['end_date'] >= filters.start_date)
        filtered = df[overlap_mask]
        if filters.planet_names:
            filtered = filtered[filtered['planet_name'].isin(filters.planet_names)]
        if filters.rashi_ids:
            filtered = filtered[filtered['rashi'].isin(filters.rashi_ids)]
        sort_column = 'end_date' if filters.sort_by_end_date else 'start_date'
        filtered = filtered.sort_values(by=[sort_column, 'time', 'rashi'], ascending=True)
        total = int(len(filtered))
        page_rows = filtered.iloc[skip:skip + limit]
        return {'transits': self._to_records(page_rows), 'count': int(len(page_rows)), 'total': total, 'page': skip // limit + 1, 'per_page': limit}
    def get_transits_for_next_month(self, reference_date: str | None=None) -> list[dict[str, Any]]:
        if reference_date:
            start_date = self._parse_iso_date(reference_date)
        else:
            start_date = datetime.now().date()
        start_ts = pd.Timestamp(start_date)
        end_ts = start_ts + pd.DateOffset(months=1)
        end_date = end_ts.date()
        df = self._dataframe
        window_mask = (df['start_date'] < end_date) & (df['end_date'] > start_date)
        filtered = df[window_mask].sort_values(by=['start_date', 'time', 'rashi'], ascending=True)
        return self._to_records(filtered)
