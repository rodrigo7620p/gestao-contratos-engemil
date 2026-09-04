from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from contract_utils import today_brt


GUARANTEE_TYPES = (
    "GARANTIA CONTRATUAL",
    "GARANTIA ADICIONAL",
    "RISCOS DE ENGENHARIA",
    "RESPONSABILIDADE CIVIL DE OBRA",
    "RESPONSABILIDADE CIVIL PROFISSIONAL",
    "SEGURO DE VIDA / ACIDENTES PESSOAIS",
    "OUTRO",
)

GUARANTEE_MODALITIES = (
    "SEGURO-GARANTIA",
    "CAUÇÃO EM DINHEIRO OU TÍTULOS DA DÍVIDA PÚBLICA",
    "FIANÇA BANCÁRIA",
    "TÍTULO DE CAPITALIZAÇÃO",
    "APÓLICE DE RISCOS DE ENGENHARIA",
    "APÓLICE DE RESPONSABILIDADE CIVIL",
    "OUTRA",
)

REQUEST_STATUSES = (
    "A SOLICITAR",
    "SOLICITADA",
    "RECEBIDA",
    "EM ANÁLISE",
    "ACEITA",
    "PENDENTE DE CORREÇÃO",
    "DISPENSADA",
    "CANCELADA",
)

CALCULATION_METHODS = (
    "PERCENTUAL_BASE",
    "GARANTIA_ADICIONAL",
    "VALOR_INFORMADO",
)

CALCULATION_LABELS = {
    "PERCENTUAL_BASE": "Percentual sobre a base contratual",
    "GARANTIA_ADICIONAL": "Garantia adicional - orçamento menos proposta",
    "VALOR_INFORMADO": "Valor definido no instrumento",
}


def default_legal_basis(guarantee_type: str) -> str:
    normalized = str(guarantee_type or "").strip().upper()
    if normalized == "GARANTIA ADICIONAL":
        return "Lei nº 14.133/2021, art. 59, § 5º"
    if normalized == "GARANTIA CONTRATUAL":
        return "Lei nº 14.133/2021, arts. 96 a 102"
    return "Edital, contrato, termo de referência ou matriz de riscos"


def _money(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def calculate_required_amount(
    method: str,
    *,
    calculation_base=0,
    percentage=0,
    estimated_budget=0,
    proposal_value=0,
    informed_amount=0,
) -> float:
    """Calcula o valor exigido sem substituir a conferência do edital/contrato."""
    method = str(method or "VALOR_INFORMADO").strip().upper()
    if method == "PERCENTUAL_BASE":
        result = _money(calculation_base) * _money(percentage) / Decimal("100")
    elif method == "GARANTIA_ADICIONAL":
        result = max(_money(estimated_budget) - _money(proposal_value), Decimal("0"))
    else:
        result = _money(informed_amount)
    return float(result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def coverage_gap(required_amount, guaranteed_amount) -> float:
    gap = max(_money(required_amount) - _money(guaranteed_amount), Decimal("0"))
    return float(gap.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def days_to_expiry(end_date, today: date | None = None) -> int | None:
    if not end_date:
        return None
    today = today or today_brt()
    try:
        target = date.fromisoformat(str(end_date)[:10])
    except (TypeError, ValueError):
        return None
    return (target - today).days


def operational_status(item, today: date | None = None) -> str:
    request_status = str(item.get("request_status") or "A SOLICITAR").strip().upper()
    if request_status in {"DISPENSADA", "CANCELADA"}:
        return request_status
    days = days_to_expiry(item.get("end_date"), today)
    if days is not None and days < 0:
        return "VENCIDA"
    if request_status not in {"RECEBIDA", "EM ANÁLISE", "ACEITA"}:
        return request_status
    if days is not None and days <= 30:
        return "A VENCER"
    if request_status == "ACEITA":
        return "VIGENTE"
    return request_status


def guarantee_issues(item, contract_end_date=None, today: date | None = None) -> list[str]:
    issues = []
    status = str(item.get("request_status") or "").strip().upper()
    if status not in {"DISPENSADA", "CANCELADA"}:
        if not item.get("policy_number") and str(item.get("modality") or "").upper() in {
            "SEGURO-GARANTIA",
            "APÓLICE DE RISCOS DE ENGENHARIA",
            "APÓLICE DE RESPONSABILIDADE CIVIL",
        }:
            issues.append("número da apólice não informado")
        if not item.get("end_date"):
            issues.append("fim da vigência não informado")
        days = days_to_expiry(item.get("end_date"), today)
        if days is not None and days < 0:
            issues.append("garantia vencida")
        if contract_end_date and item.get("end_date"):
            try:
                guarantee_end = date.fromisoformat(str(item["end_date"])[:10])
                contract_end = date.fromisoformat(str(contract_end_date)[:10])
                if guarantee_end < contract_end:
                    issues.append("vigência da garantia termina antes da vigência contratual")
            except ValueError:
                pass
    return issues
