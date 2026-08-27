from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree

from contract_utils import extract_agency_acronym

BASE_DIR = Path(__file__).resolve().parent
WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"
NS = {"w": WORD_NAMESPACE}
TOKEN_PATTERN = re.compile(r"\{\{[A-Z0-9_ÁÉÍÓÚÂÊÔÃÕÇ]+\}\}", re.IGNORECASE)


def resolve_project_path(path_value: str | Path) -> Path:
    raw = str(path_value or "").strip()
    path = Path(raw)
    if path.exists():
        return path
    normalized = Path(raw.replace("\\", "/"))
    if not normalized.is_absolute():
        candidate = BASE_DIR / normalized
        if candidate.exists():
            return candidate
    for marker in ("uploads", "templates", "assets"):
        if marker in normalized.parts:
            candidate = BASE_DIR.joinpath(
                *normalized.parts[normalized.parts.index(marker):]
            )
            if candidate.exists():
                return candidate
    return path if path.is_absolute() else BASE_DIR / path


def safe_filename(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", str(value or "").strip())
    cleaned = re.sub(r"\s+", "_", cleaned).strip("._-")
    return cleaned[:150] or "documento"


def date_in_words(value: date | None = None) -> str:
    value = value or date.today()
    months = (
        "janeiro", "fevereiro", "março", "abril", "maio", "junho",
        "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
    )
    return f"Brasília/DF, {value.day:02d} de {months[value.month - 1]} de {value.year}"


def format_document_number(
    document_type: str,
    sequence: int,
    contract_number: str = "",
    agency_acronym: str = "",
    year: int | None = None,
) -> str:
    year = year or date.today().year
    document_type = str(document_type or "DIVERSO").upper()
    prefix = {
        "OFICIO": "OF",
        "CARTA_PREPOSTO": "CA",
        "PROCURACAO": "PR",
        "DIVERSO": "DOC",
    }.get(document_type, "DOC")
    base = f"{prefix}-{year}-{sequence:04d}/ENGEMIL/DCONT"
    if document_type == "PROCURACAO":
        return f"{base}/ATIV.ADM"
    normalized_acronym = extract_agency_acronym(
        f"Órgão - {agency_acronym}"
    ) if agency_acronym else ""
    suffix = "/".join(
        part.strip(" /")
        for part in (contract_number, normalized_acronym)
        if str(part or "").strip(" /")
    )
    return f"{base}/{suffix}" if suffix else base


def _set_preserve_space(text_node):
    text = text_node.text or ""
    if text.startswith(" ") or text.endswith(" ") or "  " in text:
        text_node.set(f"{{{XML_NAMESPACE}}}space", "preserve")


def _replace_token_in_nodes(text_nodes, token: str, replacement: str) -> bool:
    replaced = False
    paragraph = text_nodes[0]
    while paragraph is not None and paragraph.tag != f"{{{WORD_NAMESPACE}}}p":
        paragraph = paragraph.getparent()
    while True:
        combined = "".join(node.text or "" for node in text_nodes)
        start = combined.rfind(token)
        if start < 0:
            break
        end = start + len(token)
        offsets = []
        cursor = 0
        for node in text_nodes:
            node_text = node.text or ""
            offsets.append((cursor, cursor + len(node_text)))
            cursor += len(node_text)
        first_index = next(
            index for index, (_, node_end) in enumerate(offsets) if node_end > start
        )
        last_index = next(
            index for index, (node_start, node_end) in enumerate(offsets)
            if node_start < end <= node_end
        )
        first = text_nodes[first_index]
        last = text_nodes[last_index]
        first_start, _ = offsets[first_index]
        last_start, _ = offsets[last_index]
        prefix = (first.text or "")[: start - first_start]
        suffix = (last.text or "")[end - last_start :]
        for index in range(first_index, last_index + 1):
            text_nodes[index].text = ""
        lines = str(replacement or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
        first.text = prefix + lines[0]
        _set_preserve_space(first)
        destination = first
        if len(lines) > 1:
            run = first.getparent()
            insert_at = run.index(first) + 1
            for line in lines[1:]:
                line_break = etree.Element(f"{{{WORD_NAMESPACE}}}br")
                run.insert(insert_at, line_break)
                insert_at += 1
                new_text = etree.Element(f"{{{WORD_NAMESPACE}}}t")
                new_text.text = line
                _set_preserve_space(new_text)
                run.insert(insert_at, new_text)
                insert_at += 1
                destination = new_text
        destination.text = (destination.text or "") + suffix
        _set_preserve_space(destination)
        replaced = True
        text_nodes = paragraph.xpath(".//w:t", namespaces=NS) if paragraph is not None else text_nodes
    return replaced


def _replace_xml(data: bytes, replacements: dict[str, str]) -> bytes:
    parser = etree.XMLParser(remove_blank_text=False, recover=True)
    root = etree.fromstring(data, parser)
    for paragraph in root.xpath("//w:p", namespaces=NS):
        for token, value in replacements.items():
            nodes = paragraph.xpath(".//w:t", namespaces=NS)
            if nodes:
                _replace_token_in_nodes(nodes, token, str(value or ""))
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _force_a4_portrait_xml(data: bytes) -> bytes:
    """Mantém todos os documentos gerados no padrão institucional A4 vertical."""
    parser = etree.XMLParser(remove_blank_text=False, recover=True)
    root = etree.fromstring(data, parser)
    for section_properties in root.xpath("//w:sectPr", namespaces=NS):
        page_size = section_properties.find(f"{{{WORD_NAMESPACE}}}pgSz")
        if page_size is None:
            page_size = etree.Element(f"{{{WORD_NAMESPACE}}}pgSz")
            section_properties.insert(0, page_size)
        page_size.set(f"{{{WORD_NAMESPACE}}}w", "11906")
        page_size.set(f"{{{WORD_NAMESPACE}}}h", "16838")
        page_size.attrib.pop(f"{{{WORD_NAMESPACE}}}orient", None)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def extract_placeholders(template_path: str | Path) -> list[str]:
    template_path = resolve_project_path(template_path)
    tokens = set()
    with ZipFile(template_path) as package:
        for name in package.namelist():
            if not (name.startswith("word/") and name.endswith(".xml")):
                continue
            try:
                root = etree.fromstring(package.read(name))
            except etree.XMLSyntaxError:
                continue
            for paragraph in root.xpath("//w:p", namespaces=NS):
                text = "".join(paragraph.xpath(".//w:t/text()", namespaces=NS))
                tokens.update(TOKEN_PATTERN.findall(text))
    return sorted(tokens)


def generate_document(
    template_path: str | Path,
    output_path: str | Path,
    replacements: dict[str, str],
) -> Path:
    template_path = resolve_project_path(template_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    normalized = {
        token if token.startswith("{{") else f"{{{{{token}}}}}": str(value or "")
        for token, value in replacements.items()
    }
    with ZipFile(template_path) as source, ZipFile(output_path, "w", ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename.startswith("word/") and item.filename.endswith(".xml"):
                data = _replace_xml(data, normalized)
                if item.filename == "word/document.xml":
                    data = _force_a4_portrait_xml(data)
            target.writestr(item, data)
    return output_path


def _soffice_path() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


def convert_template_to_docx(source_path: str | Path, output_path: str | Path) -> Path:
    source_path = Path(source_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if source_path.suffix.lower() == ".docx":
        shutil.copy2(source_path, output_path)
        return output_path
    soffice = _soffice_path()
    if not soffice:
        raise RuntimeError(
            "O LibreOffice não foi localizado. Ele é necessário para converter modelos DOTM em DOCX."
        )
    with tempfile.TemporaryDirectory() as temporary:
        temporary_path = Path(temporary)
        profile = temporary_path / "profile"
        command = [
            soffice,
            f"-env:UserInstallation={profile.as_uri()}",
            "--headless",
            "--convert-to",
            "docx",
            "--outdir",
            str(temporary_path),
            str(source_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
        converted = temporary_path / f"{source_path.stem}.docx"
        if result.returncode != 0 or not converted.exists():
            message = result.stderr.strip() or result.stdout.strip() or "Falha na conversão do modelo."
            raise RuntimeError(message)
        shutil.copy2(converted, output_path)
    return output_path
