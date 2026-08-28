from __future__ import annotations

"""Análise automática de viabilidade de licitações via IA (Claude/Anthropic).

Fluxo: a partir do Número de controle PNCP já cadastrado na licitação, busca
os documentos do edital publicados no PNCP (API pública, sem chave — mesmo
padrão de bids.py), envia-os para análise à API da Anthropic junto com os
dados já cadastrados no sistema (nossa proposta, classificação, grupos/
itens) e devolve uma Nota Técnica de Análise de Viabilidade estruturada,
formatada como documento Word com a identidade visual da ENGEMIL.

Importante: o PNCP só publica o edital e seus anexos — o mapa de lances por
empresa é dado da plataforma do pregão (ComprasNet, Portal de Compras
Públicas etc.), não do PNCP. Continua vindo do que já está cadastrado na
aba Classificação da licitação (bid_rankings); quando não há nada
cadastrado, a análise é instruída a declarar essa limitação em vez de
inventar concorrentes.

Tem custo real por análise gerada (API paga da Anthropic) — por isso nunca
é disparada sozinha; sempre por um clique explícito, com estimativa de
custo mostrada antes.
"""

import base64
import io
import os
import re
import zipfile
from pathlib import Path

import requests

from db import execute, query

PNCP_ORGAOS_BASE_URL = "https://pncp.gov.br/api/pncp/v1/orgaos"
PNCP_TIMEOUT = 30
ANALYSIS_MODEL = "claude-opus-5"
INPUT_PRICE_PER_MTOK = 5.0
OUTPUT_PRICE_PER_MTOK = 25.0
MAX_OUTPUT_TOKENS = 16000

_PNCP_CONTROL_RE = re.compile(r"^(\d{14})-\d+-(\d+)/(\d{4})$")


def parse_pncp_control_number(value):
    """Extrai (cnpj, ano, sequencial) de um nº de controle PNCP.

    Formato oficial: {cnpj:14}-{esfera}-{sequencial}/{ano}, ex.:
    "26989715000102-1-001161/2026"."""
    match = _PNCP_CONTROL_RE.match(str(value or "").strip())
    if not match:
        return None
    cnpj, sequencial, ano = match.groups()
    return cnpj, int(ano), int(sequencial)


def _secret(name: str) -> str | None:
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st
        return st.secrets.get(name)
    except Exception:
        return None


def anthropic_api_key_configured() -> bool:
    return bool(_secret("ANTHROPIC_API_KEY"))


def _anthropic_client():
    import anthropic
    api_key = _secret("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY não configurado. Peça ao administrador para "
            "cadastrar a chave da API da Anthropic (criada em "
            "console.anthropic.com) nas configurações do sistema."
        )
    return anthropic.Anthropic(api_key=api_key)


def fetch_pncp_document_list(cnpj: str, ano: int, sequencial: int) -> list[dict]:
    url = f"{PNCP_ORGAOS_BASE_URL}/{cnpj}/compras/{ano}/{sequencial}/arquivos"
    response = requests.get(url, headers={"Accept": "application/json"}, timeout=PNCP_TIMEOUT)
    if response.status_code == 204:
        return []
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, list) else []


def download_pncp_pdfs(pncp_control_number: str) -> list[tuple[str, bytes]]:
    """Baixa os anexos de uma licitação no PNCP e devolve só os PDFs.

    Alguns órgãos publicam os anexos compactados num único .zip; nesse
    caso, extrai apenas os arquivos .pdf de dentro. Arquivos que não são
    PDF (ex.: planilha-modelo de proposta em .xlsx) são ignorados — a
    análise só precisa dos documentos textuais do edital."""
    parsed = parse_pncp_control_number(pncp_control_number)
    if not parsed:
        raise ValueError(
            f"Número de controle PNCP em formato inesperado: {pncp_control_number!r}. "
            "Formato esperado: 00000000000000-1-000000/0000."
        )
    cnpj, ano, sequencial = parsed
    documents = fetch_pncp_document_list(cnpj, ano, sequencial)
    if not documents:
        raise RuntimeError("O PNCP não retornou nenhum documento anexado a esta licitação.")
    pdfs: list[tuple[str, bytes]] = []
    for doc in documents:
        file_url = doc.get("uri") or doc.get("url")
        title = str(doc.get("titulo") or f"documento_{doc.get('sequencialDocumento', '')}")
        if not file_url:
            continue
        response = requests.get(file_url, timeout=PNCP_TIMEOUT * 2)
        response.raise_for_status()
        content = response.content
        lower_title = title.lower()
        if lower_title.endswith(".zip") or content[:2] == b"PK":
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    for name in archive.namelist():
                        if name.lower().endswith(".pdf"):
                            pdfs.append((Path(name).name, archive.read(name)))
            except zipfile.BadZipFile:
                continue
        elif lower_title.endswith(".pdf") or content[:4] == b"%PDF":
            pdfs.append((title, content))
    if not pdfs:
        raise RuntimeError(
            "Os documentos do PNCP foram encontrados, mas nenhum é um PDF "
            "(ou o arquivo compactado não continha PDFs) — não há o que analisar."
        )
    return pdfs


def _context_text(bid_process: dict, lots: list[dict], rankings: list[dict]) -> str:
    def _fmt(value):
        try:
            return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except (TypeError, ValueError):
            return "não informado"

    lines = [
        f"Órgão: {bid_process.get('agency') or 'não informado'}",
        f"UASG: {bid_process.get('uasg') or 'não informado'}",
        f"Processo administrativo: {bid_process.get('process_number') or 'não informado'}",
        f"Edital nº: {bid_process.get('edital_number') or bid_process.get('process_number') or 'não informado'}",
        f"Modalidade: {bid_process.get('modality') or 'não informada'}",
        f"Escopo: {bid_process.get('scope') or 'não informado'}",
        f"Data/hora da disputa: {bid_process.get('dispute_date') or '—'} {bid_process.get('dispute_time') or ''}".strip(),
        f"Valor estimado cadastrado no sistema: {_fmt(bid_process.get('estimated_value'))}",
        f"Nosso lance cadastrado: {_fmt(bid_process.get('our_bid_value')) if bid_process.get('our_bid_value') is not None else 'ainda não cadastrado'}",
        f"Nosso desconto cadastrado: {bid_process.get('our_discount_percent')}%"
        if bid_process.get("our_discount_percent") is not None else "Nosso desconto: ainda não cadastrado",
        f"Nossa colocação/classificação cadastrada: {bid_process.get('our_ranking') or 'não informada'}",
        f"Sigilosa: {'sim' if bid_process.get('is_confidential') else 'não'}",
    ]
    if lots:
        lines.append("\nGrupos/Itens cadastrados no sistema:")
        for lot in lots:
            lines.append(
                f"- {lot.get('label')}: estimado {_fmt(lot.get('estimated_value'))}, "
                f"nosso lance {_fmt(lot.get('our_bid_value')) if lot.get('our_bid_value') is not None else '—'}"
            )
    if rankings:
        lines.append("\nMapa de lances/classificação já cadastrado no sistema (fonte: plataforma do pregão, inserido manualmente pela equipe):")
        for row in rankings:
            marker = " [ESTA É A ENGEMIL]" if row.get("is_engemil") else ""
            lines.append(
                f"- {row.get('seq')}º colocado: {row.get('company_name')} — "
                f"lance {_fmt(row.get('final_bid_value')) if row.get('final_bid_value') is not None else '—'}, "
                f"desconto {row.get('discount_percent')}%, situação {row.get('situation')}{marker}"
            )
    else:
        lines.append(
            "\nAVISO: ainda não há mapa de lances/classificação cadastrado no sistema para "
            "esta licitação. Se os documentos anexados não trouxerem essa informação por si "
            "só, NÃO invente nomes de empresas concorrentes nem valores de lance de "
            "terceiros — registre essa limitação explicitamente na análise."
        )
    return "\n".join(lines)


SYSTEM_PROMPT = (
    "Você é um analista sênior de viabilidade contratual da ENGEMIL Engenharia, "
    "Empreendimentos, Manutenção e Instalações Ltda., especializado em licitações "
    "públicas de manutenção predial, elétrica e afins. Sua tarefa é produzir uma Nota "
    "Técnica de Análise de Viabilidade de altíssimo nível profissional sobre uma "
    "licitação específica, com base nos documentos do edital fornecidos (PDF) e nos "
    "dados internos da ENGEMIL fornecidos no contexto.\n\n"
    "Diretrizes obrigatórias:\n"
    "- Leia e cite itens/cláusulas ESPECÍFICOS dos documentos anexados (ex.: \"item "
    "5.7.10 do edital\", \"cláusula 7.2 da minuta\") sempre que fundamentar uma "
    "afirmação — nunca generalize sem apontar a fonte.\n"
    "- Separe, quando aplicável, o desconto \"aparente\" do desconto \"real\", "
    "identificando valores do próprio edital que não são alteráveis pelo licitante "
    "(ex.: verbas de reembolsáveis fixas) e que distorcem a leitura simples do "
    "percentual de desconto global.\n"
    "- Calcule cenários de ponto de equilíbrio quando houver composição de custos "
    "(SINAPI ou própria) disponível nos anexos, considerando tributos e BDI.\n"
    "- Identifique riscos operacionais e de fluxo de caixa concretos (não genéricos), "
    "como prazos de ressarcimento, descasamento de caixa, penalidades de instrumento "
    "de medição de resultados, rigidez de repactuação, cobertura do parque de "
    "equipamentos etc., sempre que os documentos tragam essas informações.\n"
    "- NUNCA invente números, nomes de empresas concorrentes ou cláusulas que não "
    "estejam realmente presentes nos documentos fornecidos ou no contexto interno "
    "informado. Quando uma informação necessária não estiver disponível, diga isso "
    "explicitamente na seção relevante em vez de supor um valor.\n"
    "- Seja direto e decisório na recomendação final, mas sempre condicionado às "
    "ressalvas reais identificadas.\n"
    "- Escreva em português do Brasil, tom formal e técnico, como um documento "
    "interno de apoio à decisão da Diretoria."
)

REPORT_TOOL_NAME = "emitir_nota_tecnica_viabilidade"
REPORT_TOOL_SCHEMA = {
    "name": REPORT_TOOL_NAME,
    "description": (
        "Registra a nota técnica de análise de viabilidade estruturada em seções, "
        "para ser formatada como documento Word."
    ),
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "objeto", "valor_estimado_texto", "proposta_engemil_texto",
            "situacao_texto", "conclusao_executiva", "recomendacao",
        ],
        "properties": {
            "objeto": {"type": "string"},
            "valor_estimado_texto": {"type": "string"},
            "proposta_engemil_texto": {"type": "string"},
            "situacao_texto": {"type": "string"},
            "conclusao_executiva": {
                "type": "string",
                "description": "1 a 3 parágrafos, separados por \\n\\n",
            },
            "recomendacao": {"type": "string", "description": "1 parágrafo objetivo"},
            "analise_desconto": {
                "type": "object",
                "properties": {
                    "explicacao": {"type": "string"},
                    "colunas_tabela": {"type": "array", "items": {"type": "string"}},
                    "linhas_tabela": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "string"}},
                    },
                    "limites_controle": {"type": "array", "items": {"type": "string"}},
                },
            },
            "ponto_equilibrio": {
                "type": "object",
                "properties": {
                    "explicacao": {"type": "string"},
                    "colunas_tabela": {"type": "array", "items": {"type": "string"}},
                    "linhas_tabela": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "pontos_favoraveis": {"type": "array", "items": {"type": "string"}},
            "riscos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "titulo": {"type": "string"},
                        "texto": {"type": "string"},
                    },
                    "required": ["titulo", "texto"],
                },
            },
            "encaminhamentos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "titulo": {"type": "string"},
                        "texto": {"type": "string"},
                    },
                    "required": ["titulo", "texto"],
                },
            },
            "sintese_final": {"type": "string"},
        },
    },
}


def _build_message_content(bid_process, lots, rankings, pdf_documents):
    content = []
    for filename, pdf_bytes in pdf_documents:
        content.append({
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": base64.standard_b64encode(pdf_bytes).decode("ascii"),
            },
            "title": filename[:250],
        })
    context_text = _context_text(bid_process, lots, rankings)
    content.append({
        "type": "text",
        "text": (
            "Dados internos da ENGEMIL sobre esta licitação:\n\n" + context_text +
            "\n\nCom base nesses dados e nos documentos do edital anexados, produza a "
            f"nota técnica de análise de viabilidade, preenchendo a ferramenta "
            f"{REPORT_TOOL_NAME}."
        ),
    })
    return content


def estimate_analysis_cost(bid_process, lots, rankings, pdf_documents) -> dict:
    """Estimativa de custo ANTES de chamar a análise de verdade (barato: só conta tokens)."""
    client = _anthropic_client()
    content = _build_message_content(bid_process, lots, rankings, pdf_documents)
    count = client.messages.count_tokens(
        model=ANALYSIS_MODEL,
        system=SYSTEM_PROMPT,
        tools=[REPORT_TOOL_SCHEMA],
        messages=[{"role": "user", "content": content}],
    )
    input_tokens = count.input_tokens
    input_cost = input_tokens / 1_000_000 * INPUT_PRICE_PER_MTOK
    max_output_cost = MAX_OUTPUT_TOKENS / 1_000_000 * OUTPUT_PRICE_PER_MTOK
    return {
        "input_tokens": input_tokens,
        "min_cost_usd": round(input_cost, 2),
        "max_cost_usd": round(input_cost + max_output_cost, 2),
    }


def call_viability_analysis(bid_process, lots, rankings, pdf_documents):
    client = _anthropic_client()
    content = _build_message_content(bid_process, lots, rankings, pdf_documents)
    response = client.messages.create(
        model=ANALYSIS_MODEL,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=SYSTEM_PROMPT,
        output_config={"effort": "max"},
        tools=[REPORT_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": REPORT_TOOL_NAME},
        messages=[{"role": "user", "content": content}],
    )
    tool_use = next((block for block in response.content if block.type == "tool_use"), None)
    if not tool_use:
        raise RuntimeError("A IA não retornou a análise estruturada esperada.")
    return tool_use.input, response.usage


def latest_analysis(bid_process_id):
    rows = query(
        """SELECT * FROM bid_viability_analyses WHERE bid_process_id=?
        ORDER BY id DESC LIMIT 1""",
        (bid_process_id,),
    )
    return dict(rows[0]) if rows else None


def analysis_history(bid_process_id):
    return [
        dict(row) for row in query(
            """SELECT * FROM bid_viability_analyses WHERE bid_process_id=?
            ORDER BY id DESC""",
            (bid_process_id,),
        )
    ]


def generate_bid_viability_report(bid_process_id: int, requested_by=None) -> dict:
    """Orquestra o fluxo completo: busca no PNCP, chama a IA, gera o Word,
    salva tudo e devolve o registro da análise. Lança exceção em caso de
    falha em qualquer etapa (fica registrada na própria análise)."""
    from reports import generate_bid_viability_docx
    from db import UPLOAD_DIR

    bid_rows = query("SELECT * FROM bid_processes WHERE id=?", (bid_process_id,))
    if not bid_rows:
        raise ValueError("Licitação não encontrada.")
    bid_process = dict(bid_rows[0])
    pncp_number = str(bid_process.get("pncp_control_number") or "").strip()
    if not pncp_number:
        raise ValueError(
            "Esta licitação não tem Número de controle PNCP cadastrado — preencha "
            "esse campo na aba Resumo e edição antes de gerar a análise automática."
        )
    lots = [dict(row) for row in query(
        "SELECT * FROM bid_lots WHERE bid_process_id=? ORDER BY id", (bid_process_id,)
    )]
    rankings = [dict(row) for row in query(
        "SELECT * FROM bid_rankings WHERE bid_process_id=? ORDER BY seq", (bid_process_id,)
    )]

    analysis_id = execute(
        "INSERT INTO bid_viability_analyses(bid_process_id,status,requested_by) VALUES(?,?,?)",
        (bid_process_id, "PROCESSANDO", requested_by),
    )
    try:
        pdf_documents = download_pncp_pdfs(pncp_number)
        source_names = "; ".join(name for name, _ in pdf_documents)
        report_data, usage = call_viability_analysis(bid_process, lots, rankings, pdf_documents)
        input_tokens = int(usage.input_tokens)
        output_tokens = int(usage.output_tokens)
        cost = (
            input_tokens / 1_000_000 * INPUT_PRICE_PER_MTOK
            + output_tokens / 1_000_000 * OUTPUT_PRICE_PER_MTOK
        )
        docx_bytes = generate_bid_viability_docx(report_data, bid_process)
        safe_process = re.sub(r"[^A-Za-z0-9]+", "_", str(bid_process.get("process_number") or bid_process_id)).strip("_")
        docx_dir = UPLOAD_DIR / "bid_viability"
        docx_dir.mkdir(parents=True, exist_ok=True)
        docx_filename = f"nota_tecnica_viabilidade_{safe_process}_{analysis_id}.docx"
        docx_path = docx_dir / docx_filename
        docx_path.write_bytes(docx_bytes)
        import json
        execute(
            """UPDATE bid_viability_analyses SET status='CONCLUIDA',recommendation=?,
            report_json=?,docx_filename=?,docx_path=?,source_documents=?,
            input_tokens=?,output_tokens=?,estimated_cost_usd=?,completed_at=CURRENT_TIMESTAMP
            WHERE id=?""",
            (
                report_data.get("recomendacao"), json.dumps(report_data, ensure_ascii=False),
                docx_filename, str(docx_path), source_names,
                input_tokens, output_tokens, round(cost, 4), analysis_id,
            ),
        )
        return latest_analysis(bid_process_id)
    except Exception as error:
        execute(
            """UPDATE bid_viability_analyses SET status='ERRO',error_message=?,
            completed_at=CURRENT_TIMESTAMP WHERE id=?""",
            (str(error), analysis_id),
        )
        raise
