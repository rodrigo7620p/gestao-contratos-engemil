import os
import sqlite3
import tempfile
from pathlib import Path


def run():
    with tempfile.TemporaryDirectory() as directory:
        database_path = Path(directory) / "legacy_v22.db"
        connection = sqlite3.connect(database_path)
        connection.execute(
            """CREATE TABLE arts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_id INTEGER NOT NULL,
            professional_name TEXT NOT NULL,
            professional_title TEXT,
            professional_registration TEXT,
            art_number TEXT NOT NULL,
            issue_date TEXT,
            end_date TEXT,
            status TEXT DEFAULT 'ATIVA',
            description TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"""
        )
        connection.commit()
        connection.close()

        os.environ["GESTAO_DB_PATH"] = str(database_path)
        os.environ["GESTAO_UPLOAD_DIR"] = str(Path(directory) / "uploads")

        from contract_utils import parse_brazilian_number
        from db import execute, init_db, query

        init_db()
        art_columns = {row["name"] for row in query("PRAGMA table_info(arts)")}
        assert {"amendment_id", "instrument_scope"}.issubset(art_columns)
        assert query(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_art_amendment'"
        )

        contract_id = execute(
            """INSERT INTO contracts(
            cost_center,client,contract_number,start_date,end_date,
            original_value,current_value)
            VALUES('TESTE.V23','ÓRGÃO TESTE','23/2026',
            '2026-01-01','2027-12-31',22763546.65,22763546.65)"""
        )
        amendment_id = execute(
            """INSERT INTO amendments(
            contract_id,ordinal,kind,start_date,end_date,value)
            VALUES(?,'1º','TERMO ADITIVO','2026-07-29','2028-08-02',22763546.65)""",
            (contract_id,),
        )
        art_id = execute(
            """INSERT INTO arts(
            contract_id,amendment_id,instrument_scope,professional_name,
            professional_title,art_number,status)
            VALUES(?,?,'ADITIVO','PROFISSIONAL TESTE','ENGENHEIRO CIVIL','ART-23','ATIVA')""",
            (contract_id, amendment_id),
        )
        linked = dict(query(
            "SELECT amendment_id,instrument_scope FROM arts WHERE id=?",
            (art_id,),
        )[0])
        assert linked == {"amendment_id": amendment_id, "instrument_scope": "ADITIVO"}
        assert parse_brazilian_number("R$ 22.763.546,65") == 22763546.65

        app_source = Path("app.py").read_text(encoding="utf-8")
        reports_source = Path("reports.py").read_text(encoding="utf-8")
        assert 'APP_VERSION = "' in app_source
        assert "contract_amendments_with_arts" in app_source
        assert "Instrumento contratual de referência *" in app_source
        assert "ARTs vinculadas" in app_source
        assert 'amendment_edit_df["value"] = amendment_edit_df["value"].map(brl)' in app_source
        assert 'position_edit_df["base_salary"] = position_edit_df["base_salary"].map(brl)' in app_source
        assert 'format="R$ %.2f"' not in app_source
        assert "ART e instrumento" in reports_source

    print("Testes da versão 23 concluídos com sucesso.")


if __name__ == "__main__":
    run()
