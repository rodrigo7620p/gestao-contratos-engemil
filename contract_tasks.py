from __future__ import annotations

"""Notificação automática das providências iniciais de um contrato/aditivo:
garantia contratual e ART.

Sempre que um contrato novo é cadastrado, ou um aditivo/apostilamento é
lançado e seu documento é anexado, o sistema verifica se já existe garantia
e ART vinculadas àquele instrumento especificamente. Quando falta alguma
das duas, um único e-mail consolidado (listando cada providência pendente
e o respectivo responsável) é enviado para o(s) e-mail(is) de grupo
cadastrados (contract_task_group_recipients); responsáveis marcados para
"envio individual" (contract_task_responsibles.notify_individually) também
recebem cópia, assim como o engenheiro e o responsável administrativo do
contrato, quando cadastrados (ver extra_recipients).

O assunto do e-mail segue um padrão fixo para facilitar a comunicação entre
departamentos: {centro_de_custo}_{código_do_instrumento}_{sigla_do_órgão}_
{número_do_contrato}_{ação}, ex.: "01_01_00001_1ºTA_ANA_25-2026_ASSINADO"."""

import re

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
    "ATA": "ATA",
}

_AGENCY_SIGLA_DASH_PATTERN = re.compile(r"[-–—]\s*(?P<sigla>[^-–—]+?)\s*$")
_AGENCY_SIGLA_PAREN_PATTERN = re.compile(r"\((?P<sigla>[^()]+)\)\s*$")


def _instrument_code(kind_label: str, ordinal: str | None, ata_derived: bool = False) -> str:
    base_code = DOCUMENT_TYPE_CODES.get(str(kind_label or "").strip().upper(), "DOC")
    ordinal_prefix = str(ordinal or "").strip()
    code = f"{ordinal_prefix}{base_code}" if ordinal_prefix and base_code != "CTR" else base_code
    # Um contrato (ou aditivo) decorrente de uma ATA usa o código do
    # instrumento normal, mas prefixado com "ATA-" no assunto — associa
    # visualmente os dois sem confundir com o código "ATA" isolado, usado
    # só no aviso de registro da própria ATA (notify_ata_registration).
    return f"ATA-{code}" if ata_derived else code


def _agency_subject_token(agency: str) -> str:
    """Extrai só a sigla do órgão para o assunto do e-mail — o trecho após
    o último traço do nome (ex.: "SESC/GO (CALDAS NOVAS)" a partir de
    "SERVIÇO SOCIAL DO COMÉRCIO – SESC/GO (CALDAS NOVAS)"), preservando um
    eventual complemento entre parênteses que identifique a unidade. Sem
    traço, usa a sigla entre parênteses no final do nome; sem nenhum dos
    dois, usa o nome completo (não há sigla explícita para extrair)."""
    text = re.sub(r"\s+", " ", str(agency or "")).strip()
    match = _AGENCY_SIGLA_DASH_PATTERN.search(text) or _AGENCY_SIGLA_PAREN_PATTERN.search(text)
    sigla = match.group("sigla").strip() if match else text
    return re.sub(r"\s+", "-", sigla) or "ORGAO"


def build_task_email_subject(
    cost_center, kind_label, ordinal, agency, contract_number, action_tag="ASSINADO",
    ata_derived: bool = False,
) -> str:
    cost_center_part = re.sub(r"\s+", "_", str(cost_center or "").strip()).strip("_")
    instrument_code = _instrument_code(kind_label, ordinal, ata_derived)
    acronym = _agency_subject_token(agency)
    contract_part = str(contract_number or "").replace("/", "-").replace(" ", "")
    return "_".join(filter(None, [
        cost_center_part, instrument_code, acronym, contract_part, action_tag,
    ]))


def active_task_responsibles(task_type: str) -> list[dict]:
    return [
        dict(row) for row in query(
            """SELECT responsible_name,responsible_email,notify_individually
            FROM contract_task_responsibles
            WHERE task_type=? AND active=1 ORDER BY responsible_name""",
            (task_type,),
        )
    ]


def active_group_recipients() -> list[str]:
    return [
        row["email"] for row in query(
            "SELECT email FROM contract_task_group_recipients WHERE active=1 ORDER BY email"
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
    ata_number: str | None = None,
    kind_label: str,
    ordinal: str | None,
    cost_center: str,
    client: str,
    contract_number: str,
    document_bytes: bytes | None = None,
    document_filename: str | None = None,
    action_tag: str = "ASSINADO",
    extra_recipients: list[str] | None = None,
) -> list[str]:
    """Verifica garantia/ART pendentes para o instrumento recém-lançado e
    envia UM único e-mail consolidado listando cada providência pendente e
    o responsável correspondente. Devolve a lista de e-mails efetivamente
    notificados — vazia quando nada está pendente ou quando não há
    responsável/grupo cadastrado para as providências pendentes.

    Aceita tanto contratos/aditivos regulares (contract_id/amendment_id)
    quanto contratos decorrentes de ATA e seus aditivos
    (ata_contract_id/ata_amendment_id — quando presentes, o assunto ganha o
    prefixo "ATA-" no código do instrumento, ex. "ATA-CTR", associando os
    dois visualmente, e `ata_number` deve trazer o número da própria ATA
    para o corpo do e-mail deixar claro tanto o número da ATA quanto o do
    contrato decorrente). `extra_recipients` recebe cópia do mesmo e-mail
    (ex.: engenheiro e responsável administrativo do contrato) além dos
    e-mails de grupo/individuais já cadastrados."""
    missing = _missing_tasks(contract_id, amendment_id, ata_contract_id, ata_amendment_id)
    if not missing:
        return []
    is_ata_derived = ata_contract_id is not None
    is_amendment = bool(amendment_id or ata_amendment_id)
    instrument_label = (
        f"{ordinal} {kind_label}".strip().title() if is_amendment else "novo contrato"
    )
    document_label = (
        instrument_label if is_amendment else str(kind_label or "Contrato").strip().title()
    )
    contract_reference = (
        f"{contract_number or cost_center} (decorrente da ATA {ata_number})"
        if is_ata_derived and ata_number else (contract_number or cost_center)
    )

    task_lines = []
    individual_recipients = []
    for task_type in missing:
        for person in active_task_responsibles(task_type):
            task_lines.append(
                f"{len(task_lines) + 1:02d} - {person['responsible_name']}, conforme "
                f"{instrument_label} do contrato {contract_reference} "
                f"({client}), favor {TASK_LABELS[task_type]} correspondente."
            )
            if person.get("notify_individually"):
                individual_recipients.append(person["responsible_email"])
    if not task_lines:
        return []

    recipients = list(dict.fromkeys(active_group_recipients() + individual_recipients))
    if not recipients:
        # Sem e-mail de grupo nem responsável marcado para envio individual:
        # notifica direto cada responsável para o aviso não se perder.
        recipients = list(dict.fromkeys(
            person["responsible_email"]
            for task_type in missing
            for person in active_task_responsibles(task_type)
        ))
    if not recipients:
        return []

    subject = build_task_email_subject(
        cost_center, kind_label, ordinal, client, contract_number, action_tag,
        ata_derived=is_ata_derived,
    )
    attachments = [(document_filename, document_bytes)] if document_bytes and document_filename else None
    intro = f"Segue em anexo o {document_label} assinado entre as partes.\n\n" if attachments else ""
    closing_object = "providências" if len(task_lines) > 1 else "providência"
    ata_line = f"ATA de origem: {ata_number}\n" if is_ata_derived and ata_number else ""
    body = (
        "Prezado(a),\n\n"
        f"{intro}"
        + "\n\n".join(task_lines) +
        "\n\n"
        f"Centro de custo: {cost_center}\n"
        f"Contratante: {client}\n"
        f"{ata_line}"
        f"Instrumento: {instrument_label}\n"
        + ("\nDocumento em anexo.\n" if attachments else "\n") +
        "\nApós a providência, responda a este e-mail com a confirmação e as "
        "evidências da execução, assegurando o registro e a rastreabilidade do "
        f"cumprimento da{'s' if len(task_lines) > 1 else ''} {closing_object}."
    )
    ok, _ = send_email(recipients, subject, body, cc=extra_recipients, attachments=attachments)
    return recipients if ok else []


def notify_ata_registration(
    *, cost_center: str, client: str, contract_number: str,
    extra_recipients: list[str] | None = None,
) -> list[str]:
    """Avisa a equipe que um novo centro de custo foi reservado para uma
    ATA — só para conhecimento, SEM cobrar garantia contratual nem ART. A
    ATA em si não gera essas obrigações; elas só passam a valer quando os
    contratos decorrentes dela forem cadastrados e assinados, ocasião em
    que o fluxo normal (notify_contract_task_needs) passa a valer para
    cada um deles."""
    recipients = list(dict.fromkeys(active_group_recipients()))
    if not recipients:
        return []
    subject = build_task_email_subject(
        cost_center, "ATA", None, client, contract_number, action_tag="REGISTRADA",
    )
    body = (
        "Prezado(a),\n\n"
        f"Foi reservado o centro de custo {cost_center} para a ATA de registro de "
        f"preços firmada com {client}"
        + (f" (nº {contract_number})" if contract_number else "") + ".\n\n"
        "Este cadastro é só para conhecimento da equipe — a ATA, por si só, não gera "
        "obrigação de garantia contratual nem de ART. Essas providências só serão "
        "cobradas quando os contratos decorrentes dela forem cadastrados; assim que a "
        "ATA e cada contrato oriundo dela forem assinados, seguimos normalmente os "
        "passos de garantia e ART.\n\n"
        "Nenhuma ação é necessária neste momento."
    )
    ok, _ = send_email(recipients, subject, body, cc=extra_recipients)
    return recipients if ok else []
