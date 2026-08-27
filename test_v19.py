import os
import tempfile
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

temporary = tempfile.TemporaryDirectory()
os.environ["GESTAO_DB_PATH"] = str(Path(temporary.name) / "test_v19.db")
os.environ["GESTAO_UPLOAD_DIR"] = str(Path(temporary.name) / "uploads")

from backlog import BACKLOG_SORT_OPTIONS, sort_backlog_rows  # noqa: E402
from db import execute, init_db, query  # noqa: E402
from reports import generate_backlog_pdf  # noqa: E402


def run():
    rows = [
        {
            "Item": 1,
            "Centro de custo": "01.02.00010",
            "Contratante": "ÓRGÃO B",
            "Contrato": "2/2026",
            "Início": "2026-01-01",
            "Fim": "2027-12-31",
            "Valor atual": 100,
            "Instrumento vigente": "Contrato",
            "Remanescente total": 80,
        },
        {
            "Item": 2,
            "Centro de custo": "01.02.00002",
            "Contratante": "ÁGÊNCIA A",
            "Contrato": "1/2026",
            "Início": "2026-01-01",
            "Fim": "2026-12-31",
            "Valor atual": 300,
            "Instrumento vigente": "1º Termo Aditivo",
            "Remanescente total": 250,
        },
    ]
    alphabetical = sort_backlog_rows(rows, "client_asc")
    assert alphabetical[0]["Contrato"] == "1/2026"
    assert [row["Item"] for row in alphabetical] == [1, 2]
    by_cost_center = sort_backlog_rows(rows, "cost_center_asc")
    assert by_cost_center[0]["Centro de custo"] == "01.02.00002"
    by_value = sort_backlog_rows(rows, "current_value_desc")
    assert by_value[0]["Valor atual"] == 300
    by_remaining = sort_backlog_rows(rows, "remaining_desc")
    assert by_remaining[0]["Remanescente total"] == 250
    by_end = sort_backlog_rows(rows, "end_date_asc")
    assert by_end[0]["Fim"] == "2026-12-31"
    assert len(BACKLOG_SORT_OPTIONS) >= 6

    signatory = {
        "name": "MATHEUS ANTONIO MILITAO DE MENEZES",
        "title": "Engenheiro Civil - Sócio Diretor",
        "registration": "CREA 13.814/D-DF",
        "cpf": "000.400.681-02",
    }
    pdf = generate_backlog_pdf(
        alphabetical,
        signatory=signatory,
        sort_label="Contratante - ordem alfabética",
    )
    reader = PdfReader(BytesIO(pdf))
    assert len(reader.pages) == 1
    assert float(reader.pages[0].mediabox.height) > float(reader.pages[0].mediabox.width)
    text = reader.pages[0].extract_text()
    assert "MATHEUS ANTONIO MILITAO DE MENEZES" in text
    assert "Ordenação: Contratante - ordem alfabética" in text

    init_db()
    contract_id = execute(
        """INSERT INTO contracts(
        cost_center,client,contract_number,original_value,current_value,status)
        VALUES(?,?,?,?,?,'ATIVO')""",
        ("TESTE.V19", "ÓRGÃO TESTE", "19/2026", 817706.44, 0),
    )
    init_db()
    contract = query(
        "SELECT original_value,current_value FROM contracts WHERE id=?",
        (contract_id,),
    )[0]
    assert contract["current_value"] == contract["original_value"] == 817706.44
    assert query(
        """SELECT id FROM audit_log
        WHERE action='CORRIGIR VALOR ATUAL'
        AND entity='contratos sem aditivo'"""
    )

    app_source = Path("app.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "' in app_source
    assert "current_value = original_value" in app_source
    assert "Responsável pela assinatura" in app_source
    assert "Ordenar o Backlog por" in app_source
    print("Testes da versão 19 concluídos com sucesso.")


if __name__ == "__main__":
    run()
