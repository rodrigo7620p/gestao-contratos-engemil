from __future__ import annotations

"""Notificação automática das providências iniciais de um contrato/aditivo:
garantia contratual e ART.

Sempre que um contrato novo é cadastrado, ou um aditivo/apostilamento é
lançado e seu documento é anexado, o sistema verifica se já existe garantia
e ART vinculadas àquele instrumento especificamente. Quando falta alguma
das duas, avisa por e-mail o(s) responsável(is) cadastrado(s) para aquela
providência (ver contract_task_responsibles) — cada um recebe uma mensagem
endereçada a si, com o documento em anexo quando disponível.

O assunto do e-mail segue um padrão fixo para facilitar a comunicação entre
departamentos: {centro_de_custo}_{código_do_instrumento}_{sigla_do_órgão}_
{número_do_contrato}_{ação}, ex.: "01_01_00001_1ºTA_ANA_25-2026_ASSINADO"."""

import re

from contract_utils import extract_agency_acronym
from db import query
from notifications import send_email

TASK_GARANTIA = "GARANTIA"
TASK_ART = "ART"
TASK_LABELS = {
    TASK_GARANTIA: "providenciar a garantia contratual",
    TASK_ART: "providenciar a atualização das ARTs",
}

DOCUMENT_TYPE_CODES = {
    "CONTRATO": "CTR",
    "TERMO ADITIVO": "TA",
    "TERMO DE APOSTILAMENTO": "TAP",
}


def _instrument_code(kind_label: str, ordinal: str | None) -> str:
    base_code = DOCUMENT_TYPE_CODES.get(str(kind_label or "").strip().upper(), "DOC")
    ordinal_prefix = str(ordinal or "").strip()
    return f"{ordinal_prefix}{base_code}" if ordinal_prefix and base_code != "CTR" else base_code


def build_task_email_subject(
    cost_center, kind_label, ordinal, agency, contract_number, action_tag="ASSINADO",
) -> str:
    cost_center_part = re.sub(r"[.\s]+", "_", str(cost_center or "").strip()).strip("_")
    instrument_code = _instrument_code(kind_label, ordinal)
    acronym = extract_agency_acronym(agency) or re.sub(r"\s+", "-", str(agency or "ORGAO").strip())
    contract_part = str(contract_number or "").replace("/", "-").replace(" ", "")
    return "_".join(filter(None, [
        cost_center_part, instrument_code, acronym, contract_part, action_tag,
    ]))


def active_task_responsibles(task_type: str) -> list[dict]:
    return [
        dict(row) for row in query(
            """SELECT responsible_name,responsible_email FROM contract_task_responsibles
            WHERE task_type=? AND active=1 ORDER BY responsible_name""",
            (task_type,),
        )
    ]


def _missing_tasks(
    contract_id: int | None,
    amendment_id: int | None,
    ata_contract_id: int | None = None,
    ata_amendment_id: int | None = None,
) -> list[str]:
    if ata_contract_id is not None:
        if ata_amendment_id:
            guarantee_filter, art_filter, param = (
                "ata_amendment_id=?", "ata_amendment_id=?", ata_amendment_id,
            )
        else:
            guarantee_filter = "ata_contract_id=? AND ata_amendment_id IS NULL"
            art_filter = "ata_contract_id=? AND ata_amendment_id IS NULL"
            param = ata_contract_id
    elif amendment_id:
        guarantee_filter, art_filter, param = "amendment_id=?", "amendment_id=?", amendment_id
    else:
        guarantee_filter = "contract_id=? AND amendment_id IS NULL"
        art_filter = "contract_id=? AND amendment_id IS NULL"
        param = contract_id
    guarantees = query(
        f"SELECT request_status FROM contract_guarantees WHERE {guarantee_filter}", (param,),
    )
    missing = []
    if not guarantees or all(
        str(row["request_status"] or "").strip().upper() == "A SOLICITAR" for row in guarantees
    ):
        missing.append(TASK_GARANTIA)
    arts = query(f"SELECT id FROM arts WHERE {art_filter}", (param,))
    if not arts:
        missing.append(TASK_ART)
    return missing


def notify_contract_task_needs(
    *,
    contract_id: int | None = None,
    amendment_id: int | None = None,
    ata_contract_id: int | None = None,
    ata_amendment_id: int | None = None,
    kind_label: str,
    ordinal: str | None,
    cost_center: str,
    client: str,
    contract_number: str,
    document_bytes: bytes | None = None,
    document_filename: str | None = None,
    action_tag: str = "ASSINADO",
) -> list[tuple[str, str]]:
    """Verifica garantia/ART pendentes para o instrumento recém-lançado e
    notifica os responsáveis cadastrados. Devolve a lista de (tipo, e-mail)
    efetivamente notificados — vazia quando nada está pendente ou quando
    não há responsável cadastrado para o tipo pendente.

    Aceita tanto contratos/aditivos regulares (contract_id/amendment_id)
    quanto contratos decorrentes de ATA e seus aditivos
    (ata_contract_id/ata_amendment_id)."""
    missing = _missing_tasks(contract_id, amendment_id, ata_contract_id, ata_amendment_id)
    if not missing:
        return []
    is_amendment = bool(amendment_id or ata_amendment_id)
    instrument_label = (
        f"{ordinal} {kind_label}".strip().title() if is_amendment else "novo contrato"
    )
    subject = build_task_email_subject(
        cost_center, kind_label, ordinal, client, contract_number, action_tag,
    )
    attachments = [(document_filename, document_bytes)] if document_bytes and document_filename else None
    notified = []
    for task_type in missing:
        for person in active_task_responsibles(task_type):
            body = (
                f"{person['responsible_name']}, conforme {instrument_label} do contrato "
                f"{contract_number or cost_center} ({client}), favor "
                f"{TASK_LABELS[task_type]} correspondente.\n\n"
                f"Centro de custo: {cost_center}\n"
                f"Contratante: {client}\n"
                f"Instrumento: {instrument_label}\n"
                + ("\nDocumento em anexo.\n" if attachments else "\n") +
                "\nApós a providência, responda a este e-mail com a confirmação e as "
                "evidências da execução, assegurando o registro e a rastreabilidade do "
                "cumprimento da providência."
            )
            ok, _ = send_email(
                person["responsible_email"], subject, body, attachments=attachments,
            )
            if ok:
                notified.append((task_type, person["responsible_email"]))
    return notified
