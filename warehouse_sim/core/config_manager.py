from __future__ import annotations

import configparser
from pathlib import Path
from typing import Dict, Optional

from services.oracle_id_provider import OracleConnectionConfig, OracleIdProvider, OracleQueryConfig
from services.sequence_id_provider import SequenceIdProvider


DEFAULT_SETTINGS: Dict[str, object] = {
    "sim_speed_cells": 1.7,
    "grid_gray": 65,
    "induction_poll_interval": 5.0,
    "scan_endpoint": "http://vpn.v10.solutions:18080/ords/merza/merza/scan",
    "scanner_default_tag": "SCAN01",
    "oracle_enabled": False,
    "oracle_host": "localhost",
    "oracle_port": 1521,
    "oracle_sid": "ORCL",
    "oracle_user": "",
    "oracle_password": "",
    "oracle_box_id_query": (
        "SELECT MIN(CODCNTSSCC) BARCODE FROM VDCNTSSCC WHERE CODCNTSSCC NOT IN "
        "(SELECT MATCAJA FROM VDBULTOCAB WHERE MATCAJA IS NOT NULL AND STATUS > -VDST.FBUCFINALIZADO "
        "AND STATUS < VDST.FBUCFINALIZADO)"
    ),
    "oracle_tracking_id_query": "SELECT NVL(MAX(TRACKINGIDHOST),0) + 1 FROM VDBULTOSCANHIST WHERE TRACKINGIDHOST IS NOT NULL",
}


class ConfigManager:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self, current_settings: Optional[Dict[str, object]] = None) -> Dict[str, object]:
        settings: Dict[str, object] = dict(DEFAULT_SETTINGS)
        if current_settings:
            settings.update(current_settings)

        if not self.path.exists():
            self.save(settings)
            return settings

        cfg = configparser.ConfigParser()
        cfg.read(self.path)
        if "sim" not in cfg:
            return settings

        sim = cfg["sim"]
        settings["sim_speed_cells"] = sim.getfloat("sim_speed_cells", fallback=float(settings["sim_speed_cells"]))
        settings["grid_gray"] = sim.getint("grid_gray", fallback=int(settings["grid_gray"]))
        settings["induction_poll_interval"] = sim.getfloat(
            "induction_poll_interval", fallback=float(settings["induction_poll_interval"])
        )
        settings["scan_endpoint"] = sim.get("scan_endpoint", fallback=str(settings["scan_endpoint"]))
        settings["scanner_default_tag"] = sim.get("scanner_default_tag", fallback=str(settings["scanner_default_tag"]))
        settings["oracle_enabled"] = sim.getboolean("oracle_enabled", fallback=bool(settings["oracle_enabled"]))
        settings["oracle_host"] = sim.get("oracle_host", fallback=str(settings["oracle_host"]))
        settings["oracle_port"] = sim.getint("oracle_port", fallback=int(settings["oracle_port"]))
        settings["oracle_sid"] = sim.get("oracle_sid", fallback=str(settings["oracle_sid"]))
        settings["oracle_user"] = sim.get("oracle_user", fallback=str(settings["oracle_user"]))
        settings["oracle_password"] = sim.get("oracle_password", fallback=str(settings["oracle_password"]))
        settings["oracle_box_id_query"] = self._normalize_query(
            sim.get("oracle_box_id_query", fallback=str(settings["oracle_box_id_query"]))
        )
        settings["oracle_tracking_id_query"] = self._normalize_query(
            sim.get("oracle_tracking_id_query", fallback=str(settings["oracle_tracking_id_query"]))
        )
        return settings

    def save(self, settings: Dict[str, object]) -> None:
        cfg = configparser.ConfigParser()
        cfg["sim"] = {
            "sim_speed_cells": str(settings["sim_speed_cells"]),
            "grid_gray": str(int(settings["grid_gray"])),
            "induction_poll_interval": str(settings["induction_poll_interval"]),
            "scan_endpoint": str(settings["scan_endpoint"]),
            "scanner_default_tag": str(settings["scanner_default_tag"]),
            "oracle_enabled": str(bool(settings["oracle_enabled"])).lower(),
            "oracle_host": str(settings["oracle_host"]),
            "oracle_port": str(int(settings["oracle_port"])),
            "oracle_sid": str(settings["oracle_sid"]),
            "oracle_user": str(settings["oracle_user"]),
            "oracle_password": str(settings["oracle_password"]),
            "oracle_box_id_query": self._normalize_query(str(settings["oracle_box_id_query"])),
            "oracle_tracking_id_query": self._normalize_query(str(settings["oracle_tracking_id_query"])),
        }
        with self.path.open("w", encoding="utf-8") as config_file:
            cfg.write(config_file)

    def build_id_provider(self, settings: Dict[str, object]):
        if not settings["oracle_enabled"]:
            return SequenceIdProvider()
        conn = OracleConnectionConfig(
            host=str(settings["oracle_host"]),
            port=int(settings["oracle_port"]),
            sid=str(settings["oracle_sid"]),
            user=str(settings["oracle_user"]),
            password=str(settings["oracle_password"]),
        )
        queries = OracleQueryConfig(
            box_id_query=str(settings["oracle_box_id_query"]),
            tracking_id_query=str(settings["oracle_tracking_id_query"]),
        )
        return OracleIdProvider(conn, queries)

    @staticmethod
    def _normalize_query(raw_query: str) -> str:
        return raw_query.replace("\\n", "\n").strip()
