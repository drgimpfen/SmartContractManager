from fastapi import APIRouter
from .auth import router as auth_router
from .dashboard import router as dashboard_router
from .provider import router as provider_router
from .contract import router as contract_router
from .settings import router as settings_router

__all__ = ["auth_router", "dashboard_router", "provider_router", "contract_router", "settings_router"]
