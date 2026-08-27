from __future__ import annotations

import math
import re
from datetime import date, datetime


_DASH_ACRONYM_PATTERN = re.compile(
    r"\s[-–—]\s*(?P<suffix>[A-Z0-9][A-Z0-9./_-]*(?:\s*/\s*[^-–—]+)?)\s*$",
    re.IGNORECASE,
)
_PARENTHESIS_ACRONYM_PATTERN = re.compile(
    r"\((?P<acronym>[A-Z0-9][A-Z0-9./_-]{1,20})\)\s*$",
    re.IGNORECASE,
)


def parse_brazilian_number(value, default: float | None = None) -> float:
    """Converte números técnicos ou monetários brasileiros sem zerar silenciosamente."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        if default is None:
            raise ValueError("Valor numérico não informado.")
        return float(default)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        if default is None:
            raise ValueError("Valor numérico não informado.")
        return float(default)
    text = re.sub(r"[Rr]\$\s*", "", text)
    text = re.sub(r"\s+", "", text)
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    text = re.sub(r"[^0-9+\-.]", "", text)
    try:
        return float(text)
    except ValueError as error:
        if default is not None:
            return float(default)
        raise ValueError(f"Valor numérico inválido: {value}") from error


def _as_date(value) -> date | None:
    if value in (None, ""):
        return None
    if str(value).strip() in {"NaT", "nan", "None"}:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def contract_duration_months(start_value, end_value) -> int | None:
    """Retorna os meses completos de vigência entre duas datas."""
    start = _as_date(start_value)
    end = _as_date(end_value)
    if not start or not end or end < start:
        return None
    months = (end.year - start.year) * 12 + end.month - start.month
    if end.day < start.day:
        months -= 1
    return max(0, months)


def humanize_remaining(end_value, today_value=None) -> str:
    """Resume o tempo até o fim da vigência em linguagem adequada ao backlog."""
    end = _as_date(end_value)
    today = _as_date(today_value) or date.today()
    if not end:
        return "Prazo não informado"
    difference = (end - today).days
    if difference == 0:
        return "Encerra hoje"
    expired = difference < 0
    days = abs(difference)
    if days < 30:
        text = f"{days} dia{'s' if days != 1 else ''}"
    elif days < 365:
        months, remaining_days = divmod(days, 30)
        parts = [f"{months} mês{'es' if months != 1 else ''}"]
        if remaining_days:
            parts.append(
                f"{remaining_days} dia{'s' if remaining_days != 1 else ''}"
            )
        text = " e ".join(parts)
    else:
        years, remainder = divmod(days, 365)
        months, remaining_days = divmod(remainder, 30)
        parts = [f"{years} ano{'s' if years != 1 else ''}"]
        if months:
            parts.append(f"{months} mês{'es' if months != 1 else ''}")
        if remaining_days:
            parts.append(
                f"{remaining_days} dia{'s' if remaining_days != 1 else ''}"
            )
        text = ", ".join(parts[:-1]) + (
            f" e {parts[-1]}" if len(parts) > 1 else parts[0]
        )
    return f"Encerrado há {text}" if expired else f"Falta {text}"


def format_cnpj(value) -> str:
    """Formata um CNPJ (só dígitos, com ou sem máscara) no padrão
    XX.XXX.XXX/XXXX-XX. Devolve o valor original se não tiver 14 dígitos
    (ex.: CNPJ incompleto sendo digitado, ou vazio)."""
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) != 14:
        return str(value or "")
    return f"{digits[0:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:14]}"


def extract_agency_acronym(client_name: str) -> str:
    """Extrai uma sigla explicitamente informada no final do contratante."""
    text = re.sub(r"\s+", " ", str(client_name or "")).strip()
    match = _DASH_ACRONYM_PATTERN.search(text)
    if match:
        suffix = match.group("suffix")
        token = re.split(r"\s+/\s+|\s+/\s*|\s*/\s+", suffix, maxsplit=1)[0]
        token = token.strip(" .-/")
        if 2 <= len(token) <= 20 and re.search(r"[A-Za-z]", token):
            return token.upper()
    match = _PARENTHESIS_ACRONYM_PATTERN.search(text)
    if match:
        return match.group("acronym").strip(" .-/").upper()
    return ""


def split_agency_name(client_name: str) -> tuple[str, str, str]:
    """Separa nome, sigla e eventual complemento sem inventar abreviações."""
    text = re.sub(r"\s+", " ", str(client_name or "")).strip()
    acronym = extract_agency_acronym(text)
    if not acronym:
        return text, "", ""
    match = _DASH_ACRONYM_PATTERN.search(text)
    if match:
        suffix = match.group("suffix").strip()
        parts = re.split(r"\s+/\s+|\s+/\s*|\s*/\s+", suffix, maxsplit=1)
        qualifier = parts[1].strip() if len(parts) > 1 else ""
        return text[: match.start()].strip(), acronym, qualifier
    match = _PARENTHESIS_ACRONYM_PATTERN.search(text)
    return (text[: match.start()].strip(), acronym, "") if match else (text, acronym, "")


def normalize_agency_name(client_name: str) -> str:
    """Normaliza espaços e remove siglas finais repetidas, preservando o texto do usuário."""
    text = re.sub(r"\s+", " ", str(client_name or "")).strip()
    while True:
        match = re.search(
            r"(?i)(\s[-–—]\s*([A-Z0-9][A-Z0-9./_-]{1,20}))"
            r"\s[-–—]\s*\2\s*$",
            text,
        )
        if not match:
            break
        text = text[: match.end(1)].strip()
    return text


def agency_document_fields(client_name: str) -> tuple[str, str]:
    """Retorna ORGAO e SIGLA para modelos que já possuem o separador entre campos."""
    normalized = normalize_agency_name(client_name)
    name, acronym, qualifier = split_agency_name(normalized)
    if not acronym:
        return normalized, ""
    display_acronym = f"{acronym} / {qualifier}" if qualifier else acronym
    return name, display_acronym
