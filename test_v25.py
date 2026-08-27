import os
import tempfile
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader


def run():
    with tempfile.TemporaryDirectory() as directory:
        os.environ["GESTAO_DB_PATH"] = str(Path(directory) / "v25.db")
        os.environ["GESTAO_UPLOAD_DIR"] = str(Path(directory) / "uploads")

        from alerts import obligation_notification_text, contract_expiry_notification_text
        from db import execute, init_db, query
        from reports import generate_indices_pdf

        init_db()
        contract_id = execute(
            """INSERT INTO contracts(
            cost_center,client,contract_number,start_date,end_date,cno_required)
            VALUES(?,?,?,?,?,NULL)""",
            (
                "01.02.00253",
                "AGÊNCIA BRASILEIRA DE PROMOÇÃO INTERNACIONAL DO TURISMO - EMBRATUR",
                "02/2024",
                "2024-02-01",
                "2029-02-01",
            ),
        )
        cno_id = execute(
            """INSERT INTO contract_cnos(contract_id,registration_number)
            VALUES(?,'CNO-V25')""",
            (contract_id,),
        )
        assert cno_id
        init_db()
        assert query(
            "SELECT cno_required FROM contracts WHERE id=?", (contract_id,)
        )[0]["cno_required"] == 1

        today = date(2026, 7, 31)
        obligation = {
            "due_date": (today + timedelta(days=30)).isoformat(),
            "cost_center": "01.02.00253",
            "client": "AGÊNCIA BRASILEIRA DE PROMOÇÃO INTERNACIONAL DO TURISMO - EMBRATUR",
            "contract_number": "02/2024",
            "title": "Teste de sistema",
            "category": "ADMINISTRATIVA",
            "priority": "CRÍTICA",
            "responsible_name": "RESPONSÁVEL TESTE",
            "notes": "Providenciar a demanda.",
        }
        subject, body = obligation_notification_text(obligation, today)
        assert subject == "01.02.00253_EMBRATUR_[VENCE EM 30 DIA(S)]"
        assert "Providencie o atendimento e registre a conclusão no sistema." not in body
        assert "responda a este e-mail com a confirmação e as evidências" in body

        expiry = {
            "effective_end": (today + timedelta(days=15)).isoformat(),
            "cost_center": "01.02.00253",
            "client": obligation["client"],
            "contract_number": "02/2024",
            "effective_instrument": "2º Termo Aditivo",
            "engineer_name": "ENGENHEIRO TESTE",
        }
        expiry_subject, _ = contract_expiry_notification_text(expiry, 15, today)
        assert expiry_subject == "01.02.00253_EMBRATUR_[VENCE EM 15 DIA(S)]"

        rows = []
        for item in range(1, 66):
            rows.append({
                "Item": item,
                "Centro de custo": f"01.02.{item:04d}",
                "Contratante": f"CONTRATANTE DE TESTE {item:02d}",
                "Contrato": f"{item:02d}/2026",
                "Início": "2026-01-01",
                "Fim": "2027-12-31",
                "Valor atual": 1_000_000 + item,
                "Instrumento vigente": "Contrato",
                "Remanescente total": 500_000 + item,
            })
        parameters = {
            "reference_year": 2025,
            "equity_value": 139_259_969.94,
            "gross_revenue": 420_350_912.61,
            "justification_text": (
                "A divergência decorre dos diferentes períodos de reconhecimento das "
                "receitas e das vigências contratuais futuras."
            ),
            "signatory_name": "GESTOR RESPONSÁVEL",
            "signatory_registration": "REGISTRO 123",
            "signatory_cpf": "000.000.000-00",
            "signatory_title": "Diretor",
        }
        pdf = generate_indices_pdf(rows, parameters, reference_date=today)
        reader = PdfReader(BytesIO(pdf))
        assert len(reader.pages) == 2
        for page in reader.pages:
            assert float(page.mediabox.height) > float(page.mediabox.width)
        first_text = reader.pages[0].extract_text()
        second_text = reader.pages[1].extract_text()
        assert "DECLARAÇÃO DE CONTRATOS" in first_text
        assert "CONTRATANTE DE TESTE 65" in first_text
        assert "D.1" in second_text
        assert "JUSTIFICATIVA" in second_text
        assert "GESTOR RESPONSÁVEL" in second_text

        app_source = Path("app.py").read_text(encoding="utf-8")
        assert 'APP_VERSION = "25"' in app_source
        assert "Este contrato exige inscrição no CNO?" in app_source
        assert "Cadastrar outro diretor, gestor ou responsável" in app_source
        assert "Gerar declaração oficial de Índices em PDF" in app_source
        assert "Gerar declaração em Word" not in app_source

    print("Testes da versão 25 concluídos com sucesso.")


if __name__ == "__main__":
    run()
