"""业务页面。"""

from .components import ComponentsPage
from .dashboard import DashboardPage
from .feeders import FeedersPage
from .logs import LogsPage
from .manual import ManualPage
from .production import ProductionPage
from .programming import ProgrammingPage
from .settings import SettingsPage
from .vision import VisionPage

__all__ = [
    "ComponentsPage",
    "DashboardPage",
    "FeedersPage",
    "LogsPage",
    "ManualPage",
    "ProductionPage",
    "ProgrammingPage",
    "SettingsPage",
    "VisionPage",
]
