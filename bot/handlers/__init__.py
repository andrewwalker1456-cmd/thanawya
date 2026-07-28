# Thanaweya Amma Bot — Handlers Package
from .shared import get_main_keyboard, SearchStates, AdminStates

__all__ = [
    "get_main_keyboard", "SearchStates", "AdminStates",
]

def get_routers():
    """Lazy-load routers to avoid circular imports at package level."""
    from .admin import router as admin_router
    from .search import router as search_router
    from .dashboard import router as dashboard_router
    return admin_router, search_router, dashboard_router