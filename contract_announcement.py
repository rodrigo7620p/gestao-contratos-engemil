from __future__ import annotations

"""Rascunho do e-mail de anúncio de uma licitação vencida, enviado
internamente (compras, RH, financeiro, SESMT, contratos etc.) assim que o
centro de custo é reservado — geralmente antes de o contrato ser assinado.

Monta assunto e corpo a partir dos dados já preenchidos no pré-contrato
(contracts.formalized=0), reaproveitando o mesmo cálculo de garantia usado
na aba Garantias e seguros. É sempre um rascunho: quem cria o pré-contrato
revisa e edita antes de efetivamente enviar."""

import re

from contract_tasks import _agency_subject_token
from db import query
from guarantees import default_legal_basis

ANNOUNCEMENT_DOCUMENT_CATEGORIES = (
    "EDITAL", "TERMO DE REFERÊNCIA", "PLANILHA", "PROPOSTA HOMOLOGADA",
)


def _brl(value) -> str:
    return (
        f"R$ {float(value or 0):,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def build_announcement_subject(contract: dict) -> str:
    cost_center_part = re.sub(r"\s+", "_", str(contract.get("cost_center") or "").strip())
    sigla = _agency_subject_token(contract.get("client"))
    category = re.sub(r"\s+", "-", str(contract.get("category") or "").strip())
    object_tag = re.sub(r"\s+", "-", str(contract.get("object_identifier") or "").strip())
    return "_".join(filter(None, [cost_center_part, sigla, category, object_tag]))


def announcement_attachments_available(contract_id: int) -> list[dict]:
    """Documentos do certame já anexados ao pré-contrato (edital, TR,
    planilha, proposta homologada), disponíveis para ir junto no e-mail."""
    placeholders = ",".join("?" for _ in ANNOUNCEMENT_DOCUMENT_CATEGORIES)
    return [
        dict(row) for row in query(
            f"""SELECT * FROM documents WHERE contract_id=? AND category IN ({placeholders})
            ORDER BY uploaded_at DESC""",
            (contract_id, *ANNOUNCEMENT_DOCUMENT_CATEGORIES),
        )
    ]


def build_announcement_email(contract_id: int) -> tuple[str, str]:
    """Monta (assunto, corpo) do rascunho a partir dos dados já cadastrados
    do pré-contrato — inclusive garantia contratual/adicional (calculadas)
    e as composições de BDI informadas."""
    contract = dict(query("SELECT * FROM contracts WHERE id=?", (contract_id,))[0])
    subject = build_announcement_subject(contract)

    lines = [
        "Prezado(a),",
        "",
        "Encaminho para conhecimento a documentação do processo licitatório do qual "
        "fomos vencedores. Assim que o contrato estiver disponível, farei o devido "
        "encaminhamento.",
        "",
    ]
    if contract.get("bid_number"):
        lines.append(f"Número do Certame: {contract['bid_number']}")
    if contract.get("process_number"):
        lines.append(f"Número do Processo: {contract['process_number']}")
    if contract.get("uasg"):
        lines.append(f"UASG: {contract['uasg']}")
    lines.append("")
    if contract.get("object"):
        lines += ["Objeto", contract["object"], ""]

    lines += ["INFORMAÇÕES ADICIONAIS", ""]
    if contract.get("manager_name"):
        lines += [f"Gestor do contrato (ENGEMIL): {contract['manager_name']}", ""]

    guarantees = [
        dict(row) for row in query(
            "SELECT * FROM contract_guarantees WHERE contract_id=? AND amendment_id IS NULL "
            "AND ata_contract_id IS NULL ORDER BY id",
            (contract_id,),
        )
    ]
    contratual = next(
        (g for g in guarantees if g["guarantee_type"] == "GARANTIA CONTRATUAL"), None
    )
    if contratual:
        percentage = contratual["percentage"] or 0
        percent_text = f"{percentage:.2f}".replace(".", ",")
        lines += [
            f"Garantia contratual: {percent_text}%",
            f"Conforme {default_legal_basis('GARANTIA CONTRATUAL')}, é necessária a "
            f"apresentação da garantia contratual no percentual de {percent_text}% "
            "aplicado sobre o valor total da contratação, atualmente de "
            f"{_brl(contratual['calculation_base'])}. Dessa forma, deverá ser "
            f"providenciada a garantia no valor de {_brl(contratual['required_amount'])}, "
            "quando da formalização do contrato.",
            "",
        ]
    adicional = next(
        (g for g in guarantees if g["guarantee_type"] == "GARANTIA ADICIONAL"), None
    )
    if adicional:
        if str(adicional.get("request_status") or "").upper() == "DISPENSADA":
            lines += [
                f"Garantia adicional (obras e serviços de engenharia): NÃO SE APLICA",
                f"Conforme {default_legal_basis('GARANTIA ADICIONAL')}, a exigência de "
                "garantia contratual adicional não é aplicável ao presente caso.",
                "",
            ]
        else:
            lines += [
                "Garantia adicional (obras e serviços de engenharia):",
                f"Estimado: {_brl(adicional['estimated_budget'])} — "
                f"Lance final: {_brl(adicional['proposal_value'])} — "
                f"Valor exigido: {_brl(adicional['required_amount'])}",
                "",
            ]

    bdis = [
        dict(row) for row in query(
            "SELECT name,notes FROM contract_bdis WHERE contract_id=? ORDER BY id",
            (contract_id,),
        )
    ]
    if bdis:
        lines.append("BDI:")
        for bdi in bdis:
            note = f" — {bdi['notes']}" if bdi.get("notes") else ""
            lines.append(f"- {bdi['name']}{note}")
        lines.append("")

    lines.append(
        "Mensagem gerada automaticamente pelo Sistema de Gestão Contratual ENGEMIL a "
        "partir dos dados do pré-contrato — revise antes de enviar."
    )
    body = "\n".join(lines)
    return subject, body
