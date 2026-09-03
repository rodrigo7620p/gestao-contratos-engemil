from __future__ import annotations

from datetime import date, datetime, timedelta
from html import escape
import re

from bids import (
    bid_process_aggregate_values,
    bid_process_structure_label,
    format_estimated_value_display,
)
from contract_utils import extract_agency_acronym, humanize_remaining
from db import archive_expired_contracts, connect, execute, init_db, query
from notifications import send_email, send_test_email, smtp_status

BID_SCHEDULE_EXCLUDED_STATUSES = {"REVOGADA / CANCELADA", "DESERTA / FRACASSADA"}


FINAL_STATUSES = {"CONCLUÍDA", "CONCLUIDA", "CANCELADA", "CANCELADO"}


def _brl(value):
    formatted = f"{float(value or 0):,.2f}"
    return "R$ " + formatted.replace(",", "_").replace(".", ",").replace("_", ".")


def _row_value(row, key, default=""):
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def _subject_token(value, fallback):
    token = re.sub(r"\s+", "-", str(value or "").strip().upper())
    token = re.sub(r"[^A-Z0-9À-ÖØ-Ý._-]", "-", token)
    token = re.sub(r"-+", "-", token).strip("-_.")
    return token or fallback


def standardized_email_subject(row, situation):
    """Padroniza centro de custo, sigla do órgão e situação do alerta."""
    cost_center = _subject_token(_row_value(row, "cost_center"), "SEM-CC")
    acronym = extract_agency_acronym(_row_value(row, "client"))
    acronym = _subject_token(acronym, "SEM-SIGLA")
    return f"{cost_center}_{acronym}_[{situation}]"


def obligation_notification_text(row, today=None):
    today = today or date.today()
    due = date.fromisoformat(str(row["due_date"])[:10])
    days = (due - today).days
    if days < 0:
        timing = f"VENCIDA HÁ {abs(days)} DIA(S)"
    elif days == 0:
        timing = "VENCE HOJE"
    else:
        timing = f"VENCE EM {days} DIA(S)"
    subject = standardized_email_subject(row, timing)
    body = (
        f"CONTROLE DE OBRIGAÇÃO CONTRATUAL — {timing}\n\n"
        f"Contrato: {row['contract_number'] or 'não informado'}\n"
        f"Centro de custo: {row['cost_center']}\n"
        f"Órgão/contratante: {row['client']}\n"
        f"Obrigação: {row['title']}\n"
        f"Categoria: {row['category'] or 'não informada'}\n"
        f"Prioridade: {row['priority'] or 'MÉDIA'}\n"
        f"Responsável: {row['responsible_name'] or 'não informado'}\n"
        f"Prazo: {due.strftime('%d/%m/%Y')}\n\n"
        f"Orientações:\n{row['notes'] or 'Sem orientações adicionais.'}\n\n"
        "Após o atendimento da demanda, responda a este e-mail com a confirmação "
        "e as evidências da execução, assegurando o registro e a rastreabilidade "
        "do cumprimento da obrigação."
    )
    return subject, body


def send_obligation_alert(obligation_id, force=False, today=None):
    today = today or date.today()
    rows = query(
        """SELECT o.*,c.client,c.contract_number,c.cost_center
        FROM obligations o JOIN contracts c ON c.id=o.contract_id
        WHERE o.id=?""",
        (obligation_id,),
    )
    if not rows:
        return False, "Obrigação não encontrada."
    row = dict(rows[0])
    status = str(row["status"] or "").strip().upper()
    if status in FINAL_STATUSES:
        return False, "A obrigação já está concluída ou cancelada."
    if not force and not bool(row["notification_enabled"]):
        return False, "Os alertas por e-mail estão desabilitados para esta obrigação."
    if not row["responsible_email"]:
        return False, "A obrigação não possui e-mail de responsável."
    try:
        due = date.fromisoformat(str(row["due_date"])[:10])
    except ValueError:
        return False, "A obrigação não possui uma data de vencimento válida."
    advance_days = max(0, int(row["advance_days"] or 0))
    if not force and today < due - timedelta(days=advance_days):
        return False, "A obrigação ainda não atingiu o período de alerta."
    frequency = max(1, int(row["reminder_frequency_days"] or 7))
    if not force and row["last_reminder_at"]:
        try:
            last_date = datetime.fromisoformat(str(row["last_reminder_at"])).date()
        except ValueError:
            last_date = date.fromisoformat(str(row["last_reminder_at"])[:10])
        if (today - last_date).days < frequency:
            return False, "A próxima cobrança ainda não atingiu a frequência configurada."
    subject, body = obligation_notification_text(row, today)
    ok, message = send_email(
        row["responsible_email"],
        subject,
        body,
        cc=row["copy_emails"],
    )
    if ok:
        execute(
            """UPDATE obligations SET notified_at=CURRENT_TIMESTAMP,
            last_reminder_at=CURRENT_TIMESTAMP,reminder_count=COALESCE(reminder_count,0)+1
            WHERE id=?""",
            (obligation_id,),
        )
        execute(
            """INSERT OR IGNORE INTO notification_log(
            event_type,reference_id,event_date,recipient) VALUES('OBRIGACAO_LEMBRETE',?,?,?)""",
            (obligation_id, today.isoformat(), row["responsible_email"]),
        )
    return ok, message


def process_obligation_alerts(today=None):
    today = today or date.today()
    rows = query(
        """SELECT o.id,o.status,o.due_date FROM obligations o
        JOIN contracts c ON c.id=o.contract_id
        WHERE c.archived=0 AND o.notification_enabled=1
        AND UPPER(COALESCE(o.status,'')) NOT IN ('CONCLUÍDA','CONCLUIDA','CANCELADA','CANCELADO')
        ORDER BY o.due_date"""
    )
    result = {"checked": len(rows), "sent": 0, "overdue": 0}
    for row in rows:
        try:
            due = date.fromisoformat(str(row["due_date"])[:10])
        except ValueError:
            continue
        if due < today:
            result["overdue"] += 1
            if str(row["status"] or "").strip().upper() == "PENDENTE":
                execute("UPDATE obligations SET status='VENCIDA' WHERE id=?", (row["id"],))
        ok, _ = send_obligation_alert(row["id"], today=today)
        if ok:
            result["sent"] += 1
    return result


def contract_expiry_notification_text(row, alert_days, today=None):
    today = today or date.today()
    end_date = date.fromisoformat(str(row["effective_end"])[:10])
    contract_reference = row["contract_number"] or row["cost_center"] or "não informado"
    remaining_days = max(0, (end_date - today).days)
    timing = "VENCE HOJE" if remaining_days == 0 else f"VENCE EM {remaining_days} DIA(S)"
    subject = standardized_email_subject(row, timing)
    if alert_days == 15:
        required_action = (
            "Confirme se haverá termo aditivo de prorrogação. Caso não haja, "
            "confirme o encerramento conforme a vigência contratual e providencie "
            "as obrigações administrativas de fechamento."
        )
    else:
        required_action = (
            "Verifique imediatamente com o órgão contratante se haverá termo "
            "aditivo de prorrogação e inicie os procedimentos administrativos "
            "necessários."
        )
    body = (
        f"CONTROLE DE VIGÊNCIA CONTRATUAL — {timing}\n\n"
        f"Contrato: {contract_reference}\n"
        f"Centro de custo: {row['cost_center'] or 'não informado'}\n"
        f"Órgão/contratante: {row['client']}\n"
        f"Instrumento vigente: {row['effective_instrument'] or 'Contrato'}\n"
        f"Engenheiro responsável: {row['engineer_name'] or 'não informado'}\n"
        f"Fim da vigência atual: {end_date.strftime('%d/%m/%Y')}\n"
        f"Prazo restante: {humanize_remaining(end_date, today)}\n\n"
        f"Ação necessária:\n{required_action}\n\n"
        "Após a definição, atualize a ficha do contrato na plataforma de "
        "Gestão Contratual ENGEMIL."
    )
    return subject, body


def process_contract_expiry_alerts(today=None):
    """Envia uma comunicação única nas janelas de 30 e 15 dias da vigência atual."""
    today = today or date.today()
    rows = query(
        """SELECT c.id,c.cost_center,c.client,c.contract_number,
        c.manager_email,c.engineer_name,c.engineer_email,
        COALESCE(
            (SELECT a.end_date FROM amendments a
             WHERE a.contract_id=c.id
             AND a.end_date IS NOT NULL AND a.end_date<>''
             AND NOT (
                UPPER(TRIM(COALESCE(a.ordinal,'')))
                    IN ('INICIAL','CONTRATO INICIAL')
                AND UPPER(TRIM(COALESCE(a.kind,'')))
                    IN ('CONTRATO','CONTRATO INICIAL')
             )
             ORDER BY a.id DESC LIMIT 1),
            c.end_date
        ) effective_end,
        COALESCE(
            (SELECT TRIM(COALESCE(a.ordinal,'') || ' ' || COALESCE(a.kind,''))
             FROM amendments a
             WHERE a.contract_id=c.id
             AND NOT (
                UPPER(TRIM(COALESCE(a.ordinal,'')))
                    IN ('INICIAL','CONTRATO INICIAL')
                AND UPPER(TRIM(COALESCE(a.kind,'')))
                    IN ('CONTRATO','CONTRATO INICIAL')
             )
             ORDER BY a.id DESC LIMIT 1),
            'Contrato'
        ) effective_instrument
        FROM contracts c
        WHERE c.archived=0 AND c.formalized=1
        ORDER BY effective_end,c.client"""
    )
    result = {
        "checked": len(rows),
        "sent_30": 0,
        "sent_15": 0,
        "missing_engineer_email": [],
    }
    for raw in rows:
        row = dict(raw)
        try:
            end_date = date.fromisoformat(str(row["effective_end"])[:10])
        except (TypeError, ValueError):
            continue
        days = (end_date - today).days
        if 16 <= days <= 30:
            alert_days = 30
        elif 0 <= days <= 15:
            alert_days = 15
        else:
            continue
        recipient = str(row["engineer_email"] or "").strip()
        if not recipient:
            result["missing_engineer_email"].append(
                {
                    "contract_id": row["id"],
                    "contract": row["contract_number"] or row["cost_center"],
                    "client": row["client"],
                    "end_date": end_date.isoformat(),
                }
            )
            continue
        event_type = f"CONTRATO_VENCIMENTO_{alert_days}_DIAS"
        already_sent = query(
            """SELECT id FROM notification_log
            WHERE event_type=? AND reference_id=? AND event_date=? AND recipient=?""",
            (event_type, row["id"], end_date.isoformat(), recipient),
        )
        if already_sent:
            continue
        subject, body = contract_expiry_notification_text(row, alert_days, today)
        copy_email = (
            row["manager_email"]
            if str(row["manager_email"] or "").strip() != recipient
            else None
        )
        ok, _ = send_email(recipient, subject, body, cc=copy_email)
        if ok:
            execute(
                """INSERT OR IGNORE INTO notification_log(
                event_type,reference_id,event_date,recipient)
                VALUES(?,?,?,?)""",
                (event_type, row["id"], end_date.isoformat(), recipient),
            )
            result[f"sent_{alert_days}"] += 1
    return result


def guarantee_expiry_notification_text(row, today=None):
    today = today or date.today()
    end_date = date.fromisoformat(str(row["end_date"])[:10])
    days = (end_date - today).days
    if days < 0:
        timing = f"GARANTIA VENCIDA HÁ {abs(days)} DIA(S)"
    elif days == 0:
        timing = "GARANTIA VENCE HOJE"
    else:
        timing = f"GARANTIA VENCE EM {days} DIA(S)"
    guarantee_name = (
        row.get("custom_type")
        if str(row.get("guarantee_type") or "").upper() == "OUTRO"
        else row.get("guarantee_type")
    )
    subject = standardized_email_subject(row, timing)
    body = (
        f"CONTROLE DE GARANTIAS E SEGUROS — {timing}\n\n"
        f"Contrato: {row.get('contract_number') or 'não informado'}\n"
        f"Centro de custo: {row.get('cost_center') or 'não informado'}\n"
        f"Órgão/contratante: {row.get('client') or 'não informado'}\n"
        f"Tipo: {guarantee_name or 'não informado'}\n"
        f"Modalidade: {row.get('modality') or 'não informada'}\n"
        f"Apólice/garantia: {row.get('policy_number') or 'não informada'}\n"
        f"Instrumento relacionado: {row.get('instrument_scope') or 'Contrato'}\n"
        f"Valor exigido: {_brl(row.get('required_amount'))}\n"
        f"Fim da vigência: {end_date.strftime('%d/%m/%Y')}\n\n"
        "Verifique a necessidade de renovação, substituição ou emissão de endosso, "
        "considerando a vigência e as condições do instrumento contratual atual.\n\n"
        "Após o atendimento, responda a este e-mail com a confirmação e os documentos "
        "comprobatórios, preservando a rastreabilidade da providência."
    )
    return subject, body


def process_guarantee_alerts(today=None):
    """Processa alertas de vigência e de prazo para apresentação de garantias."""
    today = today or date.today()
    rows = [dict(row) for row in query(
        """SELECT g.*,c.client,c.contract_number,c.cost_center,c.engineer_name,
        c.engineer_email,c.manager_name,c.manager_email
        FROM contract_guarantees g
        JOIN contracts c ON c.id=g.contract_id
        WHERE c.archived=0 AND g.notification_enabled=1
        AND UPPER(COALESCE(g.request_status,'')) NOT IN ('DISPENSADA','CANCELADA')
        ORDER BY g.end_date,g.id"""
    )]
    result = {
        "checked": len(rows),
        "expiry_sent_60": 0,
        "expiry_sent_30": 0,
        "expiry_sent_15": 0,
        "request_sent": 0,
        "missing_email": [],
    }
    for row in rows:
        recipient = str(
            row.get("responsible_email") or row.get("engineer_email")
            or row.get("manager_email") or ""
        ).strip()
        if not recipient:
            result["missing_email"].append({
                "guarantee_id": row["id"],
                "contract": row.get("contract_number") or row.get("cost_center"),
            })
            continue
        copies = []
        for value in (row.get("copy_emails"), row.get("manager_email")):
            if value and str(value).strip() != recipient and str(value).strip() not in copies:
                copies.append(str(value).strip())
        copy_emails = "; ".join(copies) or None
        if row.get("end_date"):
            try:
                end_date = date.fromisoformat(str(row["end_date"])[:10])
            except ValueError:
                end_date = None
            if end_date:
                days = (end_date - today).days
                if 31 <= days <= 60:
                    alert_window = 60
                elif 16 <= days <= 30:
                    alert_window = 30
                elif 0 <= days <= 15:
                    alert_window = 15
                else:
                    alert_window = None
                if alert_window:
                    event_type = f"GARANTIA_VENCIMENTO_{alert_window}_DIAS"
                    sent = query(
                        """SELECT id FROM notification_log WHERE event_type=?
                        AND reference_id=? AND event_date=? AND recipient=?""",
                        (event_type, row["id"], end_date.isoformat(), recipient),
                    )
                    if not sent:
                        subject, body = guarantee_expiry_notification_text(row, today)
                        ok, _ = send_email(recipient, subject, body, cc=copy_emails)
                        if ok:
                            execute(
                                """INSERT OR IGNORE INTO notification_log(
                                event_type,reference_id,event_date,recipient)
                                VALUES(?,?,?,?)""",
                                (event_type, row["id"], end_date.isoformat(), recipient),
                            )
                            result[f"expiry_sent_{alert_window}"] += 1
        request_status = str(row.get("request_status") or "").strip().upper()
        if row.get("request_due_date") and request_status in {
            "A SOLICITAR", "SOLICITADA", "PENDENTE DE CORREÇÃO"
        }:
            try:
                request_due = date.fromisoformat(str(row["request_due_date"])[:10])
            except ValueError:
                request_due = None
            if request_due and (request_due - today).days <= 15:
                event_type = "GARANTIA_PRAZO_APRESENTACAO"
                sent = query(
                    """SELECT id FROM notification_log WHERE event_type=?
                    AND reference_id=? AND event_date=? AND recipient=?""",
                    (event_type, row["id"], request_due.isoformat(), recipient),
                )
                if not sent:
                    days = (request_due - today).days
                    timing = (
                        f"PRAZO DA GARANTIA VENCIDO HÁ {abs(days)} DIA(S)"
                        if days < 0 else (
                            "PRAZO DA GARANTIA VENCE HOJE"
                            if days == 0 else f"PRAZO DA GARANTIA VENCE EM {days} DIA(S)"
                        )
                    )
                    ok, _ = send_email(
                        recipient,
                        standardized_email_subject(row, timing),
                        (
                            f"Contrato: {row.get('contract_number') or 'não informado'}\n"
                            f"Centro de custo: {row.get('cost_center') or 'não informado'}\n"
                            f"Órgão/contratante: {row.get('client') or 'não informado'}\n"
                            f"Garantia/seguro: {row.get('guarantee_type') or 'não informado'}\n"
                            f"Prazo para apresentação: {request_due.strftime('%d/%m/%Y')}\n\n"
                            "Após o atendimento, responda a este e-mail com a confirmação e "
                            "os documentos comprobatórios da providência."
                        ),
                        cc=copy_emails,
                    )
                    if ok:
                        execute(
                            """INSERT OR IGNORE INTO notification_log(
                            event_type,reference_id,event_date,recipient)
                            VALUES(?,?,?,?)""",
                            (event_type, row["id"], request_due.isoformat(), recipient),
                        )
                        result["request_sent"] += 1
    return result


def sesmt_notification_text(kind, row, today=None):
    """kind: 'EXAME' (exame ocupacional/ASO) ou 'TREINAMENTO' (NR/certificado)."""
    today = today or date.today()
    end_date = date.fromisoformat(str(row["valid_until"])[:10])
    days = (end_date - today).days
    noun = "EXAME OCUPACIONAL" if kind == "EXAME" else "TREINAMENTO/CERTIFICADO"
    if days < 0:
        timing = f"{noun} VENCIDO HÁ {abs(days)} DIA(S)"
    elif days == 0:
        timing = f"{noun} VENCE HOJE"
    else:
        timing = f"{noun} VENCE EM {days} DIA(S)"
    subject = standardized_email_subject(row, timing)
    if kind == "EXAME":
        detail = (
            f"Tipo de exame: {row.get('exam_type') or 'não informado'}\n"
            f"Resultado: {row.get('result') or 'não informado'}\n"
        )
    else:
        detail = (
            f"Treinamento: {row.get('training_name') or 'não informado'}\n"
            f"Instituição/instrutor: {row.get('provider') or 'não informada'}\n"
        )
    body = (
        f"CONTROLE SESMT — {timing}\n\n"
        f"Profissional: {row.get('full_name') or 'não informado'}\n"
        f"Cargo/função: {row.get('role_title') or 'não informado'}\n"
        f"Contrato: {row.get('contract_number') or 'não informado'}\n"
        f"Centro de custo: {row.get('cost_center') or 'não informado'}\n"
        f"Órgão/contratante: {row.get('client') or 'não informado'}\n"
        f"{detail}"
        f"Validade: {end_date.strftime('%d/%m/%Y')}\n\n"
        "Verifique a necessidade de reagendar o exame ou o treinamento, "
        "considerando o prazo de validade indicado.\n\n"
        "Após o atendimento, responda a este e-mail com a confirmação e os "
        "documentos comprobatórios, preservando a rastreabilidade da providência."
    )
    return subject, body


def process_sesmt_alerts(today=None):
    """Processa alertas de vencimento de exames ocupacionais (ASO) e de
    treinamentos/certificados (NRs) do SESMT. Como o cadastro de
    profissionais não tem um e-mail de contato próprio, avisa o engenheiro
    responsável (ou, na falta dele, o responsável administrativo) do
    contrato ao qual o profissional está vinculado — mesmo padrão de
    fallback já usado nos alertas de garantias."""
    today = today or date.today()
    exam_rows = [dict(row) for row in query(
        """SELECT e.id,e.exam_type,e.result,e.valid_until,
        p.full_name,p.role_title,p.contract_id,
        c.client,c.contract_number,c.cost_center,c.engineer_email,c.manager_email
        FROM sesmt_exams e
        JOIN sesmt_professionals p ON p.id=e.professional_id
        JOIN contracts c ON c.id=p.contract_id
        WHERE e.valid_until IS NOT NULL AND c.archived=0 AND p.status='ATIVO'
        ORDER BY e.valid_until,e.id"""
    )]
    training_rows = [dict(row) for row in query(
        """SELECT t.id,t.training_name,t.provider,t.valid_until,
        p.full_name,p.role_title,p.contract_id,
        c.client,c.contract_number,c.cost_center,c.engineer_email,c.manager_email
        FROM sesmt_trainings t
        JOIN sesmt_professionals p ON p.id=t.professional_id
        JOIN contracts c ON c.id=p.contract_id
        WHERE t.valid_until IS NOT NULL AND c.archived=0 AND p.status='ATIVO'
        ORDER BY t.valid_until,t.id"""
    )]
    result = {
        "checked": len(exam_rows) + len(training_rows),
        "expiry_sent_30": 0,
        "expiry_sent_15": 0,
        "expiry_sent_0": 0,
        "missing_email": [],
    }
    for kind, rows in (("EXAME", exam_rows), ("TREINAMENTO", training_rows)):
        for row in rows:
            recipient = str(row.get("engineer_email") or row.get("manager_email") or "").strip()
            if not recipient:
                result["missing_email"].append({
                    "id": row["id"], "kind": kind, "professional": row.get("full_name"),
                })
                continue
            try:
                end_date = date.fromisoformat(str(row["valid_until"])[:10])
            except ValueError:
                continue
            days = (end_date - today).days
            if 16 <= days <= 30:
                alert_window = 30
            elif 1 <= days <= 15:
                alert_window = 15
            elif days <= 0:
                alert_window = 0
            else:
                continue
            event_type = f"SESMT_{kind}_VENCIMENTO_{alert_window}_DIAS"
            sent = query(
                """SELECT id FROM notification_log WHERE event_type=?
                AND reference_id=? AND event_date=? AND recipient=?""",
                (event_type, row["id"], end_date.isoformat(), recipient),
            )
            if sent:
                continue
            subject, body = sesmt_notification_text(kind, row, today)
            ok, _ = send_email(recipient, subject, body)
            if ok:
                execute(
                    """INSERT OR IGNORE INTO notification_log(
                    event_type,reference_id,event_date,recipient)
                    VALUES(?,?,?,?)""",
                    (event_type, row["id"], end_date.isoformat(), recipient),
                )
                result[f"expiry_sent_{alert_window}"] += 1
    return result


def process_repactuation_alerts():
    init_db()
    today = date.today()
    archived_ids = archive_expired_contracts()
    rows = query(
        """SELECT u.*,c.client,c.contract_number,c.cost_center,c.manager_name,c.manager_email,
        c.engineer_name,c.engineer_email FROM contract_unions u
        JOIN contracts c ON c.id=u.contract_id
        WHERE c.archived=0 AND u.next_repactuation IS NOT NULL AND u.next_repactuation<>''"""
    )
    result = {"checked": 0, "created": 0, "sent": 0, "archived": len(archived_ids)}
    for row in rows:
        result["checked"] += 1
        try:
            repactuation = date.fromisoformat(str(row["next_repactuation"])[:10])
        except ValueError:
            continue
        alert_date = repactuation - timedelta(days=90)
        if not (alert_date <= today <= repactuation):
            continue
        title = f"Preparar repactuação — {row['union_name']}"
        existing = query(
            "SELECT id FROM obligations WHERE contract_id=? AND title=? AND due_date=?",
            (row["contract_id"], title, repactuation.isoformat()),
        )
        recipient_name = row["manager_name"] or row["engineer_name"] or "Responsável"
        recipient = row["manager_email"] or row["engineer_email"]
        copy_email = (
            row["engineer_email"] if recipient == row["manager_email"] else row["manager_email"]
        )
        if not existing:
            obligation_id = execute(
                """INSERT INTO obligations(contract_id,title,category,due_date,responsible_name,
                responsible_email,copy_emails,priority,status,advance_days,
                notification_enabled,reminder_frequency_days,notes)
                VALUES(?,?,?,?,?,?,?,'ALTA','PENDENTE',90,1,7,?)""",
                (
                    row["contract_id"], title, "REPACTUAÇÃO", repactuation.isoformat(),
                    recipient_name, recipient, copy_email,
                    f"Alerta automático de 90 dias. CCT: {row['collective_agreement'] or 'não informada'}.",
                ),
            )
            result["created"] += 1
        else:
            obligation_id = existing[0]["id"]
        if not recipient:
            continue
        sent = query(
            """SELECT id FROM notification_log WHERE event_type='REPACTUACAO_90_DIAS'
            AND reference_id=? AND event_date=? AND recipient=?""",
            (row["id"], repactuation.isoformat(), recipient),
        )
        if sent:
            continue
        ok, _ = send_email(
            recipient,
            standardized_email_subject(
                row,
                (
                    "REPACTUAÇÃO HOJE"
                    if (repactuation - today).days == 0
                    else f"REPACTUAÇÃO EM {(repactuation - today).days} DIA(S)"
                ),
            ),
            (
                f"Contrato: {row['contract_number']} | Centro de custo: {row['cost_center']}\n"
                f"Sindicato: {row['union_name']}\n"
                f"CCT: {row['collective_agreement'] or 'não informada'}\n"
                f"Data prevista: {repactuation.strftime('%d/%m/%Y')}\n\n"
                "Providencie a documentação e a memória de cálculo da repactuação."
            ),
            cc=copy_email,
        )
        if ok:
            execute(
                """INSERT OR IGNORE INTO notification_log(event_type,reference_id,event_date,recipient)
                VALUES('REPACTUACAO_90_DIAS',?,?,?)""",
                (row["id"], repactuation.isoformat(), recipient),
            )
            execute(
                """UPDATE obligations SET notified_at=CURRENT_TIMESTAMP,
                last_reminder_at=CURRENT_TIMESTAMP,reminder_count=COALESCE(reminder_count,0)+1
                WHERE id=?""",
                (obligation_id,),
            )
            result["sent"] += 1
    obligation_result = process_obligation_alerts(today)
    result["obligations_checked"] = obligation_result["checked"]
    result["obligations_sent"] = obligation_result["sent"]
    result["obligations_overdue"] = obligation_result["overdue"]
    expiry_result = process_contract_expiry_alerts(today)
    result["contract_expiry_checked"] = expiry_result["checked"]
    result["contract_expiry_sent_30"] = expiry_result["sent_30"]
    result["contract_expiry_sent_15"] = expiry_result["sent_15"]
    result["contract_expiry_missing_engineer_email"] = expiry_result[
        "missing_engineer_email"
    ]
    guarantee_result = process_guarantee_alerts(today)
    result["guarantees_checked"] = guarantee_result["checked"]
    result["guarantees_expiry_sent_60"] = guarantee_result["expiry_sent_60"]
    result["guarantees_expiry_sent_30"] = guarantee_result["expiry_sent_30"]
    result["guarantees_expiry_sent_15"] = guarantee_result["expiry_sent_15"]
    result["guarantees_request_sent"] = guarantee_result["request_sent"]
    result["guarantees_missing_email"] = guarantee_result["missing_email"]
    sesmt_result = process_sesmt_alerts(today)
    result["sesmt_checked"] = sesmt_result["checked"]
    result["sesmt_expiry_sent_30"] = sesmt_result["expiry_sent_30"]
    result["sesmt_expiry_sent_15"] = sesmt_result["expiry_sent_15"]
    result["sesmt_expiry_sent_0"] = sesmt_result["expiry_sent_0"]
    result["sesmt_missing_email"] = sesmt_result["missing_email"]
    return result


def todays_bid_schedule_rows(today=None):
    """Monta as linhas de licitações com disputa marcada para hoje, na
    ordem: dia, hora, uasg, nº da licitação, órgão, escopo, estrutura,
    objeto, valor estimado. Reaproveita o mesmo cálculo de valor agregado e
    estrutura (grupos/itens) usado na tela de Licitações, para os números
    do e-mail nunca divergirem dos exibidos no sistema."""
    today = today or date.today()
    processes = [
        dict(row) for row in query(
            """SELECT * FROM bid_processes WHERE dispute_date=? ORDER BY dispute_time""",
            (today.isoformat(),),
        )
        if str(row["status"] or "").strip().upper() not in BID_SCHEDULE_EXCLUDED_STATUSES
    ]
    rows = []
    for process in processes:
        lots = [
            dict(row) for row in query(
                "SELECT * FROM bid_lots WHERE bid_process_id=? ORDER BY id",
                (process["id"],),
            )
        ]
        aggregate = bid_process_aggregate_values(process, lots)
        rows.append({
            "dia": today.strftime("%d/%m/%Y"),
            "hora": process.get("dispute_time") or "—",
            "uasg": process.get("uasg") or "—",
            "numero": process.get("edital_number") or process.get("process_number") or "—",
            "orgao": process.get("agency") or "—",
            "escopo": process.get("scope") or "—",
            "estrutura": bid_process_structure_label(lots),
            "objeto": process.get("object") or "—",
            "valor_estimado": format_estimated_value_display(aggregate),
        })
    return rows


def _bid_schedule_email_content(rows, today):
    date_label = today.strftime("%d/%m/%Y")
    headers = [
        "Dia", "Hora", "UASG", "Nº da licitação", "Órgão", "Escopo", "Estrutura",
        "Objeto", "Valor estimado",
    ]
    plain_lines = [f"LICITAÇÕES DO DIA — {date_label}", ""]
    html_rows = []
    for row in rows:
        values = [
            row["dia"], row["hora"], row["uasg"], row["numero"], row["orgao"],
            row["escopo"], row["estrutura"], row["objeto"],
            row["valor_estimado"].replace("\n", " — "),
        ]
        plain_lines.append(" | ".join(f"{h}: {v}" for h, v in zip(headers, values)))
        plain_lines.append("")
        html_rows.append(
            "<tr>" + "".join(
                f'<td style="padding:8px 12px;border:1px solid #ddd;">{escape(str(v)).replace(chr(10), "<br>")}</td>'
                for v in values
            ) + "</tr>"
        )
    plain_lines.append(
        "Mensagem automática do Sistema de Gestão Contratual ENGEMIL — "
        "não é necessário responder."
    )
    plain_body = "\n".join(plain_lines)
    header_html = "".join(
        f'<th style="padding:8px 12px;border:1px solid #ddd;background:#5a1235;'
        f'color:#fff;text-align:left;">{escape(h)}</th>'
        for h in headers
    )
    html_body = f"""
    <div style="font-family:Arial,Helvetica,sans-serif;color:#1f1b1d;">
        <h2 style="color:#5a1235;">Licitações do dia — {escape(date_label)}</h2>
        <table style="border-collapse:collapse;width:100%;font-size:14px;">
            <thead><tr>{header_html}</tr></thead>
            <tbody>{"".join(html_rows)}</tbody>
        </table>
        <p style="color:#6b7280;font-size:12px;margin-top:16px;">
            Mensagem automática do Sistema de Gestão Contratual ENGEMIL —
            não é necessário responder.
        </p>
    </div>
    """
    subject = f"LICITAÇÕES DO DIA — {date_label} ({len(rows)})"
    return subject, plain_body, html_body


def send_daily_bid_schedule(today=None, force=False):
    """Envia, para os e-mails cadastrados em bid_schedule_recipients, o
    quadro das licitações com disputa marcada para hoje. Roda de
    segunda a sexta (parado nos fins de semana, quando não há pregão).

    A ideia é que MAIS DE UM gatilho possa chamar esta função no mesmo dia
    (a tarefa agendada local, o próprio app publicado na nuvem como reforço
    ao abrir uma sessão, um cron externo) sem nunca duplicar e-mail — por
    isso a "reserva" da vaga em notification_log usa INSERT OR IGNORE (que
    é atômico graças à restrição UNIQUE da tabela) ANTES de enviar, e só
    envia se realmente conseguiu reservar. Checar-e-só-depois-inserir (como
    era antes) tinha uma janela de corrida: dois processos podiam checar
    "ainda não foi enviado" ao mesmo tempo e os dois enviarem.

    Os destinatários pendentes do dia são reservados um a um (mantendo o
    registro individual em notification_log, para nunca reenviar a quem já
    recebeu), mas o e-mail em si sai em UM ÚNICO envio com todos eles —
    antes cada um recebia uma mensagem separada, e notifications.send_email()
    inclui automaticamente o CC padrão (SMTP_DEFAULT_CC) em toda mensagem
    que manda; com N mensagens separadas, quem estivesse nesse CC padrão
    recebia N cópias do mesmo quadro no mesmo dia — daí o e-mail duplicado
    mesmo com a reserva em notification_log funcionando certinho (ela nunca
    permitiu reservar a vaga duas vezes; o problema era o CC repetido a
    cada mensagem individual)."""
    init_db()
    today = today or date.today()
    result = {"sent": 0, "skipped_weekend": False, "recipients": 0, "bids_today": 0}
    if not force and today.weekday() >= 5:
        result["skipped_weekend"] = True
        return result
    recipients = [
        row["email"] for row in query(
            "SELECT email FROM bid_schedule_recipients WHERE active=1 ORDER BY email"
        )
    ]
    result["recipients"] = len(recipients)
    if not recipients:
        return result
    rows = todays_bid_schedule_rows(today)
    result["bids_today"] = len(rows)
    if not rows:
        return result
    subject, plain_body, html_body = _bid_schedule_email_content(rows, today)
    pending = []
    for recipient in recipients:
        if force:
            execute(
                """DELETE FROM notification_log WHERE event_type='LICITACOES_DIA'
                AND reference_id=0 AND event_date=? AND recipient=?""",
                (today.isoformat(), recipient),
            )
        with connect() as conn:
            claim = conn.execute(
                """INSERT OR IGNORE INTO notification_log(
                event_type,reference_id,event_date,recipient)
                VALUES('LICITACOES_DIA',0,?,?)""",
                (today.isoformat(), recipient),
            )
            claimed = bool(claim.rowcount)
        if claimed:
            pending.append(recipient)
    if not pending:
        return result
    ok, _ = send_email(pending, subject, plain_body, html_body=html_body)
    if ok:
        result["sent"] = len(pending)
    else:
        # Reservou as vagas mas não conseguiu enviar (ex.: SMTP fora do
        # ar) — libera de novo para a próxima chamada tentar, em vez de
        # perder o aviso silenciosamente.
        for recipient in pending:
            execute(
                """DELETE FROM notification_log WHERE event_type='LICITACOES_DIA'
                AND reference_id=0 AND event_date=? AND recipient=?""",
                (today.isoformat(), recipient),
            )
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Processa os alertas automáticos da Gestão Contratual ENGEMIL."
    )
    parser.add_argument(
        "--test-email",
        help="Envia somente uma mensagem de teste para o endereço informado.",
    )
    parser.add_argument(
        "--smtp-status",
        action="store_true",
        help="Exibe a configuração SMTP efetiva sem revelar a senha.",
    )
    parser.add_argument(
        "--bid-schedule",
        action="store_true",
        help=(
            "Envia o quadro de licitações do dia aos e-mails cadastrados "
            "(segunda a sexta; use --force para ignorar o filtro de dia útil "
            "e o controle de envio único do dia)."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Usado com --bid-schedule para reenviar mesmo já tendo sido enviado hoje.",
    )
    args = parser.parse_args()
    if args.bid_schedule:
        print(send_daily_bid_schedule(force=args.force))
    elif args.smtp_status:
        status = smtp_status()
        print("SMTP configurado: " + ("SIM" if status["configured"] else "NAO"))
        print(f"Origem: {status['source']}")
        print(f"Servidor: {status['host']}:{status['port']} ({status['security']})")
        print(f"Usuario: {status['user']}")
        print(f"Remetente: {status['sender']}")
        if status["missing"]:
            print("Campos pendentes: " + ", ".join(status["missing"]))
    elif args.test_email:
        print(send_test_email(args.test_email))
    else:
        print(process_repactuation_alerts())
