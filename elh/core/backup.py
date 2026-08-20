"""Database backup and restore operations shared by desktop and future web UIs."""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import subprocess
import tempfile
from contextlib import closing
from datetime import datetime
from pathlib import Path

from elh.config import AppConfig


class BackupError(RuntimeError):
    """Raised when a backup cannot be safely created, verified, or restored."""


class BackupService:
    def __init__(self, config: AppConfig):
        self.config = config

    @property
    def extension(self) -> str:
        return ".sql" if self.config.database_engine == "mysql" else ".db"

    def default_path(self) -> Path:
        directory = self.config.backup_directory
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        candidate = directory / f"elh_{self.config.database_name}_{stamp}{self.extension}"
        sequence = 1
        while candidate.exists():
            candidate = directory / f"elh_{self.config.database_name}_{stamp}_{sequence}{self.extension}"
            sequence += 1
        return candidate

    def create(self, destination: Path | str | None = None) -> Path:
        path = Path(destination) if destination else self.default_path()
        if not path.suffix:
            path = path.with_suffix(self.extension)
        path.parent.mkdir(parents=True, exist_ok=True)
        if self.config.database_engine == "sqlite":
            self._create_sqlite(path)
        elif self.config.database_engine == "mysql":
            self._create_mysql(path)
        else:
            raise BackupError(f"Unsupported database engine: {self.config.database_engine}")
        self._write_checksum(path)
        return path

    def verify(self, source: Path | str) -> None:
        path = Path(source)
        if not path.is_file():
            raise BackupError(f"Backup file was not found: {path}")
        self._verify_checksum(path)
        if path.suffix.lower() == ".db" or self.config.database_engine == "sqlite":
            try:
                with closing(sqlite3.connect(path)) as connection:
                    result = connection.execute("PRAGMA integrity_check").fetchone()[0]
            except sqlite3.Error as exc:
                raise BackupError(f"Invalid SQLite backup: {exc}") from exc
            if result != "ok":
                raise BackupError(f"SQLite integrity check failed: {result}")
            return
        if path.stat().st_size < 32:
            raise BackupError("The SQL backup is empty or incomplete.")
        with path.open("rb") as stream:
            sample = stream.read(1_048_576)
        if b"\x00" in sample or b";" not in sample:
            raise BackupError("The selected file does not appear to be a SQL backup.")

    def restore(self, source: Path | str) -> None:
        path = Path(source)
        self.verify(path)
        if self.config.database_engine == "sqlite":
            self._restore_sqlite(path)
        elif self.config.database_engine == "mysql":
            self._restore_mysql(path)
        else:
            raise BackupError(f"Unsupported database engine: {self.config.database_engine}")

    def tool_status(self) -> tuple[bool, str]:
        if self.config.database_engine != "mysql":
            return True, "SQLite online backup is available"
        dump = self._find_mysql_tool("mysqldump", self.config.mysql_dump_path)
        client = self._find_mysql_tool("mysql", self.config.mysql_client_path)
        if dump and client:
            return True, f"MySQL backup tools available ({dump.parent})"
        missing = []
        if not dump:
            missing.append("mysqldump")
        if not client:
            missing.append("mysql client")
        return False, f"Missing {' and '.join(missing)}; configure the tool path in Environment Configuration"

    def _create_sqlite(self, destination: Path) -> None:
        source = self.config.database_path.resolve()
        if not source.is_file():
            raise BackupError(f"SQLite database was not found: {source}")
        if destination.resolve() == source:
            raise BackupError("The backup destination cannot replace the live database.")
        try:
            with closing(sqlite3.connect(source)) as source_db, closing(
                sqlite3.connect(destination)
            ) as destination_db:
                source_db.backup(destination_db)
        except (OSError, sqlite3.Error) as exc:
            destination.unlink(missing_ok=True)
            raise BackupError(f"SQLite backup failed: {exc}") from exc

    def _create_mysql(self, destination: Path) -> None:
        executable = self._find_mysql_tool("mysqldump", self.config.mysql_dump_path)
        if not executable:
            raise BackupError("mysqldump was not found. Configure ELH_MYSQL_DUMP_PATH.")
        with tempfile.TemporaryDirectory(prefix="elh-mysql-") as folder:
            option_file = self._write_mysql_option_file(Path(folder))
            command = [
                str(executable),
                f"--defaults-extra-file={option_file}",
                "--default-character-set=utf8mb4",
                "--single-transaction",
                "--routines",
                "--triggers",
                "--events",
                "--hex-blob",
                "--set-gtid-purged=OFF",
                f"--result-file={destination.resolve()}",
                self.config.database_name,
            ]
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    timeout=600,
                    check=False,
                    creationflags=self._creation_flags(),
                )
            except (OSError, subprocess.SubprocessError) as exc:
                destination.unlink(missing_ok=True)
                raise BackupError(f"MySQL backup could not run: {exc}") from exc
        if result.returncode != 0:
            destination.unlink(missing_ok=True)
            detail = result.stderr.decode("utf-8", errors="replace").strip()[-1500:]
            raise BackupError(f"mysqldump failed: {detail or 'unknown error'}")
        if not destination.is_file() or destination.stat().st_size == 0:
            raise BackupError("mysqldump completed without creating a backup file.")

    def _restore_sqlite(self, source: Path) -> None:
        target = self.config.database_path.resolve()
        if source.resolve() == target:
            raise BackupError("The selected backup is already the live database.")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.restore.tmp")
        try:
            shutil.copy2(source, temporary)
            os.replace(temporary, target)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise BackupError(f"SQLite restore failed: {exc}") from exc

    def _restore_mysql(self, source: Path) -> None:
        executable = self._find_mysql_tool("mysql", self.config.mysql_client_path)
        if not executable:
            raise BackupError("The mysql client was not found. Configure ELH_MYSQL_CLIENT_PATH.")
        with tempfile.TemporaryDirectory(prefix="elh-mysql-") as folder:
            option_file = self._write_mysql_option_file(Path(folder))
            command = [
                str(executable),
                f"--defaults-extra-file={option_file}",
                "--default-character-set=utf8mb4",
                self.config.database_name,
            ]
            try:
                with source.open("rb") as stream:
                    result = subprocess.run(
                        command,
                        stdin=stream,
                        capture_output=True,
                        timeout=1800,
                        check=False,
                        creationflags=self._creation_flags(),
                    )
            except (OSError, subprocess.SubprocessError) as exc:
                raise BackupError(f"MySQL restore could not run: {exc}") from exc
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()[-1500:]
            raise BackupError(f"MySQL restore failed: {detail or 'unknown error'}")

    def _write_mysql_option_file(self, directory: Path) -> Path:
        values = {
            "host": self.config.database_host,
            "port": str(self.config.database_port),
            "user": self.config.database_user,
            "password": self.config.database_password,
        }
        if any("\n" in value or "\r" in value for value in values.values()):
            raise BackupError("Database connection values cannot contain line breaks.")
        path = directory / "client.cnf"
        lines = ["[client]"]
        for key, value in values.items():
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key}="{escaped}"')
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
        return path

    @staticmethod
    def _find_mysql_tool(name: str, configured: str) -> Path | None:
        if configured:
            path = Path(configured).expanduser()
            if path.is_file():
                return path
        located = shutil.which(name)
        if located:
            return Path(located)
        executable = f"{name}.exe" if os.name == "nt" else name
        candidates = (
            Path("C:/Program Files/MySQL/MySQL Server 8.0/bin") / executable,
            Path("C:/Program Files/MySQL/MySQL Workbench 8.0") / executable,
        )
        return next((path for path in candidates if path.is_file()), None)

    @staticmethod
    def _creation_flags() -> int:
        return int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0

    @staticmethod
    def _checksum(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1_048_576), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _write_checksum(self, path: Path) -> None:
        checksum = self._checksum(path)
        path.with_suffix(path.suffix + ".sha256").write_text(
            f"{checksum}  {path.name}\n", encoding="ascii"
        )

    def _verify_checksum(self, path: Path) -> None:
        checksum_path = path.with_suffix(path.suffix + ".sha256")
        if not checksum_path.exists():
            return
        expected = checksum_path.read_text(encoding="ascii").strip().split(maxsplit=1)[0]
        if len(expected) != 64 or not hmac_compare(expected, self._checksum(path)):
            raise BackupError("Backup checksum verification failed.")


def hmac_compare(left: str, right: str) -> bool:
    import hmac

    return hmac.compare_digest(left, right)
