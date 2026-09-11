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
import zipfile
from io import BytesIO

from db import query
from notifications import normalize_recipients, send_email

TASK_TOTVS = "TOTVS"
TASK_GARANTIA = "GARANTIA"
TASK_ART = "ART"
TASK_LABELS = {
    TASK_TOTVS: "ativar o novo contrato no TOTVS, para futuras movimentações de controle",
    # A partir de agora quem recebe este pedido é a própria corretora de
    # seguros (cadastrada em "Responsáveis por providências iniciais" com
    # o e-mail dela), não mais um funcionário intermediando a cotação.
    TASK_GARANTIA: "realizar cotação para endosso de garantia contratual correspondente",
    TASK_ART: "providenciar a atualização das ARTs correspondente",
}

DOCUMENT_TYPE_CODES = {
    "CONTRATO": "CTR",
    "TERMO ADITIVO": "TA",
    "TERMO DE APOSTILAMENTO": "TAP",
    "ATA": "ATA",
}

_BASE_REFERENCE_LABELS = {
    "TOTAL": "Valor total do contrato",
    "ANUAL": "Valor anual estimado",
    "MANUAL": "Outro/informado manualmente",
}


def _brl(value) -> str:
    return f"R$ {float(value or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def guarantee_context_lines(
    contract_id=None, amendment_id=None, ata_contract_id=None, ata_amendment_id=None,
) -> list[str]:
    """Monta as linhas de contexto (referência do valor-base, base
    considerada, percentual, valor exigido, modalidade) a partir da
    garantia contratual já registrada — primeiro tenta a garantia
    específica do instrumento informado (aditivo/contrato decorrente),
    e cai para a garantia do contrato principal quando não há uma
    específica (a mesma % costuma valer para o contrato todo). Devolve []
    quando não há nenhuma garantia contratual com percentual definido —
    nada de útil para acrescentar ao e-mail nesse caso."""
    row = None
    if amendment_id:
        rows = query(
            """SELECT * FROM contract_guarantees WHERE amendment_id=?
            AND guarantee_type='GARANTIA CONTRATUAL' ORDER BY id DESC LIMIT 1""",
            (amendment_id,),
        )
        row = dict(rows[0]) if rows else None
    elif ata_amendment_id:
        rows = query(
            """SELECT * FROM contract_guarantees WHERE ata_amendment_id=?
            AND guarantee_type='GARANTIA CONTRATUAL' ORDER BY id DESC LIMIT 1""",
            (ata_amendment_id,),
        )
        row = dict(rows[0]) if rows else None
    if not row and contract_id:
        rows = query(
            """SELECT * FROM contract_guarantees WHERE contract_id=? AND amendment_id IS NULL
            AND ata_contract_id IS NULL AND guarantee_type='GARANTIA CONTRATUAL'
            ORDER BY id DESC LIMIT 1""",
            (contract_id,),
        )
        row = dict(rows[0]) if rows else None
    if not row or not row.get("percentage"):
        return []
    base_reference = _BASE_REFERENCE_LABELS.get(
        str(row.get("calculation_base_reference") or "").upper(), "Valor total do contrato",
    )
    modality = str(row.get("modality") or "").strip()
    return [
        f"Referência do valor-base da garantia: {base_reference}",
        f"Base contratual considerada: {_brl(row.get('calculation_base'))}",
        f"Percentual de garantia exigido: {float(row['percentage']):.2f}%",
        f"Valor exigido: {_brl(row.get('required_amount'))}",
        f"Modalidade indicada: {modality}" if modality else
        "Modalidade: a definir pela seguradora, conforme esta solicitação.",
    ]

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


_REDUNDANT_NUMBER_PREFIX = re.compile(r"^(ATA|CTR)[\s\-_/]+", re.IGNORECASE)


def _clean_subject_number(contract_number: str) -> str:
    """Tira um prefixo redundante como "ATA-" ou "CTR-" do número, quando a
    pessoa já digita o número dessa forma (ex.: "ATA-12/2026") — o assunto
    já identifica o instrumento no código anterior (ATA, CTR, ATA-CTR...),
    então repetir a sigla no número também fica redundante."""
    return _REDUNDANT_NUMBER_PREFIX.sub("", str(contract_number or "").strip())


def build_task_email_subject(
    cost_center, kind_label, ordinal, agency, contract_number, action_tag="ASSINADO",
    ata_derived: bool = False,
) -> str:
    cost_center_part = re.sub(r"\s+", "_", str(cost_center or "").strip()).strip("_")
    instrument_code = _instrument_code(kind_label, ordinal, ata_derived)
    acronym = _agency_subject_token(agency)
    contract_part = _clean_subject_number(contract_number).replace("/", "-").replace(" ", "")
    return "_".join(filter(None, [
        cost_center_part, instrument_code, acronym, contract_part, action_tag,
    ]))


def active_task_responsibles(task_type: str) -> list[dict]:
    """`responsible_email` pode conter mais de um endereço (separados por
    vírgula ou ponto e vírgula) — útil quando o "responsável" é, por
    exemplo, uma corretora de seguros com vários contatos que devem
    receber a mesma mensagem em cópia. Ainda assim gera só UMA linha
    numerada por responsável (ver notify_contract_task_needs/
    notify_ata_registration), nunca uma linha repetida por e-mail."""
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
    only_tasks: list[str] | None = None,
    extra_attachments: list[tuple[str, bytes]] | None = None,
    context_lines: list[str] | None = None,
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
    e-mails de grupo/individuais já cadastrados.

    Todo cadastro NOVO (não um aditivo/apostilamento) também pede a
    ativação no TOTVS como item 1, antes de garantia e ART — diferente
    delas, não há tabela própria para checar se isso já foi feito, então
    é sempre solicitada de novo em cada contrato/contrato decorrente
    recém-cadastrado.

    `only_tasks`, quando informado, restringe o e-mail às providências
    dessa lista (ex.: [TASK_GARANTIA]) — usado para solicitar só a
    garantia contratual antes da assinatura, em um pré-contrato, sem
    cobrar TOTVS/ART, que só fazem sentido depois de o contrato existir
    de fato.

    `extra_attachments` recebe uma lista de (nome_do_arquivo, conteúdo) —
    além do documento único já suportado por document_bytes/
    document_filename (ex.: edital, minuta do contrato, planilha de
    valores, proposta), para dar à seguradora/responsável o material
    necessário para calcular e preparar a garantia. Quando há mais de um
    anexo ao todo, eles são compactados em um único .zip (mesmo padrão já
    usado no envio do e-mail de anúncio de novo contrato).

    `context_lines`, quando informado, é inserido no corpo do e-mail logo
    após a introdução e antes das linhas de providência — usado para
    identificar o certame/processo e informar um prazo dado pelo órgão,
    sem alterar o texto padrão dos demais avisos que não passam esse
    parâmetro."""
    missing = _missing_tasks(contract_id, amendment_id, ata_contract_id, ata_amendment_id)
    is_ata_derived = ata_contract_id is not None
    is_amendment = bool(amendment_id or ata_amendment_id)
    if not is_amendment:
        missing = [TASK_TOTVS] + missing
    if only_tasks is not None:
        missing = [task for task in missing if task in only_tasks]
    if not missing:
        return []
    instrument_label = (
        f"{ordinal} {kind_label}".strip().title() if is_amendment else "novo contrato"
    )
    contract_reference = (
        f"{contract_number or cost_center} (decorrente da ATA {ata_number})"
        if is_ata_derived and ata_number else (contract_number or cost_center)
    )
    # O instrumento/contrato já é identificado UMA vez, logo no início do
    # corpo (e também no assunto) — repetir "conforme <instrumento> do
    # contrato <número> (<contratante>)" em cada linha numerada ficava
    # cansativo quando há várias providências pendentes. Cada linha agora
    # só traz o nome do responsável e a ação dele.
    reference_phrase = (
        f"{instrument_label} do contrato {contract_reference} ({client})"
        if is_amendment else f"contrato {contract_reference} ({client})"
    )

    task_lines = []
    individual_recipients = []
    for task_type in missing:
        for person in active_task_responsibles(task_type):
            task_lines.append(
                f"{len(task_lines) + 1:02d} - {person['responsible_name']}, favor "
                f"{TASK_LABELS[task_type]}."
            )
            if person.get("notify_individually"):
                individual_recipients.extend(normalize_recipients(person["responsible_email"]))
    if not task_lines:
        return []

    task_recipients = list(dict.fromkeys(
        address
        for task_type in missing
        for person in active_task_responsibles(task_type)
        for address in normalize_recipients(person["responsible_email"])
    ))
    if only_tasks is not None:
        # Pedido isolado para uma única providência (ex.: só garantia, antes
        # da assinatura) — sempre inclui todos os e-mails cadastrados para
        # essa providência especificamente, com ou sem "envio individual"
        # marcado, além de eventual e-mail de grupo. Diferente do aviso
        # combinado de várias providências (abaixo), aqui não faz sentido o
        # responsável ficar de fora só porque não está marcado para cópia
        # individual — ele É o destinatário principal do pedido.
        recipients = list(dict.fromkeys(active_group_recipients() + task_recipients))
    else:
        recipients = list(dict.fromkeys(active_group_recipients() + individual_recipients))
        if not recipients:
            # Sem e-mail de grupo nem responsável marcado para envio individual:
            # notifica direto cada responsável para o aviso não se perder.
            recipients = task_recipients
    if not recipients:
        return []

    subject = build_task_email_subject(
        cost_center, kind_label, ordinal, client, contract_number, action_tag,
        ata_derived=is_ata_derived,
    )
    attachment_items = (
        [(document_filename, document_bytes)] if document_bytes and document_filename else []
    )
    attachment_items.extend(extra_attachments or [])
    if len(attachment_items) > 1:
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for filename, content in attachment_items:
                zf.writestr(filename, content)
        attachment_items = [("Documentos_anexos.zip", zip_buffer.getvalue())]
    attachments = attachment_items or None
    has_signed_document = bool(document_bytes and document_filename)
    intro = (
        f"Segue em anexo o documento assinado entre as partes, referente ao "
        f"{reference_phrase}.\n\n"
        if has_signed_document else
        f"Seguem as providências pendentes referentes ao {reference_phrase}:\n\n"
    )
    context_block = ("\n".join(context_lines) + "\n\n") if context_lines else ""
    closing_object = "providências" if len(task_lines) > 1 else "providência"
    ata_line = f"ATA de origem: {ata_number}\n" if is_ata_derived and ata_number else ""
    body = (
        "Prezado(a),\n\n"
        f"{intro}"
        f"{context_block}"
        + "\n\n".join(task_lines) +
        "\n\n"
        f"Centro de custo: {cost_center}\n"
        f"Contratante: {client}\n"
        f"{ata_line}"
        f"Instrumento: {instrument_label}\n"
        + ("\nDocumento(s) em anexo.\n" if attachments else "\n") +
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
    ATA — SEM cobrar garantia contratual nem ART, já que a ATA em si não
    gera essas obrigações (elas só passam a valer quando os contratos
    decorrentes dela forem cadastrados e assinados, ocasião em que o fluxo
    normal — notify_contract_task_needs — passa a valer para cada um
    deles). Mas a ATA em si já pede UMA ação: ativar o novo contrato no
    TOTVS, para futuras movimentações de controle — igual ao pedido de
    garantia/ART, precisa de um responsável cadastrado
    (contract_task_responsibles, task_type TOTVS) para o e-mail sair."""
    task_lines = []
    individual_recipients = []
    for person in active_task_responsibles(TASK_TOTVS):
        task_lines.append(
            f"{len(task_lines) + 1:02d} - {person['responsible_name']}, favor "
            f"{TASK_LABELS[TASK_TOTVS]}."
        )
        if person.get("notify_individually"):
            individual_recipients.extend(normalize_recipients(person["responsible_email"]))
    if not task_lines:
        return []

    recipients = list(dict.fromkeys(active_group_recipients() + individual_recipients))
    if not recipients:
        recipients = list(dict.fromkeys(
            address
            for person in active_task_responsibles(TASK_TOTVS)
            for address in normalize_recipients(person["responsible_email"])
        ))
    if not recipients:
        return []

    subject = build_task_email_subject(
        cost_center, "ATA", None, client, contract_number, action_tag="REGISTRADA",
    )
    body = (
        "Prezado(a),\n\n"
        f"Segue a providência pendente referente à ATA {contract_number or cost_center} "
        f"({client}):\n\n"
        + "\n\n".join(task_lines) +
        "\n\n"
        f"Centro de custo: {cost_center}\n"
        f"Contratante: {client}\n"
        "Instrumento: nova ATA\n\n"
        "Esta ATA, por si só, não gera obrigação de garantia contratual nem de ART — "
        "essas providências só serão cobradas quando os contratos decorrentes dela "
        "forem cadastrados; assim que cada um for assinado, seguimos normalmente os "
        "passos de garantia e ART.\n\n"
        "Após a providência, responda a este e-mail com a confirmação e as evidências "
        "da execução, assegurando o registro e a rastreabilidade do cumprimento da "
        "providência."
    )
    ok, _ = send_email(recipients, subject, body, cc=extra_recipients)
    return recipients if ok else []
