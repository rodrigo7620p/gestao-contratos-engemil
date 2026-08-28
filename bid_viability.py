from __future__ import annotations

"""Busca automática dos documentos do edital no PNCP, para apoiar a
análise de viabilidade de uma licitação.

A partir do Número de controle PNCP já cadastrado na licitação, baixa os
documentos publicados no PNCP (API pública, sem chave — mesmo padrão de
bids.py) e devolve tudo compactado num único .zip, pronto para anexar a um
pedido de análise (ex.: pedir a análise diretamente ao Claude no chat,
informando a licitação) — sem nenhum custo de API envolvido.

Importante: o PNCP só publica o edital e seus anexos — o mapa de lances
por empresa é dado da plataforma do pregão (ComprasNet, Portal de Compras
Públicas etc.), não do PNCP. Isso continua vindo do que já está cadastrado
manualmente na aba Classificação da licitação (bid_rankings)."""

import io
import re
import zipfile
from pathlib import Path

import requests

PNCP_ORGAOS_BASE_URL = "https://pncp.gov.br/api/pncp/v1/orgaos"
PNCP_TIMEOUT = 30

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
    PDF (ex.: planilha-modelo de proposta em .xlsx) são ignorados."""
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
            "(ou o arquivo compactado não continha PDFs) — não há o que baixar."
        )
    return pdfs


def build_pncp_documents_zip(pncp_control_number: str) -> tuple[bytes, list[str]]:
    """Baixa os PDFs do edital no PNCP e devolve tudo compactado num único
    .zip, pronto para download — sem nenhuma chamada paga envolvida."""
    pdfs = download_pncp_pdfs(pncp_control_number)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename, content in pdfs:
            archive.writestr(filename, content)
    return buffer.getvalue(), [name for name, _ in pdfs]
