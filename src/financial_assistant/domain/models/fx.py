from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class ExchangeRate:
    casa: str        # "oficial" | "blue" | "mep" | "mayorista"
    nombre: str      # "Oficial" | "Blue" | "MEP" | etc.
    compra: Decimal
    venta: Decimal
    updated_at: datetime
