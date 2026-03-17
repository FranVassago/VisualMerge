from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.logging_utils import build_logger


@dataclass
class OracleConnectionConfig:
    host: str
    port: int
    sid: str
    user: str
    password: str


@dataclass
class OracleQueryConfig:
    box_id_query: str
    tracking_id_query: str


class OracleIdProvider:
    """Obtiene idCaja y trackingId desde Oracle."""

    def __init__(self, connection: OracleConnectionConfig, queries: OracleQueryConfig) -> None:
        self.connection = connection
        self.queries = queries
        self.logger = build_logger()

    def validate_connection(self) -> None:
        import oracledb

        dsn = oracledb.makedsn(self.connection.host, self.connection.port, sid=self.connection.sid)
        try:
            with oracledb.connect(user=self.connection.user, password=self.connection.password, dsn=dsn) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1 FROM DUAL")
                    cursor.fetchone()
        except Exception:
            self.logger.exception("Oracle connection validation failed")
            raise ValueError("No se pudo establecer conexión con Oracle usando la configuración indicada")

    def get_next_box_id(self) -> str:
        value = self._fetch_single_value(self.queries.box_id_query)
        return str(value)

    def get_next_tracking_id(self) -> int:
        value = self._fetch_single_value(self.queries.tracking_id_query)
        return int(value)

    def _fetch_single_value(self, query: str) -> Optional[str]:
        import oracledb

        dsn = oracledb.makedsn(self.connection.host, self.connection.port, sid=self.connection.sid)
        try:
            with oracledb.connect(user=self.connection.user, password=self.connection.password, dsn=dsn) as conn:
                with conn.cursor() as cursor:
                    self.logger.info("Executing Oracle query: %s", query)
                    cursor.execute(query)
                    row = cursor.fetchone()
                    if row is None:
                        raise ValueError(f"La consulta no devolvió resultados: {query}")
                    self.logger.info("Oracle query result type=%s value=%r", type(row[0]).__name__, row[0])
                    return row[0]
        except Exception:
            self.logger.exception("Oracle query failed: %s", query)
            raise
