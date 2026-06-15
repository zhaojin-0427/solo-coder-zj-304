from .medicines import router as medicines_router
from .baby import router as baby_router
from .records import router as records_router
from .restock import router as restock_router
from .risk import router as risk_router
from .statistics import router as statistics_router
from .baby_medicine_config import router as baby_medicine_config_router

__all__ = [
    "medicines_router",
    "baby_router",
    "records_router",
    "restock_router",
    "risk_router",
    "statistics_router",
    "baby_medicine_config_router"
]
