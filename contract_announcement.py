from __future__ import annotations

"""Rascunho do e-mail de anúncio de uma licitação vencida, enviado
internamente (compras, RH, financeiro, SESMT, contratos etc.) assim que o
centro de custo é reservado — geralmente antes de o contrato ser assinado.

Monta assunto e corpo (texto simples e HTML) a partir dos dados já
preenchidos no pré-contrato (contracts.formalized=0), reaproveitando o
mesmo cálculo de garantia (guarantees.py) e de BDI (bdi.py) já usados nas
respectivas abas da ficha do contrato — a tabela de garantia/BDI no e-mail
segue o mesmo layout da planilha de referência usada manualmente para esse
aviso. É sempre um rascunho: quem cria o pré-contrato revisa e edita antes
de efetivamente enviar."""

import re
from html import escape

from bdi import calculate_bdi, tax_total
from contract_tasks import _agency_subject_token
from db import query
from guarantees import default_legal_basis

ANNOUNCEMENT_DOCUMENT_CATEGORIES = (
    "EDITAL", "TERMO DE REFERÊNCIA", "PLANILHA", "PROPOSTA HOMOLOGADA",
)

_BRAND_COLOR = "#5a1235"
_BORDER = "1px solid #ddd"


def _brl(value) -> str:
    return (
        f"R$ {float(value or 0):,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def _pct(value) -> str:
    return f"{float(value or 0):.2f}".replace(".", ",") + "%"


def build_announcement_subject(contract: dict) -> str:
    # Este e-mail só existe para pré-contratos (formalized=0) — ou seja, é
    # sempre um registro pendente de assinatura, seja ATA ou contrato
    # comum. O sufixo "REGISTRADA" deixa isso visível já no assunto, sem
    # precisar abrir o e-mail, no mesmo padrão usado pelos avisos de
    # providências (notify_ata_registration/notify_contract_task_needs).
    cost_center_part = re.sub(r"\s+", "_", str(contract.get("cost_center") or "").strip())
    sigla = _agency_subject_token(contract.get("client"))
    category = re.sub(r"\s+", "-", str(contract.get("category") or "").strip())
    object_tag = re.sub(r"\s+", "-", str(contract.get("object_identifier") or "").strip())
    return "_".join(filter(None, [cost_center_part, sigla, category, object_tag, "REGISTRADA"]))


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


def _html_table(rows: list[list[str]], *, header: str | None = None) -> str:
    """Uma tabela simples de 2-3 colunas no mesmo estilo das demais
    tabelas HTML do sistema (ver alerts.py, _bid_schedule_email_content)."""
    header_html = (
        f'<tr><th colspan="3" style="padding:8px 12px;border:{_BORDER};'
        f'background:{_BRAND_COLOR};color:#fff;text-align:left;">{escape(header)}</th></tr>'
    ) if header else ""
    body_html = "".join(
        "<tr>" + "".join(
            f'<td style="padding:6px 12px;border:{_BORDER};">{escape(str(cell))}</td>'
            for cell in row
        ) + "</tr>"
        for row in rows
    )
    return (
        f'<table style="border-collapse:collapse;width:100%;font-size:14px;margin:8px 0 16px;">'
        f"{header_html}{body_html}</table>"
    )


def _guarantee_sections(contract_id: int) -> tuple[list[str], str]:
    """Devolve (linhas em texto simples, HTML) das seções de garantia
    contratual e adicional, no mesmo layout usado manualmente até hoje."""
    guarantees = [
        dict(row) for row in query(
            "SELECT * FROM contract_guarantees WHERE contract_id=? AND amendment_id IS NULL "
            "AND ata_contract_id IS NULL ORDER BY id",
            (contract_id,),
        )
    ]
    plain: list[str] = []
    html_parts: list[str] = []

    contratual = next(
        (g for g in guarantees if g["guarantee_type"] == "GARANTIA CONTRATUAL"), None
    )
    if contratual:
        percent_text = _pct(contratual["percentage"])
        base_text = _brl(contratual["calculation_base"])
        required_text = _brl(contratual["required_amount"])
        explanation = (
            f"Conforme {default_legal_basis('GARANTIA CONTRATUAL')}, é necessária a "
            f"apresentação da garantia contratual no percentual de {percent_text} "
            f"aplicado sobre o valor total da contratação, atualmente de {base_text}. "
            f"Dessa forma, deverá ser providenciada a garantia no valor de "
            f"{required_text}, em atendimento às exigências previstas no instrumento "
            "convocatório, quando da formalização do contrato."
        )
        plain += [
            f"GARANTIA CONTRATUAL: {percent_text}",
            f"LANCE FINAL: {base_text} — Valor exigido: {required_text}",
            explanation, "",
        ]
        html_parts.append(
            _html_table([
                ["GARANTIA CONTRATUAL", "", percent_text],
                ["LANCE FINAL", base_text, required_text],
            ]) + f'<p style="margin:0 0 16px;">{escape(explanation)}</p>'
        )

    adicional = next(
        (g for g in guarantees if g["guarantee_type"] == "GARANTIA ADICIONAL"), None
    )
    if adicional:
        title = "GARANTIA ADICIONAL (obras e serviços de engenharia)"
        if str(adicional.get("request_status") or "").upper() == "DISPENSADA":
            explanation = (
                f"Conforme {default_legal_basis('GARANTIA ADICIONAL')}, a exigência de "
                "garantia contratual adicional não é aplicável ao presente caso."
            )
            plain += [f"{title}: NÃO SE APLICA", explanation, ""]
            html_parts.append(
                _html_table([[title, "", "NÃO SE APLICA"]])
                + f'<p style="margin:0 0 16px;">{escape(explanation)}</p>'
            )
        else:
            estimated_text = _brl(adicional["estimated_budget"])
            proposal_text = _brl(adicional["proposal_value"])
            required_text = _brl(adicional["required_amount"])
            plain += [
                title,
                f"ESTIMADO: {estimated_text}",
                f"LANCE FINAL: {proposal_text}",
                f"Valor exigido: {required_text}", "",
            ]
            html_parts.append(
                _html_table([
                    [title, "", ""],
                    ["ESTIMADO", estimated_text, ""],
                    ["LANCE FINAL", proposal_text, required_text],
                ])
            )

    return plain, "".join(html_parts)


def _bdi_sections(contract_id: int) -> tuple[list[str], str]:
    """Devolve (linhas em texto simples, HTML) de cada composição de BDI
    cadastrada, com o mesmo detalhamento numerado da planilha de
    referência (1 a 5, sub-itens de seguros/riscos/garantias e tributos,
    e o BDI ADOTADO calculado por bdi.calculate_bdi)."""
    bdis = [
        dict(row) for row in query(
            "SELECT * FROM contract_bdis WHERE contract_id=? ORDER BY id", (contract_id,)
        )
    ]
    plain: list[str] = []
    html_parts: list[str] = []
    for item in bdis:
        plain.append(item["name"] or "BDI")
        html_parts.append(f'<h4 style="margin:16px 0 4px;">{escape(item["name"] or "BDI")}</h4>')
        if str(item.get("calculation_method") or "FORMULA_COMPOSTA").upper() == "SOMA_DIRETA":
            adopted = calculate_bdi(item)
            rows = [
                ["Custos indiretos", "", _pct(item.get("indirect_costs"))],
                ["Lucro", "", _pct(item.get("profit"))],
                ["Tributos", "", _pct(tax_total(item))],
                ["BDI ADOTADO", "", _pct(adopted)],
            ]
            for label, _, value in rows:
                plain.append(f"{label}: {value}")
            html_parts.append(
                _html_table(rows, header="BONIFICAÇÃO E DESPESAS INDIRETAS - BDI")
            )
            continue

        seguros_riscos_garantias = (
            float(item.get("insurance") or 0) + float(item.get("risks") or 0)
            + float(item.get("guarantees") or 0) + float(item.get("other_indirect_costs") or 0)
        )
        taxes = float(tax_total(item))
        adopted = calculate_bdi(item)
        main_rows = [
            ["1", "ADMINISTRAÇÃO CENTRAL", _pct(item.get("central_administration"))],
            ["2", "SEGUROS, RISCOS E GARANTIAS", _pct(seguros_riscos_garantias)],
            ["3", "DESPESAS FINANCEIRAS", _pct(item.get("financial_expenses"))],
            ["4", "TRIBUTOS", _pct(taxes)],
            ["5", "LUCRO", _pct(item.get("profit"))],
            ["", "BDI ADOTADO", _pct(adopted)],
        ]
        for _, label, value in main_rows:
            plain.append(f"{label}: {value}")
        html_parts.append(_html_table(main_rows, header="BONIFICAÇÃO E DESPESAS INDIRETAS - BDI"))

        detail_rows = [
            ["2.1", "Seguros + Garantias", _pct(
                float(item.get("insurance") or 0) + float(item.get("guarantees") or 0)
            )],
            ["2.2", "Riscos", _pct(item.get("risks"))],
        ]
        if float(item.get("other_indirect_costs") or 0):
            detail_rows.append(["2.3", "Outros custos indiretos", _pct(item.get("other_indirect_costs"))])
        detail_rows.append(["", "TOTAL", _pct(seguros_riscos_garantias)])
        html_parts.append(_html_table(detail_rows, header="SEGUROS, RISCOS E GARANTIAS CONSIDERADOS"))

        tax_rows = [
            ["4.1", "ISS", _pct(item.get("iss"))],
            ["4.2", "PIS", _pct(item.get("pis"))],
            ["4.3", "COFINS", _pct(item.get("cofins"))],
            ["4.4", "CPRB", _pct(item.get("cprb"))],
        ]
        if float(item.get("other_taxes") or 0):
            tax_rows.append(["4.5", "Outros tributos", _pct(item.get("other_taxes"))])
        tax_rows.append(["", "TOTAL", _pct(taxes)])
        html_parts.append(_html_table(tax_rows, header="TRIBUTOS CONSIDERADOS"))

        regime = str(item.get("tax_regime") or "CONTRATO").upper()
        if regime != "CONTRATO":
            note = f"A composição teve seu custo definido de forma {regime}."
            plain.append(note)
            html_parts.append(f'<p style="margin:0 0 16px;color:#6b7280;font-size:12px;">{escape(note)}</p>')
        if item.get("notes"):
            plain.append(str(item["notes"]))
            html_parts.append(f'<p style="margin:0 0 16px;">{escape(str(item["notes"]))}</p>')
        plain.append("")
    return plain, "".join(html_parts)


def build_announcement_email(contract_id: int) -> tuple[str, str, str]:
    """Monta (assunto, corpo em texto simples, corpo em HTML) do rascunho a
    partir dos dados já cadastrados do pré-contrato — inclusive garantia
    contratual/adicional e composições de BDI, já calculadas e detalhadas
    no mesmo layout da planilha de referência usada manualmente para esse
    aviso."""
    contract = dict(query("SELECT * FROM contracts WHERE id=?", (contract_id,))[0])
    subject = build_announcement_subject(contract)

    intro = (
        "Encaminho para conhecimento a documentação do processo licitatório do qual "
        "fomos vencedores. Assim que o contrato estiver disponível, farei o devido "
        "encaminhamento."
    )
    plain = ["Prezado(a),", "", intro, ""]
    html = [
        f'<p>Prezado(a),</p><p>{escape(intro)}</p>',
    ]

    if contract.get("bid_number"):
        plain.append(f"Número do Certame: {contract['bid_number']}")
    if contract.get("process_number"):
        plain.append(f"Número do Processo: {contract['process_number']}")
    if contract.get("uasg"):
        plain.append(f"UASG: {contract['uasg']}")
    plain.append("")
    identification_rows = [
        (label, contract.get(field)) for label, field in (
            ("Número do Certame", "bid_number"),
            ("Número do Processo", "process_number"),
            ("UASG", "uasg"),
        ) if contract.get(field)
    ]
    if identification_rows:
        html.append(
            "".join(f"<p><strong>{escape(label)}:</strong> {escape(str(value))}</p>" for label, value in identification_rows)
        )

    if contract.get("object"):
        plain += ["Objeto", contract["object"], ""]
        html.append(
            f'<p><strong>Objeto</strong><br>{escape(contract["object"])}</p>'
        )

    plain += ["INFORMAÇÕES ADICIONAIS", ""]
    html.append(
        f'<h3 style="color:{_BRAND_COLOR};border-bottom:{_BORDER};padding-bottom:4px;">'
        "INFORMAÇÕES ADICIONAIS</h3>"
    )
    if contract.get("manager_name"):
        plain += [f"Gestor do contrato (ENGEMIL): {contract['manager_name']}", ""]
        html.append(
            _html_table([["GESTOR DO CONTRATO (ENGEMIL)", contract["manager_name"], ""]])
        )

    guarantee_plain, guarantee_html = _guarantee_sections(contract_id)
    plain += guarantee_plain
    html.append(guarantee_html)

    bdi_plain, bdi_html = _bdi_sections(contract_id)
    plain += bdi_plain
    html.append(bdi_html)

    closing = (
        "Mensagem gerada automaticamente pelo Sistema de Gestão Contratual ENGEMIL a "
        "partir dos dados do pré-contrato — revise antes de enviar."
    )
    plain.append(closing)
    html.append(f'<p class="ann-note" style="color:#6b7280;font-size:12px;">{escape(closing)}</p>')

    plain_body = "\n".join(plain)
    # O st.markdown(..., unsafe_allow_html=True) do preview renderiza este HTML
    # dentro da própria página do Streamlit (sem iframe), e o tema escuro do
    # Streamlit define cor de texto clara em <p>/<td>/<li> com uma regra mais
    # específica do que a herdada da cor do <div> — sem o !important escopado
    # pela classe abaixo, o texto sai quase invisível (cinza claro sobre fundo
    # branco). Os seletores ficam restritos a .announcement-email-preview para
    # não vazar para o resto da página.
    html_body = (
        '<div class="announcement-email-preview" style="font-family:Arial,'
        'Helvetica,sans-serif;color:#1f1b1d;background:#ffffff;padding:16px;">'
        '<style>'
        '.announcement-email-preview,.announcement-email-preview p,'
        '.announcement-email-preview li,.announcement-email-preview td,'
        '.announcement-email-preview strong,.announcement-email-preview h4'
        '{color:#1f1b1d !important;}'
        f'.announcement-email-preview h3{{color:{_BRAND_COLOR} !important;}}'
        '.announcement-email-preview th{color:#ffffff !important;}'
        '.announcement-email-preview p.ann-note{color:#6b7280 !important;}'
        '</style>'
        + "".join(html) + "</div>"
    )
    return subject, plain_body, html_body
