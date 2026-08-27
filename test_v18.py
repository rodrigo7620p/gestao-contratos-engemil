from datetime import date
from pathlib import Path

from data_quality import contract_review_issues
from reports import generate_backlog_pdf


def run():
    issues = contract_review_issues({
        "manager_name": "",
        "end_date": "2026-11-30",
        "current_value": 0,
    })
    assert [issue["label"] for issue in issues] == [
        "Responsável administrativo",
        "Valor atual",
    ]
    assert not contract_review_issues({
        "manager_name": "Responsável Teste",
        "end_date": "2027-12-31",
        "current_value": 1000,
    })

    rows = [{
        "Item": 1,
        "Centro de custo": "01.02.00320",
        "Contratante": "FUNDO NACIONAL DE DESENVOLVIMENTO DA EDUCAÇÃO - FNDE",
        "Contrato": "337/2026",
        "Início": "2026-07-27",
        "Fim": "2026-11-30",
        "Valor atual": 1500000,
        "Instrumento vigente": "Contrato",
        "Remanescente total": 1200000,
    }]
    pdf = generate_backlog_pdf(rows, date(2026, 7, 30))
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 10_000

    app_source = Path("app.py").read_text(encoding="utf-8")
    assert 'variant="annual-bars"' in app_source
    assert "EXIBIR PENDÊNCIAS E ABRIR FICHAS" in app_source
    assert "Abrir ficha para corrigir" in app_source
    assert "Gerar Backlog oficial em PDF" in app_source
    assert 'APP_VERSION = "' in app_source
    assert "generate_backlog_report" not in Path("reports.py").read_text(encoding="utf-8")
    print("Testes de regressão da versão 18 concluídos com sucesso.")


if __name__ == "__main__":
    run()
