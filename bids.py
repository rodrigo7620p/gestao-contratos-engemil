from __future__ import annotations

"""Integração do módulo Licitações.

Duas fontes de dados são tratadas de forma bem separada porque têm
naturezas diferentes:

1. PNCP (Portal Nacional de Contratações Públicas) — API pública, sem
   necessidade de chave, mantida pelo Governo Federal. Cobre editais
   publicados, atas de registro de preço e resultados homologados. NÃO
   expõe o mapa de lances/classificação em tempo real de uma disputa em
   andamento — isso é operacional da plataforma que está rodando o
   pregão (Compras.gov.br, Portal de Compras Públicas, BLL, Licitanet
   etc.), não do PNCP.
   Documentação oficial: https://pncp.gov.br/api/consulta/swagger-ui
   Manual: https://www.gov.br/pncp/pt-br/acesso-a-informacao/manuais

2. Portal de Compras Públicas — plataforma privada de pregão eletrônico
   (é a que gera relatórios de classificação como o do modelo enviado
   pela ENGEMIL). Tem uma API própria ("Biblioteca de Dados"), mas o
   acesso exige solicitar uma chave de integração pelo formulário oficial
   (prazo informado pela própria plataforma: até 7 dias úteis por
   e-mail). Este módulo já deixa o ponto de extensão pronto
   (`portal_compras_publicas_search`), mas ele só funciona depois que a
   ENGEMIL solicitar e configurar essa chave — ver GESTAO_LICITACOES.md
   para o passo a passo de solicitação.

Enquanto a chave não chega, o cadastro e a classificação são preenchidos
manualmente ou colados a partir do relatório exportado da própria
plataforma — exatamente como no modelo enviado.
"""

import os
import re
from datetime import date
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

from contract_utils import extract_agency_acronym, today_brt
from reports import brl

BASE_DIR = Path(__file__).resolve().parent
FONT_DIR = BASE_DIR / "assets" / "fonts"

# CNPJ da ENGEMIL Engenharia, Empreendimentos, Manutenção e Instalações Ltda.
# Usado como padrão na verificação automática de homologação no PNCP.
COMPANY_CNPJ = "04768702000170"

PNCP_BASE_URL = "https://pncp.gov.br/api/consulta/v1"
PNCP_TIMEOUT = 15

BURGUNDY = (90, 18, 53)          # #5A1235 — mesma cor institucional dos relatórios em Word
BURGUNDY_LIGHT = (243, 232, 237)  # #F3E8ED
WHITE = (255, 255, 255)
TEXT_DARK = (31, 27, 29)
ROW_ALT = (250, 244, 246)
GREEN_TEXT = (30, 110, 60)
RED_TEXT = (176, 42, 42)
ABOVE_ESTIMATE_TEXT = (181, 101, 29)  # laranja — sinaliza lance acima do valor estimado

PLATFORMS = [
    "COMPRASNET / COMPRAS.GOV.BR",
    "PORTAL DE COMPRAS PÚBLICAS",
    "LICITAÇÕES-E (BANCO DO BRASIL)",
    "PREGÃO ONLINE BANCO DO BRASIL",
    "PORTAL DE COMPRAS CAIXA (CAIXA ECONÔMICA FEDERAL)",
    "BLL COMPRAS",
    "BBMNET LICITAÇÕES",
    "BNC COMPRAS",
    "LICITANET",
    "OUTRO",
]
MODALITIES = [
    "Pregão Eletrônico",
    "Pregão Presencial",
    "Concorrência Eletrônica",
    "Concorrência Presencial",
    "Concurso",
    "Leilão Eletrônico",
    "Leilão Presencial",
    "Diálogo Competitivo",
    "Dispensa de Licitação",
    "Inexigibilidade de Licitação",
    "Credenciamento",
    "Outro",
]
DISPUTE_MODES = [
    "Aberto",
    "Fechado",
    "Aberto/Fechado",
    "Fechado/Aberto",
    "Randômico",
    "Outro",
]
BRAZILIAN_UF_OPTIONS = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
]
STATUSES = [
    "EM ANDAMENTO",
    "HOMOLOGADA - VENCEDORA",
    "HOMOLOGADA - NÃO VENCEDORA",
    "DESERTA / FRACASSADA",
    "SUSPENSA",
    "REVOGADA / CANCELADA",
]
RANKING_SITUATIONS = [
    "CLASSIFICADA",
    "DESCLASSIFICADA",
    "INABILITADA",
    "DESISTENTE",
]
SCOPE_OPTIONS = [
    "OBRA",
    "MANUTENÇÃO",
    "REFORMA",
    "TERCEIRIZAÇÃO",
    "ATA",
    "CONSÓRCIO",
    "OUTRO",
]

# Modalidades de contratação do PNCP (tabela de domínio do Manual de Integração).
PNCP_MODALIDADES = {
    1: "Leilão - Eletrônico",
    2: "Diálogo Competitivo",
    3: "Concurso",
    4: "Concorrência - Eletrônica",
    5: "Concorrência - Presencial",
    6: "Pregão - Eletrônico",
    7: "Pregão - Presencial",
    8: "Dispensa de Licitação",
    9: "Inexigibilidade",
    10: "Manifestação de Interesse",
    11: "Pré-qualificação",
    12: "Credenciamento",
    13: "Leilão - Presencial",
}


class PncpError(RuntimeError):
    """Erro de comunicação ou de resposta inesperada da API do PNCP."""


def bid_process_structure_label(lots):
    """Descreve resumidamente a estrutura de grupos/itens cadastrados para
    um processo, sem detalhar cada um — só uma noção geral no resumo (ex.:
    "3 grupo(s) · 20 itens no total", "5 item(ns) avulso(s)")."""
    if not lots:
        return "Individual (item único)"
    groups = [lot for lot in lots if (lot.get("lot_type") or "ITEM") == "GRUPO"]
    standalone_items = [lot for lot in lots if (lot.get("lot_type") or "ITEM") != "GRUPO"]
    total_sub_items = sum(int(lot.get("item_count") or 0) for lot in lots)
    parts = []
    if groups:
        parts.append(f"{len(groups)} grupo(s)")
    if standalone_items:
        parts.append(f"{len(standalone_items)} item(ns) avulso(s)")
    label = " + ".join(parts) if parts else f"{len(lots)} grupo(s)/item(ns)"
    if total_sub_items:
        label += f" · {total_sub_items} itens no total"
    return label


def bid_process_aggregate_values(process, lots):
    """Quando a licitação usa Grupos/Itens, o valor estimado (e o nosso
    lance/desconto) deixam de viver só no processo — cada grupo/item tem
    o seu próprio. Esta função soma tudo automaticamente para dar a visão
    geral do certame inteiro (usada no Resumo, na listagem geral, no PDF
    e no e-mail diário de licitações do dia), sem afetar o detalhamento
    por grupo/item, que continua intacto na aba própria. Se a licitação
    não usa Grupos/Itens, devolve os valores do próprio processo, sem
    alteração de comportamento. Quando a licitação é sigilosa, o desconto
    nunca é exibido — o valor cadastrado é só uma referência interna, não
    uma comparação oficial válida."""
    is_confidential = bool(process.get("is_confidential"))
    if not lots:
        return {
            "estimated_value": process.get("estimated_value"),
            "our_bid_value": process.get("our_bid_value"),
            "our_discount_percent": None if is_confidential else process.get("our_discount_percent"),
            "structure_label": "Individual (item único)",
            "is_confidential": is_confidential,
        }
    total_estimated = sum(float(lot.get("estimated_value") or 0) for lot in lots)
    lots_with_offer = [lot for lot in lots if lot.get("our_bid_value") is not None]
    total_offered = (
        sum(float(lot["our_bid_value"] or 0) for lot in lots_with_offer)
        if lots_with_offer else None
    )
    discount = None
    if total_offered and total_estimated and not is_confidential:
        discount = (1 - total_offered / total_estimated) * 100
    return {
        "estimated_value": total_estimated,
        "our_bid_value": total_offered,
        "our_discount_percent": discount,
        "structure_label": bid_process_structure_label(lots),
        "is_confidential": is_confidential,
    }


def format_estimated_value_display(aggregate):
    """Mostra o valor estimado normalmente — ou, quando a licitação é
    sigilosa, sinaliza isso claramente ('🔒 Sigiloso') com o valor
    cadastrado logo abaixo, para não passar a falsa impressão de que é o
    valor oficial divulgado pelo órgão."""
    if aggregate.get("is_confidential"):
        registered_value = aggregate.get("estimated_value")
        if registered_value:
            return f"🔒 Sigiloso\n{brl(registered_value)} (cadastrado)"
        return "🔒 Sigiloso — sem valor de referência cadastrado"
    return brl(aggregate.get("estimated_value"))


def pncp_search_contratacoes(
    data_inicial: date,
    data_final: date,
    codigo_modalidade: int = 6,
    uf: str | None = None,
    codigo_municipio_ibge: str | None = None,
    cnpj_orgao: str | None = None,
    pagina: int = 1,
) -> dict:
    """Consulta contratações publicadas no PNCP num período.

    Espelha o serviço "Consultar Contratações por Data de Publicação" do
    Manual de Integração PNCP (endpoint público, sem autenticação):
    GET {PNCP_BASE_URL}/contratacoes/publicacao

    Útil para localizar editais de um órgão/UF/modalidade específicos e
    conferir se já foram homologados, sem cadastrar tudo manualmente.
    Não traz o mapa de lances/classificação — apenas o edital e, quando
    concluído, o resultado publicado.
    """
    params = {
        "dataInicial": data_inicial.strftime("%Y%m%d"),
        "dataFinal": data_final.strftime("%Y%m%d"),
        "codigoModalidadeContratacao": codigo_modalidade,
        "pagina": pagina,
    }
    if uf:
        params["uf"] = uf
    if codigo_municipio_ibge:
        params["codigoMunicipioIbge"] = codigo_municipio_ibge
    if cnpj_orgao:
        params["cnpj"] = cnpj_orgao
    try:
        response = requests.get(
            f"{PNCP_BASE_URL}/contratacoes/publicacao",
            params=params,
            timeout=PNCP_TIMEOUT,
            headers={"Accept": "application/json"},
        )
    except requests.RequestException as error:
        raise PncpError(f"Falha de conexão com o PNCP: {error}") from error
    if response.status_code == 204:
        return {"total": 0, "paginas": 0, "itens": []}
    if not response.ok:
        raise PncpError(
            f"PNCP respondeu {response.status_code}: {response.text[:300]}"
        )
    payload = response.json()
    return {
        "total": payload.get("totalRegistros", 0),
        "paginas": payload.get("totalPaginas", 0),
        "itens": payload.get("data", payload if isinstance(payload, list) else []),
    }


def pncp_check_awarded_contracts(
    cnpj_orgao: str,
    data_inicial: date,
    data_final: date,
    cnpj_fornecedor: str = COMPANY_CNPJ,
    pagina: int = 1,
) -> list[dict]:
    """Verifica, entre os contratos publicados por UM órgão específico, quais
    foram firmados com o CNPJ do fornecedor informado (por padrão, a ENGEMIL).

    Limitação real da API pública do PNCP, confirmada no Manual de Integração
    oficial: não existe busca por CNPJ do fornecedor/participante — apenas
    por CNPJ do órgão comprador. Por isso esta função exige que o CNPJ do
    órgão já seja conhecido (preenchido na licitação cadastrada) e serve
    para CONFIRMAR o resultado de um processo já homologado, não para
    descobrir novas participações nem disputas em andamento.

    Espelha o serviço "Consultar Contratos por Data de Publicação" do
    Manual de Integração PNCP: GET {PNCP_BASE_URL}/contratos
    """
    cnpj_orgao_digits = re.sub(r"\D", "", cnpj_orgao or "")
    cnpj_fornecedor_digits = re.sub(r"\D", "", cnpj_fornecedor or "")
    if not cnpj_orgao_digits:
        raise PncpError("Informe o CNPJ do órgão para verificar a homologação.")
    params = {
        "dataInicial": data_inicial.strftime("%Y%m%d"),
        "dataFinal": data_final.strftime("%Y%m%d"),
        "cnpjOrgao": cnpj_orgao_digits,
        "pagina": pagina,
    }
    try:
        response = requests.get(
            f"{PNCP_BASE_URL}/contratos",
            params=params,
            timeout=PNCP_TIMEOUT,
            headers={"Accept": "application/json"},
        )
    except requests.RequestException as error:
        raise PncpError(f"Falha de conexão com o PNCP: {error}") from error
    if response.status_code == 204:
        return []
    if not response.ok:
        raise PncpError(
            f"PNCP respondeu {response.status_code}: {response.text[:300]}"
        )
    payload = response.json()
    items = payload.get("data", payload if isinstance(payload, list) else [])
    return [
        item for item in items
        if re.sub(r"\D", "", str(item.get("niFornecedor") or "")) == cnpj_fornecedor_digits
    ]



    """Ponto de extensão para a API do Portal de Compras Públicas.

    Ainda não é chamado pela interface porque a ENGEMIL precisa primeiro
    solicitar a chave de integração (Biblioteca de Dados) junto à
    plataforma. Assim que a chave existir, defina a variável de ambiente
    GESTAO_PCP_API_KEY (mesmo padrão usado para outras credenciais do
    sistema, como o e-mail) e implemente a chamada real aqui.
    """
    api_key = os.getenv("GESTAO_PCP_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Integração com o Portal de Compras Públicas ainda não configurada. "
            "Solicite a chave de integração (Biblioteca de Dados) na própria "
            "plataforma e defina GESTAO_PCP_API_KEY antes de usar esta função."
        )
    raise NotImplementedError(
        "Endpoint da Biblioteca de Dados do Portal de Compras Públicas ainda não "
        "implementado — implemente aqui assim que a documentação da chave "
        "recebida detalhar o formato de requisição/resposta."
    )


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        FONT_DIR / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
             else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            try:
                return ImageFont.truetype(str(candidate), size)
            except OSError:
                continue
    return ImageFont.load_default()


def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def generate_ranking_image(process: dict, rankings: list[dict], logo_path=None) -> bytes:
    """Gera a imagem PNG de classificação no padrão visual ENGEMIL.

    Reproduz a estrutura do relatório de classificação exportado das
    plataformas de pregão (título do processo, valor estimado, objeto,
    tabela SEQ/EMPRESA/LANCE FINAL/DESCONTO), com a linha da ENGEMIL
    destacada, pronta para encaminhar aos gestores.
    """
    width = 1200
    padding = 36
    has_cnpj = any(row.get("company_cnpj") for row in rankings)
    has_technical_score = any(row.get("technical_score") is not None for row in rankings)
    needs_tall_row = has_cnpj or has_technical_score
    is_confidential = bool(process.get("is_confidential"))
    row_height = 54 if needs_tall_row else 40
    header_height = 44
    rows = sorted(rankings, key=lambda item: item.get("seq") or 0)

    font_title = _load_font(22, bold=True)
    font_subtitle = _load_font(14)
    font_header = _load_font(14, bold=True)
    font_cell = _load_font(14)
    font_cell_bold = _load_font(14, bold=True)
    font_footer = _load_font(11)
    note_font = _load_font(12, bold=True)

    # Medição prévia — a imagem final só é criada depois de sabermos
    # exatamente quantas linhas o objeto precisa. Antes, a altura da
    # imagem era fixa e o texto do objeto era cortado em 3 linhas, mesmo
    # quando o objeto real precisava de mais — objetos longos ficavam
    # incompletos. Agora a imagem cresce conforme necessário (até um
    # limite generoso de 6 linhas, com reticências só além disso).
    measuring_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))

    acronym = extract_agency_acronym(process.get("agency") or "") or (process.get("agency") or "")
    identification_parts = [part for part in [
        acronym,
        process.get("edital_number") or process.get("process_number"),
        f"UASG {process['uasg']}" if process.get("uasg") else None,
    ] if part]
    value_part = "Valor estimado: SIGILOSO" if is_confidential else f"Estimado: {brl(process.get('estimated_value'))}"
    title = f"{' · '.join(identification_parts) or 'PROCESSO NÃO INFORMADO'} · {value_part}"
    title_w = _text_width(measuring_draw, title, font_title)
    if title_w > width - padding * 2 - 40:
        # Título longo: reduz a fonte proporcionalmente para caber numa linha.
        font_title = _load_font(int(22 * (width - padding * 2 - 40) / title_w), bold=True)
        title_w = _text_width(measuring_draw, title, font_title)

    subtitle = process.get("object") or ""
    max_subtitle_width = width - padding * 2
    words = subtitle.split()
    subtitle_lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if _text_width(measuring_draw, candidate, font_subtitle) > max_subtitle_width and current:
            subtitle_lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        subtitle_lines.append(current)
    max_subtitle_lines = 6
    if len(subtitle_lines) > max_subtitle_lines:
        subtitle_lines = subtitle_lines[:max_subtitle_lines]
        last = subtitle_lines[-1]
        while _text_width(measuring_draw, last + "…", font_subtitle) > max_subtitle_width and len(last) > 1:
            last = last[:-1]
        subtitle_lines[-1] = last + "…"

    agency = process.get("agency") or ""

    note_text = ""
    if is_confidential:
        note_parts = ["SIGILOSO — valor estimado ainda não divulgado pelo órgão até o momento"]
        if process.get("estimated_value"):
            note_parts.append(f"referência interna: {brl(process['estimated_value'])} (não oficial)")
        note_text = "  ·  ".join(note_parts)

    title_block_height = 44 + len(subtitle_lines) * 20 + (22 if agency else 0) + (24 if note_text else 0) + 14
    height = title_block_height + header_height + row_height * max(len(rows), 1) + padding * 2 + 60

    image = Image.new("RGB", (width, height), WHITE)
    draw = ImageDraw.Draw(image)

    cursor_y = padding
    logo_bottom = cursor_y
    if logo_path and Path(logo_path).exists():
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((150, 60))
            image.paste(logo, (padding, cursor_y), logo)
            logo_bottom = cursor_y + logo.height
        except Exception:
            pass

    draw.text(((width - title_w) / 2, cursor_y + 4), title, font=font_title, fill=BURGUNDY)
    cursor_y += 34
    cursor_y = max(cursor_y, logo_bottom + 10)

    for line in subtitle_lines:
        line_w = _text_width(draw, line, font_subtitle)
        draw.text(((width - line_w) / 2, cursor_y), line, font=font_subtitle, fill=TEXT_DARK)
        cursor_y += 20

    if agency:
        agency_w = _text_width(draw, agency, font_subtitle)
        draw.text(((width - agency_w) / 2, cursor_y), agency, font=font_subtitle, fill=(107, 114, 128))
        cursor_y += 22

    if note_text:
        note_w = _text_width(draw, note_text, note_font)
        draw.text(((width - note_w) / 2, cursor_y), note_text, font=note_font, fill=ABOVE_ESTIMATE_TEXT)
        cursor_y += 24

    cursor_y += 10
    columns = [
        ("SEQ", 70, "left"),
        ("EMPRESAS", width - padding * 2 - 70 - 220 - 150, "left"),
        ("LANCE FINAL", 220, "right"),
        ("DESCONTO", 150, "right"),
    ]
    header_top = cursor_y
    x = padding
    draw.rectangle([padding, header_top, width - padding, header_top + header_height], fill=BURGUNDY)
    for label, col_width, align in columns:
        text_w = _text_width(draw, label, font_header)
        text_x = x + 12 if align == "left" else x + col_width - text_w - 12
        draw.text((text_x, header_top + 12), label, font=font_header, fill=WHITE)
        x += col_width
    cursor_y = header_top + header_height

    font_cnpj = _load_font(11)

    for index, row in enumerate(rows):
        is_engemil = bool(row.get("is_engemil"))
        situation = str(row.get("situation") or "CLASSIFICADA").upper()
        is_out = situation not in ("CLASSIFICADA", "")
        row_top = cursor_y
        row_bottom = row_top + row_height
        if is_engemil:
            fill = BURGUNDY_LIGHT
        elif index % 2 == 0:
            fill = WHITE
        else:
            fill = ROW_ALT
        draw.rectangle([padding, row_top, width - padding, row_bottom], fill=fill)
        draw.line([padding, row_bottom, width - padding, row_bottom], fill=(225, 227, 231), width=1)

        cell_font = font_cell_bold if is_engemil else font_cell
        text_color = (150, 150, 150) if is_out else (BURGUNDY if is_engemil else TEXT_DARK)
        discount = row.get("discount_percent")
        is_above_estimate = discount is not None and discount < 0
        if is_out:
            discount_color = (150, 150, 150)
        elif is_above_estimate:
            discount_color = ABOVE_ESTIMATE_TEXT
        elif (discount or 0) > 0:
            discount_color = RED_TEXT
        else:
            discount_color = TEXT_DARK
        text_top = row_top + (10 if not needs_tall_row else 7)

        x = padding
        seq_text = str(row.get("seq") or index + 1)
        draw.text((x + 12, text_top), seq_text, font=cell_font, fill=text_color)
        x += columns[0][1]

        company = str(row.get("company_name") or "").upper()
        if is_out:
            company = f"{company} — {situation}"
        draw.text((x + 12, text_top), company, font=cell_font, fill=text_color)
        if is_out:
            company_w = _text_width(draw, company, cell_font)
            strike_y = text_top + 9
            draw.line([x + 12, strike_y, x + 12 + company_w, strike_y], fill=text_color, width=1)
        if row.get("company_cnpj"):
            cnpj_digits = re.sub(r"\D", "", str(row["company_cnpj"]))
            cnpj_fmt = (
                f"{cnpj_digits[0:2]}.{cnpj_digits[2:5]}.{cnpj_digits[5:8]}/"
                f"{cnpj_digits[8:12]}-{cnpj_digits[12:14]}"
                if len(cnpj_digits) == 14 else str(row["company_cnpj"])
            )
            draw.text((x + 12, text_top + 20), cnpj_fmt, font=font_cnpj, fill=(130, 130, 130))
        x += columns[1][1]

        bid_text = brl(row.get("final_bid_value")) if row.get("final_bid_value") is not None else "—"
        bid_w = _text_width(draw, bid_text, cell_font)
        draw.text((x + columns[2][1] - bid_w - 12, text_top), bid_text, font=cell_font, fill=text_color)
        x += columns[2][1]

        if discount is None:
            discount_text = "—"
        elif is_above_estimate:
            discount_text = f"▲ {abs(discount):.2f}".replace(".", ",") + "%"
        else:
            discount_text = f"{discount:.2f}".replace(".", ",") + "%"
        discount_w = _text_width(draw, discount_text, cell_font)
        draw.text(
            (x + columns[3][1] - discount_w - 12, text_top),
            discount_text, font=cell_font, fill=discount_color,
        )
        technical_score = row.get("technical_score")
        if technical_score is not None:
            technical_text = f"Nota técnica: {technical_score:.2f}".replace(".", ",")
            technical_w = _text_width(draw, technical_text, font_cnpj)
            draw.text(
                (x + columns[3][1] - technical_w - 12, text_top + 20),
                technical_text, font=font_cnpj, fill=(130, 130, 130),
            )
        cursor_y = row_bottom

    cursor_y += 24
    footer = (
        f"Gerado pelo Sistema de Gestão Contratual ENGEMIL em "
        f"{today_brt().strftime('%d/%m/%Y')} · uso interno, para acompanhamento gerencial."
    )
    draw.text((padding, cursor_y), footer, font=font_footer, fill=(120, 120, 120))

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
