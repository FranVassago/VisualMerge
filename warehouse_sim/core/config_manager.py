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
}

DEFAULT_DB_SETTINGS: Dict[str, object] = {
    "oracle_host": "",
    "oracle_port": 1521,
    "oracle_sid": "",
    "oracle_user": "",
    "oracle_password": "",
    "oracle_box_id_query": "",
    "oracle_tracking_id_query": "",
    "oracle_reinduction_box_id_query": "",
}


class ConfigManager:
    def __init__(self, path: Path, db_path: Path) -> None:
        self.path = path
        self.db_path = db_path

    def load(self, current_settings: Optional[Dict[str, object]] = None) -> Dict[str, object]:
        settings: Dict[str, object] = dict(DEFAULT_SETTINGS)
        settings.update(DEFAULT_DB_SETTINGS)
        if current_settings:
            settings.update(current_settings)

        if not self.path.exists():
            self.save(settings)
        else:
            cfg = configparser.ConfigParser()
            cfg.read(self.path)
            if "sim" in cfg:
                sim = cfg["sim"]
                settings["sim_speed_cells"] = sim.getfloat("sim_speed_cells", fallback=float(settings["sim_speed_cells"]))
                settings["grid_gray"] = sim.getint("grid_gray", fallback=int(settings["grid_gray"]))
                settings["induction_poll_interval"] = sim.getfloat(
                    "induction_poll_interval", fallback=float(settings["induction_poll_interval"])
                )
                settings["scan_endpoint"] = sim.get("scan_endpoint", fallback=str(settings["scan_endpoint"]))
                settings["scanner_default_tag"] = sim.get("scanner_default_tag", fallback=str(settings["scanner_default_tag"]))
                settings["oracle_enabled"] = sim.getboolean("oracle_enabled", fallback=bool(settings["oracle_enabled"]))

        self._load_db_settings(settings)
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
        }
        with self.path.open("w", encoding="utf-8") as config_file:
            cfg.write(config_file)

        db_cfg = configparser.ConfigParser()
        db_cfg["oracle"] = {
            "host": str(settings["oracle_host"]),
            "port": str(int(settings["oracle_port"])),
            "sid": str(settings["oracle_sid"]),
            "user": str(settings["oracle_user"]),
            "password": str(settings["oracle_password"]),
            "box_id_query": self._normalize_query(str(settings["oracle_box_id_query"])),
            "tracking_id_query": self._normalize_query(str(settings["oracle_tracking_id_query"])),
            "reinduction_box_id_query": self._normalize_query(str(settings["oracle_reinduction_box_id_query"])),
        }
        with self.db_path.open("w", encoding="utf-8") as db_config_file:
            db_cfg.write(db_config_file)

    def build_id_provider(self, settings: Dict[str, object]):
        if not settings["oracle_enabled"]:
            return SequenceIdProvider()

        self._validate_oracle_settings(settings)

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
            reinduction_box_id_query=str(settings["oracle_reinduction_box_id_query"]),
        )
        provider = OracleIdProvider(conn, queries)
        provider.validate_connection()
        return provider

    def _load_db_settings(self, settings: Dict[str, object]) -> None:
        if not self.db_path.exists():
            self.save(settings)
            return

        cfg = configparser.ConfigParser()
        cfg.read(self.db_path)
        if "oracle" not in cfg:
            return

        oracle = cfg["oracle"]
        settings["oracle_host"] = oracle.get("host", fallback=str(settings["oracle_host"]))
        settings["oracle_port"] = oracle.getint("port", fallback=int(settings["oracle_port"]))
        settings["oracle_sid"] = oracle.get("sid", fallback=str(settings["oracle_sid"]))
        settings["oracle_user"] = oracle.get("user", fallback=str(settings["oracle_user"]))
        settings["oracle_password"] = oracle.get("password", fallback=str(settings["oracle_password"]))
        settings["oracle_box_id_query"] = self._normalize_query(
            oracle.get("box_id_query", fallback=str(settings["oracle_box_id_query"]))
        )
        settings["oracle_tracking_id_query"] = self._normalize_query(
            oracle.get("tracking_id_query", fallback=str(settings["oracle_tracking_id_query"]))
        )
        settings["oracle_reinduction_box_id_query"] = self._normalize_query(
            oracle.get("reinduction_box_id_query", fallback=str(settings["oracle_reinduction_box_id_query"]))
        )

    @staticmethod
    def _validate_oracle_settings(settings: Dict[str, object]) -> None:
        required_fields = [
            "oracle_host",
            "oracle_sid",
            "oracle_user",
            "oracle_password",
            "oracle_box_id_query",
            "oracle_tracking_id_query",
            "oracle_reinduction_box_id_query",
        ]
        missing = [field for field in required_fields if not str(settings.get(field, "")).strip()]
        if int(settings.get("oracle_port", 0)) <= 0:
            missing.append("oracle_port")

        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"Configuración Oracle incompleta. Revisar: {joined}")

    @staticmethod
    def _normalize_query(raw_query: str) -> str:
        return raw_query.replace("\\n", "\n").strip()
