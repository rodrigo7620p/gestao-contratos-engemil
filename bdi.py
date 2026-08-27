from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP


TAX_FIELDS = ("pis", "cofins", "iss", "cprb", "other_taxes")
COMPOSED_INDIRECT_FIELDS = (
    "central_administration",
    "insurance",
    "risks",
    "guarantees",
    "other_indirect_costs",
)


def _decimal(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def tax_total(values) -> Decimal:
    return sum((_decimal(values.get(field)) for field in TAX_FIELDS), Decimal("0"))


def composed_indirect_total(values) -> Decimal:
    return sum(
        (_decimal(values.get(field)) for field in COMPOSED_INDIRECT_FIELDS),
        Decimal("0"),
    )


def calculate_bdi(values) -> Decimal:
    """Retorna o percentual do BDI, e não a fração decimal."""
    method = str(values.get("calculation_method") or "FORMULA_COMPOSTA").upper()
    taxes = tax_total(values)
    profit = _decimal(values.get("profit"))

    if method == "SOMA_DIRETA":
        return (
            _decimal(values.get("indirect_costs")) + profit + taxes
        ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    denominator = Decimal("1") - taxes / Decimal("100")
    if denominator <= 0:
        raise ValueError("A soma dos tributos deve ser inferior a 100%.")

    acsgr = composed_indirect_total(values)
    financial_expenses = _decimal(values.get("financial_expenses"))
    fraction = (
        (Decimal("1") + acsgr / Decimal("100"))
        * (Decimal("1") + financial_expenses / Decimal("100"))
        * (Decimal("1") + profit / Decimal("100"))
        / denominator
        - Decimal("1")
    )
    rounding_method = str(values.get("rounding_method") or "TRUNCAR_4").upper()
    if rounding_method == "ARREDONDAR_2":
        return (fraction * Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    truncated_fraction = fraction.quantize(Decimal("0.0001"), rounding=ROUND_DOWN)
    return (truncated_fraction * Decimal("100")).quantize(Decimal("0.01"))

