import json
from pathlib import Path

from sqlalchemy import func, inspect, insert, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .config import Settings
from .database import (
    approval_history, audit_logs, bins as bins_table, collections as collections_table,
    create_database_engine, events as events_table, forecasts as forecasts_table,
    metadata, readings as readings_table, routes as routes_table, users as users_table,
    vehicles as vehicles_table,
)
from .models import AgentEvent, Bin, Forecast, RoutePlan, SensorReading, Vehicle, utcnow


class Repository:
    """Cross-database repository; production schema is managed by Alembic."""

    def __init__(self, database_url: str | Path | None = None, *, initialize: bool = False, seed_data: bool = False):
        url = str(database_url) if database_url is not None else Settings.from_environment().database_url
        if '://' not in url:
            url = f'sqlite:///{Path(url).resolve().as_posix()}'
        elif url.startswith('postgres://'):
            url = 'postgresql+psycopg://' + url.removeprefix('postgres://')
        elif url.startswith('postgresql://'):
            url = 'postgresql+psycopg://' + url.removeprefix('postgresql://')
        self.engine = create_database_engine(url)
        self.dialect = self.engine.dialect.name
        if initialize:
            self.initialize_schema()
            if seed_data:
                self.seed()

    def initialize_schema(self):
        metadata.create_all(self.engine, checkfirst=True)

    def check_connection(self, *, require_migrations: bool = False):
        with self.engine.connect() as connection:
            connection.execute(select(func.count()).select_from(bins_table)).scalar_one()
            if require_migrations:
                table_names = set(inspect(connection).get_table_names())
                if 'alembic_version' not in table_names:
                    raise RuntimeError('Database migrations are missing; run `alembic upgrade head`.')
                from sqlalchemy import text
                revision = connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one_or_none()
                if revision != '20261015_0001':
                    raise RuntimeError('Database schema revision is not current; run `alembic upgrade head`.')
        return True

    def dispose(self):
        self.engine.dispose()

    def _upsert(self, table, values: dict, key: str):
        if self.dialect == 'sqlite':
            statement = sqlite_insert(table).values(**values)
        elif self.dialect == 'postgresql':
            statement = postgres_insert(table).values(**values)
        else:
            raise RuntimeError(f'Unsupported database dialect: {self.dialect}')
        changed = {name: value for name, value in values.items() if name != key}
        if changed:
            statement = statement.on_conflict_do_update(index_elements=[table.c[key]], set_=changed)
        else:
            statement = statement.on_conflict_do_nothing(index_elements=[table.c[key]])
        with self.engine.begin() as connection:
            connection.execute(statement)

    def seed(self):
        """Insert development samples only into an empty database; never delete or overwrite records."""
        sample_bins = [
            Bin(id='BIN-001', zone='Civic Square', latitude=19.076, longitude=72.877, waste_type='general', capacity_liters=1000, fill_percent=92, sensor_id='S-001'),
            Bin(id='BIN-003', zone='Market Street', latitude=19.079, longitude=72.881, waste_type='recyclable', capacity_liters=800, fill_percent=87, sensor_id='S-003'),
            Bin(id='BIN-004', zone='North Campus', latitude=19.083, longitude=72.875, waste_type='organic', capacity_liters=750, fill_percent=96, sensor_id='S-004'),
            Bin(id='BIN-006', zone='Riverside Park', latitude=19.071, longitude=72.883, waste_type='general', capacity_liters=1000, fill_percent=78, sensor_id='S-006'),
            Bin(id='BIN-008', zone='Station Road', latitude=19.074, longitude=72.889, waste_type='general', capacity_liters=900, fill_percent=63, sensor_status='stale', sensor_id='S-008'),
        ]
        sample_vehicles = [
            Vehicle(id='TRUCK-01', capacity_liters=8000, supported_waste=['general', 'recyclable'], latitude=19.072, longitude=72.876),
            Vehicle(id='TRUCK-02', capacity_liters=5000, supported_waste=['organic'], latitude=19.080, longitude=72.874),
            Vehicle(id='TRUCK-03', capacity_liters=6000, supported_waste=['general'], latitude=19.066, longitude=72.870, status='maintenance'),
        ]
        with self.engine.begin() as connection:
            if connection.execute(select(func.count()).select_from(bins_table)).scalar_one():
                return
            for bin in sample_bins:
                self._insert_if_missing(connection, bins_table, {'id': bin.id, 'payload': bin.model_dump_json()})
                for fill in [max(0, bin.fill_percent - 24), max(0, bin.fill_percent - 16), max(0, bin.fill_percent - 8), bin.fill_percent]:
                    reading = SensorReading(bin_id=bin.id, fill_percent=fill)
                    connection.execute(insert(readings_table).values(bin_id=bin.id, fill=fill, ts=reading.timestamp.isoformat(), weight=reading.weight_kg))
            for vehicle in sample_vehicles:
                self._insert_if_missing(connection, vehicles_table, {'id': vehicle.id, 'payload': vehicle.model_dump_json()})

    def _insert_if_missing(self, connection, table, values):
        key = list(table.primary_key.columns)[0]
        if self.dialect == 'sqlite':
            statement = sqlite_insert(table).values(**values).on_conflict_do_nothing(index_elements=[key])
        else:
            statement = postgres_insert(table).values(**values).on_conflict_do_nothing(index_elements=[key])
        connection.execute(statement)

    def save_bin(self, bin: Bin):
        self._upsert(bins_table, {'id': bin.id, 'payload': bin.model_dump_json()}, 'id')

    def bins(self):
        with self.engine.connect() as connection:
            rows = connection.execute(select(bins_table.c.payload).order_by(bins_table.c.id)).scalars().all()
        return [Bin.model_validate_json(payload) for payload in rows]

    def bin(self, id: str):
        with self.engine.connect() as connection:
            payload = connection.execute(select(bins_table.c.payload).where(bins_table.c.id == id)).scalar_one_or_none()
        return Bin.model_validate_json(payload) if payload else None

    def save_vehicle(self, vehicle: Vehicle):
        self._upsert(vehicles_table, {'id': vehicle.id, 'payload': vehicle.model_dump_json()}, 'id')

    def vehicles(self):
        with self.engine.connect() as connection:
            rows = connection.execute(select(vehicles_table.c.payload).order_by(vehicles_table.c.id)).scalars().all()
        return [Vehicle.model_validate_json(payload) for payload in rows]

    def add_reading(self, reading: SensorReading):
        with self.engine.begin() as connection:
            connection.execute(insert(readings_table).values(
                bin_id=reading.bin_id, fill=reading.fill_percent, ts=reading.timestamp.isoformat(), weight=reading.weight_kg,
            ))

    def reading_exists(self, reading: SensorReading) -> bool:
        with self.engine.connect() as connection:
            count = connection.execute(select(func.count()).select_from(readings_table).where(
                readings_table.c.bin_id == reading.bin_id,
                readings_table.c.ts == reading.timestamp.isoformat(),
            )).scalar_one()
        return count > 0

    def readings(self, bin_id: str):
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(readings_table).where(readings_table.c.bin_id == bin_id).order_by(readings_table.c.id.desc()).limit(30)
            ).mappings().all()
        return [dict(row) for row in rows]

    def save_forecast(self, forecast: Forecast):
        with self.engine.begin() as connection:
            connection.execute(insert(forecasts_table).values(
                bin_id=forecast.bin_id, generated_at=utcnow().isoformat(), payload=forecast.model_dump_json(),
            ))

    def forecasts(self, bin_id: str | None = None):
        statement = select(forecasts_table.c.payload).order_by(forecasts_table.c.id.desc())
        if bin_id is not None:
            statement = statement.where(forecasts_table.c.bin_id == bin_id)
        with self.engine.connect() as connection:
            payloads = connection.execute(statement).scalars().all()
        return [Forecast.model_validate_json(payload) for payload in payloads]

    def save_route(self, route: RoutePlan):
        self._upsert(routes_table, {'id': route.id, 'payload': route.model_dump_json()}, 'id')

    def route(self, id: str):
        with self.engine.connect() as connection:
            payload = connection.execute(select(routes_table.c.payload).where(routes_table.c.id == id)).scalar_one_or_none()
        return RoutePlan.model_validate_json(payload) if payload else None

    def routes(self):
        with self.engine.connect() as connection:
            payloads = connection.execute(select(routes_table.c.payload)).scalars().all()
        result = [RoutePlan.model_validate_json(payload) for payload in payloads]
        return sorted(result, key=lambda item: item.created_at, reverse=True)

    def record_collection(self, route_id: str, bin_id: str, waste_type: str, volume_liters: float):
        with self.engine.begin() as connection:
            connection.execute(insert(collections_table).values(
                route_id=route_id, bin_id=bin_id, waste_type=waste_type,
                volume_liters=volume_liters, collected_at=utcnow().isoformat(),
            ))

    def collections(self):
        with self.engine.connect() as connection:
            rows = connection.execute(select(collections_table).order_by(collections_table.c.id)).mappings().all()
        return [dict(row) for row in rows]

    def save_event(self, event: AgentEvent):
        self._upsert(events_table, {'id': event.id, 'payload': event.model_dump_json()}, 'id')

    def events(self):
        with self.engine.connect() as connection:
            payloads = connection.execute(select(events_table.c.payload)).scalars().all()
        result = [AgentEvent.model_validate_json(payload) for payload in payloads]
        return sorted(result, key=lambda item: item.created_at, reverse=True)[:100]

    def user(self, username: str):
        with self.engine.connect() as connection:
            row = connection.execute(select(users_table).where(users_table.c.username == username)).mappings().one_or_none()
        return dict(row) if row else None

    def user_by_id(self, user_id: int):
        with self.engine.connect() as connection:
            row = connection.execute(select(users_table).where(users_table.c.id == user_id)).mappings().one_or_none()
        return dict(row) if row else None

    def user_count(self):
        with self.engine.connect() as connection:
            return connection.execute(select(func.count()).select_from(users_table)).scalar_one()

    def create_user(self, username: str, password_hash: str, role: str):
        with self.engine.begin() as connection:
            result = connection.execute(insert(users_table).values(
                username=username, password_hash=password_hash, role=role, active=True, created_at=utcnow().isoformat(),
            ))
            return result.inserted_primary_key[0]

    def save_approval(self, route_id: str, operator_user_id: int, decision: str, comment: str):
        with self.engine.begin() as connection:
            connection.execute(insert(approval_history).values(
                route_id=route_id, operator_user_id=operator_user_id, decision=decision,
                comment=comment, created_at=utcnow().isoformat(),
            ))

    def save_audit(self, actor_user_id: int | None, action: str, entity_type: str, entity_id: str, details: dict):
        with self.engine.begin() as connection:
            connection.execute(insert(audit_logs).values(
                actor_user_id=actor_user_id, action=action, entity_type=entity_type,
                entity_id=entity_id, details=json.dumps(details, sort_keys=True), created_at=utcnow().isoformat(),
            ))
