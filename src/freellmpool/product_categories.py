"""Product-category configuration for the procurement SaaS MVP.

The catalog is intentionally storage-independent in P1: it provides stable,
reviewable category templates without changing existing package data.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CategoryParameter:
    key: str
    label: str
    mandatory: bool = True
    unit: str | None = None


@dataclass(frozen=True)
class ProductCategory:
    key: str
    name: str
    description: str
    parameters: tuple[CategoryParameter, ...]


_PRODUCT_CATEGORIES: tuple[ProductCategory, ...] = (
    ProductCategory(
        key="MOTOR",
        name="LV Induction Motor",
        description="Low-voltage three-phase induction motor procurement.",
        parameters=(
            CategoryParameter("rated_power", "Rated power", True, "kW"),
            CategoryParameter("rated_voltage", "Rated voltage", True, "V"),
            CategoryParameter("frequency", "Frequency", True, "Hz"),
            CategoryParameter("speed", "Rated speed", True, "rpm"),
            CategoryParameter("current", "Rated current", False, "A"),
            CategoryParameter("efficiency_class", "Efficiency class", False),
            CategoryParameter("ingress_protection", "Ingress protection", False),
        ),
    ),
    ProductCategory(
        key="VFD",
        name="Variable Frequency Drive",
        description="Low-voltage variable frequency drive procurement.",
        parameters=(
            CategoryParameter("rated_power", "Rated motor power", True, "kW"),
            CategoryParameter("rated_voltage", "Rated voltage", True, "V"),
            CategoryParameter("rated_current", "Rated output current", True, "A"),
            CategoryParameter("frequency", "Output frequency", False, "Hz"),
            CategoryParameter("overload", "Overload capability", False),
            CategoryParameter("ingress_protection", "Ingress protection", False),
        ),
    ),
    ProductCategory(
        key="PLC",
        name="PLC / Control System",
        description="PLC, controller and industrial control system procurement.",
        parameters=(
            CategoryParameter("controller_type", "Controller type", True),
            CategoryParameter("safety_rating", "Safety rating", False),
            CategoryParameter("communication", "Communication protocols", False),
            CategoryParameter("io_capacity", "I/O capacity", False),
            CategoryParameter("redundancy", "Redundancy", False),
        ),
    ),
    ProductCategory(
        key="INSTRUMENTATION",
        name="Instrumentation",
        description="Industrial measurement and instrumentation procurement.",
        parameters=(
            CategoryParameter("measurement", "Measurement variable", True),
            CategoryParameter("range", "Measurement range", True),
            CategoryParameter("accuracy", "Accuracy", False),
            CategoryParameter("process_connection", "Process connection", False),
            CategoryParameter("ingress_protection", "Ingress protection", False),
        ),
    ),
    ProductCategory(
        key="VALVE",
        name="Industrial Valve",
        description="Industrial process valve procurement.",
        parameters=(
            CategoryParameter("valve_type", "Valve type", True),
            CategoryParameter("nominal_size", "Nominal size", True),
            CategoryParameter("pressure_class", "Pressure class", True),
            CategoryParameter("body_material", "Body material", False),
            CategoryParameter("actuation", "Actuation", False),
        ),
    ),
    ProductCategory(
        key="SWITCHGEAR",
        name="LV/MV Switchgear",
        description="Low- and medium-voltage switchgear procurement.",
        parameters=(
            CategoryParameter("voltage", "Rated voltage", True, "V"),
            CategoryParameter("current", "Rated current", True, "A"),
            CategoryParameter("short_circuit", "Short-circuit withstand", False),
            CategoryParameter("protection", "Protection system", False),
            CategoryParameter("ingress_protection", "Ingress protection", False),
        ),
    ),
)

CATEGORY_INDEX = {item.key: item for item in _PRODUCT_CATEGORIES}


def list_product_categories() -> tuple[ProductCategory, ...]:
    """Return the supported procurement category configurations."""
    return _PRODUCT_CATEGORIES


def get_product_category(key: str) -> ProductCategory | None:
    """Return a category configuration by case-insensitive key."""
    return CATEGORY_INDEX.get(key.strip().upper())
