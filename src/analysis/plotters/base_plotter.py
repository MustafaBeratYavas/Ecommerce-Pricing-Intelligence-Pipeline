"""Shared rendering contract for strategic analytics plotters.

BasePlotter wraps each concrete chart in a consistent PlotArtifact so the
reporting layer can stay independent of plot-specific implementation details.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.analysis.core.data_processor import AnalyticsDataset
from src.analysis.core.plot_engine import PlotEngine


@dataclass(frozen=True)
class PlotArtifact:
    plotter: str
    title: str
    filename: str
    path: str
    summary: str


class BasePlotter(ABC):
    title: str
    filename: str
    summary: str

    def render(self, dataset: AnalyticsDataset, engine: PlotEngine) -> PlotArtifact:
        # Wrap concrete rendering in the artifact contract consumed by reports.
        fig = self.create_plot(dataset, engine)
        path = engine.save_figure(fig, self.filename)
        return PlotArtifact(
            plotter=self.__class__.__name__,
            title=self.title,
            filename=self.filename,
            path=path,
            summary=self.summary,
        )

    @abstractmethod
    def create_plot(self, dataset: AnalyticsDataset, engine: PlotEngine): ...
