from __future__ import annotations

"""Backup diário completo do sistema — banco de dados inteiro (todas as
tabelas, linha por linha, direto do Turso) e todos os documentos anexados
(extraídos do blob_store, onde ficam guardados para sobreviver ao disco
efêmero do Streamlit Cloud), salvos localmente dentro de Backups/AAAA-MM-DD/
nesta mesma pasta do projeto.

O resultado é uma cópia autônoma e utilizável: um arquivo .db no mesmo
formato que o sistema já sabe abrir localmente (sem precisar do Turso) e
uma pasta uploads/ com os arquivos de verdade — dá para apontar
GESTAO_DB_PATH/GESTAO_UPLOAD_DIR para essa pasta e rodar o sistema
inteiramente offline, ou usar como registro de segurança em caso de
sinistro. Backups mais antigos que BACKUP_RETENTION_DAYS são apagados
automaticamente para não crescer sem limite.

Uso:
    python backup_diario.py
"""

import io
import shutil
import sqlite3
import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path

from db import UPLOADS_BLOB_KEY, connect

BASE_DIR = Path(__file__).resolve().parent
BACKUP_ROOT = BASE_DIR / "Backups"
BACKUP_RETENTION_DAYS = 30

# Tabelas internas do próprio SQLite — nunca fazem parte dos dados do
# sistema, então ficam de fora da cópia (o schema já recria o que for
# necessário, como sqlite_sequence, ao rodar o SCHEMA no arquivo novo).
_INTERNAL_TABLE_PREFIXES = ("sqlite_",)


def _user_tables(conn) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return [
        row["name"] for row in rows
        if not str(row["name"]).startswith(_INTERNAL_TABLE_PREFIXES)
    ]


def _schema_statements(conn) -> list[str]:
    """Recria o schema da tabela de destino a partir do que EXISTE de
    verdade na origem (sqlite_master), em vez de replicar a constante
    SCHEMA de db.py — algumas colunas (ex.: documents.sesmt_professional_id)
    só existem via ALTER TABLE nas migrações de init_db() e nunca foram
    incluídas de volta no texto de SCHEMA, então copiar por essa constante
    ficaria incompleto e o backup falharia ao inserir essas colunas."""
    rows = conn.execute(
        """SELECT sql FROM sqlite_master
        WHERE type IN ('table','index') AND sql IS NOT NULL
        AND name NOT LIKE 'sqlite_%'
        ORDER BY CASE WHEN type='table' THEN 0 ELSE 1 END"""
    ).fetchall()
    return [row["sql"] for row in rows]


def _copy_table(source_conn, dest_conn, table: str) -> int:
    rows = source_conn.execute(f"SELECT * FROM {table}").fetchall()
    if not rows:
        return 0
    columns = list(rows[0].keys())
    placeholders = ",".join("?" for _ in columns)
    dest_conn.executemany(
        f"INSERT INTO {table}({','.join(columns)}) VALUES({placeholders})",
        [tuple(row[col] for col in columns) for row in rows],
    )
    return len(rows)


def _restore_uploads(source_conn, uploads_dir: Path) -> int:
    row = source_conn.execute(
        "SELECT data FROM blob_store WHERE key=?", (UPLOADS_BLOB_KEY,)
    ).fetchone()
    if not row or row["data"] is None:
        return 0
    data = bytes(row["data"])
    uploads_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(uploads_dir)
        return len(zf.namelist())


def _prune_old_backups() -> list[str]:
    if not BACKUP_ROOT.exists():
        return []
    cutoff = date.today() - timedelta(days=BACKUP_RETENTION_DAYS)
    removed = []
    for entry in BACKUP_ROOT.iterdir():
        if not entry.is_dir():
            continue
        try:
            entry_date = date.fromisoformat(entry.name)
        except ValueError:
            continue
        if entry_date < cutoff:
            shutil.rmtree(entry, ignore_errors=True)
            removed.append(entry.name)
    return removed


def run_backup() -> dict:
    today_label = date.today().isoformat()
    backup_dir = BACKUP_ROOT / today_label
    if backup_dir.exists():
        shutil.rmtree(backup_dir)
    backup_dir.mkdir(parents=True)

    db_path = backup_dir / "gestao_contratos.db"
    uploads_dir = backup_dir / "uploads"

    dest_conn = sqlite3.connect(db_path)
    dest_conn.row_factory = sqlite3.Row
    dest_conn.execute("PRAGMA foreign_keys = OFF")

    table_counts: dict[str, int] = {}
    with connect() as source_conn:
        for statement in _schema_statements(source_conn):
            dest_conn.execute(statement)
        tables = _user_tables(source_conn)
        for table in tables:
            table_counts[table] = _copy_table(source_conn, dest_conn, table)
        dest_conn.commit()
        files_restored = _restore_uploads(source_conn, uploads_dir)

    dest_conn.close()
    removed = _prune_old_backups()

    return {
        "backup_dir": str(backup_dir),
        "db_size_bytes": db_path.stat().st_size,
        "tables": table_counts,
        "total_rows": sum(table_counts.values()),
        "files_restored": files_restored,
        "old_backups_removed": removed,
    }


if __name__ == "__main__":
    result = run_backup()
    print(f"Backup salvo em: {result['backup_dir']}")
    print(f"Banco: {result['db_size_bytes'] / (1024 * 1024):.1f} MB, "
          f"{len(result['tables'])} tabelas, {result['total_rows']} linhas no total")
    print(f"Documentos restaurados: {result['files_restored']}")
    if result["old_backups_removed"]:
        print(f"Backups antigos removidos (> {BACKUP_RETENTION_DAYS} dias): "
              f"{', '.join(result['old_backups_removed'])}")
    sys.exit(0)
