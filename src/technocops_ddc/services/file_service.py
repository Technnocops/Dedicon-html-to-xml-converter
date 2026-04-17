from __future__ import annotations

import re
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from technocops_ddc.config import SUPPORTED_HTML_EXTENSIONS, TEMP_DIR_PREFIX
from technocops_ddc.models import InputBatch, InputDocument


def natural_sort_key(value: str) -> list[str | int]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value)]


class InputCollectionService:
    def collect_from_files(self, paths: list[Path], source_label: str = "Selected files") -> InputBatch:
        documents = self._build_documents([path for path in paths if self.is_supported_html(path)])
        return InputBatch(documents=documents, source_label=source_label)

    def collect_from_folder(self, folder: Path) -> InputBatch:
        html_files = sorted(
            [path for path in folder.rglob("*") if self.is_supported_html(path)],
            key=lambda path: natural_sort_key(str(path.relative_to(folder))),
        )
        return InputBatch(
            documents=self._build_documents(html_files),
            source_label=f"Folder: {folder.name}",
        )

    def collect_from_zip(self, archive_path: Path) -> InputBatch:
        temp_dir = TemporaryDirectory(prefix=TEMP_DIR_PREFIX)
        extraction_root = Path(temp_dir.name)
        with ZipFile(archive_path) as archive:
            archive.extractall(extraction_root)

        html_files = sorted(
            [path for path in extraction_root.rglob("*") if self.is_supported_html(path)],
            key=lambda path: natural_sort_key(str(path.relative_to(extraction_root))),
        )
        return InputBatch(
            documents=self._build_documents(html_files),
            source_label=f"ZIP: {archive_path.name}",
            temporary_directory=temp_dir,
        )

    @staticmethod
    def is_supported_html(path: Path) -> bool:
        return path.is_file() and path.suffix.lower() in SUPPORTED_HTML_EXTENSIONS

    @staticmethod
    def is_zip(path: Path) -> bool:
        return path.is_file() and path.suffix.lower() == ".zip"

    @staticmethod
    def _build_documents(paths: list[Path]) -> list[InputDocument]:
        return [
            InputDocument(path=path, order=index, origin=str(path.parent))
            for index, path in enumerate(paths, start=1)
        ]
