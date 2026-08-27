from __future__ import annotations

from datetime import date


def _valid_iso_date(value) -> bool:
    if not value:
        return False
    try:
        date.fromisoformat(str(value)[:10])
        return True
    except ValueError:
        return False


def contract_review_issues(contract) -> list[dict[str, str]]:
    """Identifica somente as pendências cadastrais que afetam o dashboard."""
    issues = []
    if not str(contract.get("manager_name") or "").strip():
        issues.append({
            "field": "manager_name",
            "label": "Responsável administrativo",
            "reason": "Não informado",
            "action": "Informe o responsável administrativo e seu e-mail na aba Editar.",
        })
    effective_end = contract.get("end_date") or contract.get("effective_end")
    if not _valid_iso_date(effective_end):
        issues.append({
            "field": "end_date",
            "label": "Prazo final vigente",
            "reason": "Não informado ou inválido",
            "action": "Revise a data final do contrato ou do último instrumento contratual.",
        })
    try:
        current_value = float(
            contract.get("current_value")
            if contract.get("current_value") is not None
            else contract.get("effective_value") or 0
        )
    except (TypeError, ValueError):
        current_value = 0
    if current_value <= 0:
        issues.append({
            "field": "current_value",
            "label": "Valor atual",
            "reason": "Não informado ou igual a zero",
            "action": "Informe o valor vigente do contrato ou do último instrumento.",
        })
    return issues
