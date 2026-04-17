from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from .config import DEFAULT_DOC_TYPE, DEFAULT_LANGUAGE


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(slots=True)
class ConversionIssue:
    severity: Severity
    message: str
    code: str = ""
    file_name: str = ""
    line: int | None = None
    tag: str = ""

    @property
    def display_text(self) -> str:
        location_parts: list[str] = []
        if self.file_name:
            location_parts.append(self.file_name)
        if self.line is not None:
            location_parts.append(f"line {self.line}")
        if self.tag:
            location_parts.append(f"tag <{self.tag}>")

        location = f" ({', '.join(location_parts)})" if location_parts else ""
        prefix = self.severity.value.upper()
        return f"[{prefix}] {self.message}{location}"


@dataclass(slots=True)
class InputDocument:
    path: Path
    order: int
    origin: str = ""
    document_id: str = field(default_factory=lambda: uuid4().hex)

    @property
    def name(self) -> str:
        return self.path.name


@dataclass(slots=True)
class InputBatch:
    documents: list[InputDocument]
    source_label: str
    temporary_directory: TemporaryDirectory[str] | None = None


@dataclass(slots=True)
class PageRangeSelection:
    start_page: int
    end_page: int

    def validate(self) -> list[str]:
        issues: list[str] = []
        if self.start_page <= 0:
            issues.append("Start Page must be greater than 0.")
        if self.end_page <= 0:
            issues.append("End Page must be greater than 0.")
        if self.start_page > self.end_page:
            issues.append("Start Page cannot be greater than End Page.")
        return issues

    @property
    def label(self) -> str:
        if self.start_page == self.end_page:
            return f"Page {self.start_page}"
        return f"Pages {self.start_page}-{self.end_page}"

    def includes(self, page_number: int) -> bool:
        return self.start_page <= page_number <= self.end_page


@dataclass(slots=True)
class ImageAsset:
    source_path: Path
    output_name: str
    original_reference: str = ""


@dataclass(slots=True)
class AuthorEntry:
    surname: str = ""
    first_name: str = ""

    @property
    def is_empty(self) -> bool:
        return not (self.surname.strip() or self.first_name.strip())

    @property
    def meta_display(self) -> str:
        parts = [part.strip() for part in (self.surname, self.first_name) if part.strip()]
        return ", ".join(parts)

    @property
    def frontmatter_display(self) -> str:
        parts = [part.strip() for part in (self.first_name, self.surname) if part.strip()]
        return " ".join(parts)


@dataclass(slots=True)
class DTBookMetadata:
    uid: str
    title: str
    creator_surname: str
    creator_first_name: str
    completion_date: str
    publisher: str
    language: str
    identifier: str
    source_isbn: str
    produced_date: str
    source_publisher: str
    producer: str
    authors: list[AuthorEntry] = field(default_factory=list)
    doc_type: str = DEFAULT_DOC_TYPE
    raw_version: str = "N"
    doc_hyphenate: str = "Y"
    guideline_version: str = "2014-1.1"

    @classmethod
    def default(cls) -> "DTBookMetadata":
        today = date.today().isoformat()
        return cls(
            uid="",
            title="",
            creator_surname="",
            creator_first_name="",
            completion_date=today,
            publisher="",
            language=DEFAULT_LANGUAGE,
            identifier="",
            source_isbn="",
            produced_date=today,
            source_publisher="",
            producer="",
        )

    @property
    def creator_display(self) -> str:
        displays = self.creator_displays
        return displays[0] if displays else ""

    @property
    def normalized_authors(self) -> list[AuthorEntry]:
        authors = [author for author in self.authors if not author.is_empty]
        if authors:
            return authors

        fallback_author = AuthorEntry(
            surname=self.creator_surname,
            first_name=self.creator_first_name,
        )
        return [] if fallback_author.is_empty else [fallback_author]

    @property
    def creator_displays(self) -> list[str]:
        return [author.meta_display for author in self.normalized_authors if author.meta_display]

    @property
    def frontmatter_authors(self) -> list[str]:
        return [author.frontmatter_display for author in self.normalized_authors if author.frontmatter_display]

    def to_meta_pairs(self) -> list[tuple[str, str]]:
        meta_pairs = [
            ("dtb:uid", self.uid),
            ("dc:Title", self.title),
            ("dc:Date", self.completion_date),
            ("dc:Publisher", self.publisher),
            ("dc:Language", self.language),
            ("dc:Identifier", self.identifier),
            ("dc:Format", "ANSI/NISO Z39.86-2005"),
            ("dc:Source", self.source_isbn),
            ("dtb:producedDate", self.produced_date),
            ("prod:docType", self.doc_type),
            ("prod:rawVersion", self.raw_version),
            ("prod:docHyphenate", self.doc_hyphenate),
            ("prod:producer", self.producer),
            ("prod:guidelineversion", self.guideline_version),
            ("dtb:sourcePublisher", self.source_publisher),
        ]
        creator_pairs = [("dc:Creator", creator) for creator in self.creator_displays]
        meta_pairs[2:2] = creator_pairs or [("dc:Creator", "")]
        if self.doc_type == "sv":
            meta_pairs.insert(-3, ("prod:colophon", "1"))
        return meta_pairs


@dataclass(slots=True)
class ConversionResult:
    xml_text: str
    issues: list[ConversionIssue] = field(default_factory=list)
    image_assets: list[ImageAsset] = field(default_factory=list)

    @property
    def has_critical_errors(self) -> bool:
        return any(issue.severity == Severity.CRITICAL for issue in self.issues)

    @property
    def has_errors(self) -> bool:
        return any(issue.severity in {Severity.ERROR, Severity.CRITICAL} for issue in self.issues)


@dataclass(slots=True)
class SavedOutput:
    xml_path: Path
    json_report_path: Path
    text_report_path: Path
    image_output_dir: Path | None = None


@dataclass(slots=True)
class UpdateInfo:
    version: str
    published_at: str
    summary: str
    html_url: str
    asset_url: str = ""
    asset_name: str = ""
