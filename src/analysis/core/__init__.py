"""Core analytics primitives for loading, shaping, plotting, and reporting.

These helpers form the internal contract used by plotters and the analytics
entry point while keeping database reads, dataset preparation, figure export,
and report writing separated.
"""

from .data_processor import AnalyticsDataset, DataProcessor
from .db_handler import DBHandler
from .plot_engine import PlotEngine
from .report_generator import ReportGenerator

__all__ = [
    "AnalyticsDataset",
    "DBHandler",
    "DataProcessor",
    "PlotEngine",
    "ReportGenerator",
]
