from __future__ import annotations

from elh.config import AppConfig
from .mysql_database import MySQLDatabase
from .sqlite_database import SQLiteDatabase


def create_database(config: AppConfig):
    if config.database_engine == "mysql":
        return MySQLDatabase(config)
    if config.database_engine == "sqlite":
        return SQLiteDatabase(config.database_path, config.seed_demo_data)
    raise ValueError(f"Unsupported database engine: {config.database_engine}")
