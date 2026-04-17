from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from pathlib import Path

from technocops_ddc.models import InputDocument

TITLE_META_PATTERNS = (
    re.compile(r"<meta[^>]+name=['\"]dc:title['\"][^>]+content=['\"](?P<value>[^\"']+)", re.IGNORECASE),
    re.compile(r"<title>(?P<value>.*?)</title>", re.IGNORECASE | re.DOTALL),
)
PUBLISHER_META_PATTERNS = (
    re.compile(r"<meta[^>]+name=['\"]dc:publisher['\"][^>]+content=['\"](?P<value>[^\"']+)", re.IGNORECASE),
    re.compile(r"<meta[^>]+name=['\"]publisher['\"][^>]+content=['\"](?P<value>[^\"']+)", re.IGNORECASE),
)
ISBN_PATTERN = re.compile(r"\b97[89](?:[\s-]?\d){10}\b")
PUBLISHER_TEXT_PATTERN = re.compile(r"\bBoom Voortgezet Onderwijs\b", re.IGNORECASE)


@dataclass(slots=True)
class MetadataSuggestions:
    title: str = ""
    source_isbn: str = ""
    publisher: str = ""
    source_publisher: str = ""


class DocumentMetadataExtractor:
    def extract_from_documents(self, documents: list[InputDocument]) -> MetadataSuggestions:
        if not documents:
            return MetadataSuggestions()

        raw_samples: list[str] = []
        visible_samples: list[str] = []
        for document in documents[:4]:
            raw_html = self._read_html(document.path)
            raw_samples.append(raw_html)
            visible_samples.append(self._extract_visible_text(raw_html))

        combined_raw = "\n".join(raw_samples)
        combined_visible = "\n".join(visible_samples)

        title = self._extract_title(combined_raw, visible_samples) or ""
        isbn = self._extract_isbn(combined_visible) or ""
        publisher = self._extract_publisher(combined_raw, combined_visible) or ""

        return MetadataSuggestions(
            title=title,
            source_isbn=isbn,
            publisher=publisher,
            source_publisher=publisher,
        )

    @staticmethod
    def _read_html(path: Path) -> str:
        encodings = ("utf-8", "utf-8-sig", "cp1252", "latin-1")
        for encoding in encodings:
            try:
                return path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue
        return path.read_text(encoding="utf-8", errors="ignore")

    def _extract_title(self, raw_html: str, visible_samples: list[str]) -> str:
        for pattern in TITLE_META_PATTERNS:
            match = pattern.search(raw_html)
            if not match:
                continue
            candidate = self._normalize_value(match.group("value"))
            if candidate and candidate.lower() not in {"html", "document"}:
                return candidate

        for sample in visible_samples:
            for line in sample.splitlines():
                candidate = self._normalize_value(line)
                if len(candidate) < 8:
                    continue
                if "<page>" in candidate.lower():
                    continue
                return candidate
        return ""

    def _extract_isbn(self, visible_text: str) -> str:
        match = ISBN_PATTERN.search(visible_text)
        return self._normalize_isbn(match.group(0)) if match else ""

    def _extract_publisher(self, raw_html: str, visible_text: str) -> str:
        for pattern in PUBLISHER_META_PATTERNS:
            match = pattern.search(raw_html)
            if match:
                candidate = self._normalize_value(match.group("value"))
                if candidate:
                    return candidate

        match = PUBLISHER_TEXT_PATTERN.search(visible_text)
        return self._normalize_value(match.group(0)) if match else ""

    @staticmethod
    def _extract_visible_text(raw_html: str) -> str:
        without_tags = re.sub(r"(?is)<script.*?</script>|<style.*?</style>|<[^>]+>", "\n", raw_html)
        normalized = unescape(without_tags).replace("\xa0", " ")
        normalized = re.sub(r"[ \t]+", " ", normalized)
        return re.sub(r"\n{2,}", "\n", normalized)

    @staticmethod
    def _normalize_value(value: str) -> str:
        cleaned = unescape(value).replace("\xa0", " ")
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip(" -:\t\r\n")

    @staticmethod
    def _normalize_isbn(value: str) -> str:
        digits = re.sub(r"[^0-9Xx]+", "", value)
        if len(digits) == 13:
            return f"{digits[0:3]} {digits[3:5]} {digits[5:9]} {digits[9:12]} {digits[12]}"
        return value.strip()
