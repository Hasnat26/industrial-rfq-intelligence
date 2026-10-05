"""HTTP API for the industrial procurement SaaS MVP."""

from .app import app
from .assets import router as assets_router
from .lifecycle import router as lifecycle_router
from .procurement_memory import router as procurement_memory_router

app.include_router(procurement_memory_router)

__all__ = ["app"]

app.include_router(lifecycle_router)
app.include_router(assets_router)
