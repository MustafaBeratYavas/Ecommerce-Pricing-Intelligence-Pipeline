"""Shared abstract contract for strategic chart plotters."""

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
        # Wrap concrete plot rendering in a stable artifact contract.
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
