from __future__ import annotations

import re
import unicodedata
from datetime import date


BACKLOG_SORT_OPTIONS = {
    "Contratante - ordem alfabética": "client_asc",
    "Centro de custo - ordem crescente": "cost_center_asc",
    "Valor atual - maior para menor": "current_value_desc",
    "Remanescente total - maior para menor": "remaining_desc",
    "Fim da vigência - mais próximo primeiro": "end_date_asc",
    "Instrumento vigente - ordem alfabética": "instrument_asc",
}


def _text_key(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(character for character in text if not unicodedata.combining(character)).casefold()


def _cost_center_key(value):
    parts = re.split(r"(\d+)", str(value or ""))
    return tuple(
        (0, int(part)) if part.isdigit() else (1, _text_key(part))
        for part in parts
        if part != ""
    )


def _date_key(value):
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return date.max


def sort_backlog_rows(rows, criterion):
    """Ordena o Backlog oficial e renumera a coluna Item."""
    records = [dict(row) for row in rows]
    sorters = {
        "client_asc": (
            lambda row: (
                _text_key(row.get("Contratante")),
                _cost_center_key(row.get("Centro de custo")),
            ),
            False,
        ),
        "cost_center_asc": (
            lambda row: (
                _cost_center_key(row.get("Centro de custo")),
                _text_key(row.get("Contratante")),
            ),
            False,
        ),
        "current_value_desc": (
            lambda row: float(row.get("Valor atual") or 0),
            True,
        ),
        "remaining_desc": (
            lambda row: float(row.get("Remanescente total") or 0),
            True,
        ),
        "end_date_asc": (
            lambda row: (
                _date_key(row.get("Fim")),
                _text_key(row.get("Contratante")),
            ),
            False,
        ),
        "instrument_asc": (
            lambda row: (
                _text_key(row.get("Instrumento vigente")),
                _text_key(row.get("Contratante")),
            ),
            False,
        ),
    }
    key_function, reverse = sorters.get(criterion, sorters["client_asc"])
    ordered = sorted(records, key=key_function, reverse=reverse)
    for item, row in enumerate(ordered, start=1):
        row["Item"] = item
    return ordered
