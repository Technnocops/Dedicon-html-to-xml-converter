from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from technocops_ddc.models import ConversionResult, DTBookMetadata, InputDocument, PageRangeSelection
from technocops_ddc.services.conversion_service import ConversionService


class ConversionWorker(QObject):
    progressChanged = pyqtSignal(int, str)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        conversion_service: ConversionService,
        documents: list[InputDocument],
        metadata: DTBookMetadata,
        page_range: PageRangeSelection | None = None,
    ) -> None:
        super().__init__()
        self.conversion_service = conversion_service
        self.documents = documents
        self.metadata = metadata
        self.page_range = page_range

    @pyqtSlot()
    def run(self) -> None:
        try:
            result = self.conversion_service.convert(
                self.documents,
                self.metadata,
                page_range=self.page_range,
                progress_callback=self._report_progress,
            )
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
            return

        self.finished.emit(result)

    def _report_progress(self, value: int, message: str) -> None:
        self.progressChanged.emit(value, message)
