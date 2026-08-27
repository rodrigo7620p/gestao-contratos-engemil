from __future__ import annotations

import sqlite3
from pathlib import Path

from art_management import art_number_key
from contract_utils import contract_duration_months, extract_agency_acronym
from db import DB_PATH, UPLOAD_DIR


def run() -> int:
    if not DB_PATH.exists():
        print(f"ERRO: banco não localizado em {DB_PATH}")
        return 1
    connection = sqlite3.connect(f"file:{DB_PATH.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    print(f"Integridade SQLite: {integrity}")
    for table in (
        "contracts", "amendments", "contract_positions", "arts",
        "contract_cnos", "contract_guarantees", "guarantee_coverages",
        "guarantee_endorsements", "contract_budget_dates", "documents", "users",
        "audit_log",
    ):
        total = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table}: {total}")

    zero_salaries = connection.execute(
        """SELECT p.id,p.title,c.cost_center FROM contract_positions p
        JOIN contracts c ON c.id=p.contract_id WHERE p.base_salary<=0
        ORDER BY c.cost_center,p.title"""
    ).fetchall()
    arts_without_title = connection.execute(
        """SELECT a.id,a.professional_name,a.art_number,c.cost_center FROM arts a
        JOIN contracts c ON c.id=a.contract_id
        WHERE TRIM(COALESCE(a.professional_title,''))='' ORDER BY c.cost_center,a.id"""
    ).fetchall()
    arts_without_instrument = connection.execute(
        """SELECT a.id,a.professional_name,a.art_number,c.cost_center FROM arts a
        JOIN contracts c ON c.id=a.contract_id
        WHERE COALESCE(a.instrument_scope,'NÃO DEFINIDO')='NÃO DEFINIDO'
        ORDER BY c.cost_center,a.id"""
    ).fetchall()
    invalid_art_links = connection.execute(
        """SELECT a.id,a.art_number,c.cost_center FROM arts a
        JOIN contracts c ON c.id=a.contract_id
        JOIN amendments m ON m.id=a.amendment_id
        WHERE a.contract_id<>m.contract_id ORDER BY c.cost_center,a.id"""
    ).fetchall()
    duplicate_art_numbers = []
    seen_art_numbers = {}
    for row in connection.execute(
        "SELECT id,contract_id,art_number FROM arts ORDER BY contract_id,id"
    ).fetchall():
        key = (row["contract_id"], art_number_key(row["art_number"]))
        if key[1] and key in seen_art_numbers:
            duplicate_art_numbers.append((seen_art_numbers[key], row))
        elif key[1]:
            seen_art_numbers[key] = row
    clients_without_acronym = [
        row for row in connection.execute(
            "SELECT id,cost_center,client FROM contracts ORDER BY cost_center"
        ).fetchall()
        if not extract_agency_acronym(row["client"])
    ]
    missing_files = []
    for row in connection.execute(
        "SELECT id,contract_id,title,stored_path FROM documents ORDER BY id"
    ).fetchall():
        raw = str(row["stored_path"] or "")
        stored_name = Path(raw.replace("\\", "/")).name
        fallback = UPLOAD_DIR / str(row["contract_id"]) / stored_name
        if not Path(raw).exists() and not fallback.exists():
            missing_files.append(row)
    invalid_terms = []
    for row in connection.execute(
        """SELECT id,start_date,end_date,duration_months FROM amendments
        WHERE start_date IS NOT NULL AND end_date IS NOT NULL ORDER BY id"""
    ).fetchall():
        calculated = contract_duration_months(row["start_date"], row["end_date"])
        if calculated is None:
            invalid_terms.append(row)
    cno_undefined = connection.execute(
        "SELECT COUNT(*) FROM contracts WHERE cno_required IS NULL"
    ).fetchone()[0]
    cno_conflicts = connection.execute(
        """SELECT COUNT(*) FROM contracts c
        WHERE c.cno_required=0
        AND EXISTS (SELECT 1 FROM contract_cnos n WHERE n.contract_id=c.id)"""
    ).fetchone()[0]
    guarantee_missing_documents = connection.execute(
        """SELECT COUNT(*) FROM contract_guarantees g
        WHERE g.request_status IN ('RECEBIDA','EM ANÁLISE','ACEITA')
        AND NOT EXISTS (SELECT 1 FROM documents d WHERE d.guarantee_id=g.id)"""
    ).fetchone()[0]
    expired_guarantees = connection.execute(
        """SELECT COUNT(*) FROM contract_guarantees
        WHERE request_status NOT IN ('DISPENSADA','CANCELADA')
        AND end_date IS NOT NULL AND date(end_date)<date('now')"""
    ).fetchone()[0]

    print(f"Revisar salários-base zerados: {len(zero_salaries)}")
    for row in zero_salaries[:20]:
        print(f"  - {row['cost_center']} · {row['title']} · código {row['id']}")
    print(f"Completar títulos profissionais das ARTs: {len(arts_without_title)}")
    print(f"Associar ARTs antigas a um instrumento: {len(arts_without_instrument)}")
    for row in arts_without_instrument[:20]:
        print(
            f"  - {row['cost_center']} · ART {row['art_number']} · "
            f"{row['professional_name']}"
        )
    print(f"Vínculos ART/aditivo inconsistentes: {len(invalid_art_links)}")
    print(f"Números de ART duplicados no mesmo contrato: {len(duplicate_art_numbers)}")
    print(f"Contratantes sem sigla explícita ao final: {len(clients_without_acronym)}")
    print(f"Documentos com arquivo não localizado: {len(missing_files)}")
    print(f"Aditivos com período inválido: {len(invalid_terms)}")
    print(f"Contratos com aplicabilidade do CNO a definir: {cno_undefined}")
    print(f"Contratos marcados sem CNO, mas com registro histórico: {cno_conflicts}")
    print(f"Garantias recebidas/aceitas sem documento: {guarantee_missing_documents}")
    print(f"Garantias vencidas para revisão: {expired_guarantees}")
    connection.close()
    return 0 if integrity == "ok" and not missing_files and not invalid_art_links else 1


if __name__ == "__main__":
    raise SystemExit(run())
