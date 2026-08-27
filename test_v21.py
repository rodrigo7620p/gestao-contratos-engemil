import os
import re
import tempfile
from datetime import date, timedelta
from pathlib import Path


temporary = tempfile.TemporaryDirectory()
os.environ["GESTAO_DB_PATH"] = str(Path(temporary.name) / "test_v21.db")
os.environ["GESTAO_UPLOAD_DIR"] = str(Path(temporary.name) / "uploads")

import alerts  # noqa: E402
from contract_utils import humanize_remaining  # noqa: E402
from db import execute, init_db, query  # noqa: E402


def run():
    init_db()
    contract_id = execute(
        """INSERT INTO contracts(
        cost_center,client,contract_number,category,start_date,end_date,
        original_value,current_value,engineer_name,engineer_email,manager_email)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "TESTE.V21",
            "ÓRGÃO DE TESTE - OT",
            "21/2026",
            "MANUTENÇÃO",
            "2024-01-01",
            (date.today() + timedelta(days=30)).isoformat(),
            1000,
            1000,
            "Engenheiro Teste",
            "engenheiro@example.com",
            "gestor@example.com",
        ),
    )
    initial_id = execute(
        """INSERT INTO amendments(
        contract_id,ordinal,kind,start_date,end_date,value)
        VALUES(?,'INICIAL','CONTRATO','2020-01-01','2021-01-01',1000)""",
        (contract_id,),
    )
    execute(
        """INSERT INTO contract_unions(
        contract_id,amendment_id,union_name)
        VALUES(?,?,'SINDICATO TESTE')""",
        (contract_id, initial_id),
    )
    execute(
        """INSERT INTO documents(
        contract_id,amendment_id,category,title,filename,stored_path)
        VALUES(?,?,'CONTRATO','Documento','documento.pdf','uploads/documento.pdf')""",
        (contract_id, initial_id),
    )
    init_db()
    assert not query("SELECT id FROM amendments WHERE id=?", (initial_id,))
    migrated_contract = query(
        """SELECT original_start_date,original_end_date
        FROM contracts WHERE id=?""",
        (contract_id,),
    )[0]
    assert migrated_contract["original_start_date"] == "2020-01-01"
    assert migrated_contract["original_end_date"] == "2021-01-01"
    assert query(
        "SELECT amendment_id FROM contract_unions WHERE contract_id=?",
        (contract_id,),
    )[0]["amendment_id"] is None
    assert query(
        "SELECT amendment_id FROM documents WHERE contract_id=?",
        (contract_id,),
    )[0]["amendment_id"] is None
    migration_logs = query(
        "SELECT id FROM audit_log WHERE action='MIGRAR CONTRATO INICIAL'"
    )
    assert len(migration_logs) == 1
    init_db()
    assert len(query(
        "SELECT id FROM audit_log WHERE action='MIGRAR CONTRATO INICIAL'"
    )) == 1

    ata_id = execute(
        """INSERT INTO contracts(
        cost_center,client,contract_number,category,start_date,end_date)
        VALUES('ATA.V21','ÓRGÃO ATA','ATA 21/2026','ATA','2026-01-01','2027-01-01')"""
    )
    ata_contract_id = execute(
        """INSERT INTO ata_contracts(
        ata_id,contract_number,client,start_date,end_date)
        VALUES(?,'DECORRENTE 1/2026','ÓRGÃO ATA','2026-01-01','2027-01-01')""",
        (ata_id,),
    )
    cno_id = execute(
        """INSERT INTO contract_cnos(
        contract_id,ata_contract_id,registration_number)
        VALUES(?,?,'CNO-TESTE-21')""",
        (ata_id, ata_contract_id),
    )
    assert query(
        "SELECT ata_contract_id FROM contract_cnos WHERE id=?", (cno_id,)
    )[0]["ata_contract_id"] == ata_contract_id
    execute(
        """INSERT INTO contracts(
        cost_center,client,contract_number,start_date,end_date,
        engineer_name,engineer_email)
        VALUES(?,?,?,?,?,?,?)""",
        (
            "TESTE.V21.15",
            "ÓRGÃO ALERTA 15",
            "15/2026",
            date.today().isoformat(),
            (date.today() + timedelta(days=15)).isoformat(),
            "Engenheira Teste",
            "engenheira@example.com",
        ),
    )
    execute(
        """INSERT INTO contracts(
        cost_center,client,contract_number,start_date,end_date)
        VALUES(?,?,?,?,?)""",
        (
            "TESTE.V21.SEM.EMAIL",
            "ÓRGÃO SEM E-MAIL",
            "10/2026",
            date.today().isoformat(),
            (date.today() + timedelta(days=10)).isoformat(),
        ),
    )

    sent_messages = []

    def fake_send_email(recipient, subject, body, cc=None):
        sent_messages.append((recipient, subject, body, cc))
        return True, "enviado"

    original_sender = alerts.send_email
    alerts.send_email = fake_send_email
    try:
        result = alerts.process_contract_expiry_alerts(date.today())
        assert result["sent_30"] == 1
        assert result["sent_15"] == 1
        assert len(result["missing_engineer_email"]) == 1
        assert len(sent_messages) == 2
        assert any("VENCE EM 30 DIA(S)" in message[1] for message in sent_messages)
        assert any(
            message[3] == "gestor@example.com"
            for message in sent_messages
            if "VENCE EM 30 DIA(S)" in message[1]
        )
        assert any(
            "VENCE EM 15 DIA(S)" in message[1] for message in sent_messages
        )
        repeated = alerts.process_contract_expiry_alerts(date.today())
        assert repeated["sent_30"] == 0
        assert repeated["sent_15"] == 0
        assert len(sent_messages) == 2
    finally:
        alerts.send_email = original_sender

    assert humanize_remaining(date.today() + timedelta(days=1)) == "Falta 1 dia"
    assert humanize_remaining(date.today()) == "Encerra hoje"
    assert humanize_remaining(date.today() - timedelta(days=2)) == "Encerrado há 2 dias"

    app_source = Path("app.py").read_text(encoding="utf-8")
    version_match = re.search(r'APP_VERSION\s*=\s*"(\d+)"', app_source)
    assert version_match and int(version_match.group(1)) >= 21
    assert '"Prazo restante"' in app_source
    assert "Contrato decorrente da ATA *" in app_source
    assert "Enviar e-mail de teste" in app_source
    assert Path("configurar_alertas_automaticos.bat").is_file()
    assert Path("testar_email.bat").is_file()
    print("Testes da versão 21 concluídos com sucesso.")


if __name__ == "__main__":
    run()
