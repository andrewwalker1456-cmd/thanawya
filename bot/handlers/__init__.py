# Thanaweya Amma Bot — Handlers Package
from .shared import get_main_keyboard, SearchStates, AdminStates

__all__ = [
    "get_main_keyboard", "SearchStates", "AdminStates",
]

def get_routers():
    """Lazy-load routers to avoid circular imports at package level."""
    from .dashboard import router as dashboard_router
    from .search import router as search_router
    from .admin import router as admin_router
    return dashboard_router, search_router, admin_router