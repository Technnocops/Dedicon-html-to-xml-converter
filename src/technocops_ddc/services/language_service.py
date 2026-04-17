from __future__ import annotations

import re
from html import unescape
from pathlib import Path

from technocops_ddc.config import DEFAULT_LANGUAGE
from technocops_ddc.models import InputDocument

DECLARED_LANGUAGE_PATTERNS = (
    re.compile(r"<html[^>]+\blang=['\"]?(?P<code>[A-Za-z-]+)", re.IGNORECASE),
    re.compile(r"\bxml:lang=['\"](?P<code>[A-Za-z-]+)", re.IGNORECASE),
    re.compile(r"<meta[^>]+http-equiv=['\"]content-language['\"][^>]+content=['\"](?P<code>[A-Za-z-]+)", re.IGNORECASE),
    re.compile(r"<meta[^>]+name=['\"]dc:Language['\"][^>]+content=['\"](?P<code>[A-Za-z-]+)", re.IGNORECASE),
)

LANGUAGE_STOPWORDS = {
    "nl": {
        "de",
        "het",
        "een",
        "en",
        "van",
        "voor",
        "met",
        "niet",
        "wat",
        "je",
        "ik",
        "op",
        "bij",
        "dit",
        "dat",
        "hoe",
        "als",
        "ook",
        "naar",
        "uit",
    },
    "en": {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "you",
        "your",
        "are",
        "was",
        "what",
        "when",
        "where",
        "into",
        "about",
        "have",
        "will",
        "not",
        "can",
    },
    "sv": {
        "och",
        "det",
        "att",
        "som",
        "med",
        "den",
        "för",
        "inte",
        "är",
        "en",
        "på",
        "till",
        "har",
        "du",
        "vad",
        "hur",
        "om",
        "kan",
    },
    "ro": {
        "si",
        "este",
        "sunt",
        "care",
        "pentru",
        "din",
        "cu",
        "sau",
        "nu",
        "ce",
        "cum",
        "la",
        "in",
        "pe",
        "un",
        "o",
        "de",
        "ale",
        "fie",
    },
}


class DocumentLanguageDetector:
    def detect_from_documents(self, documents: list[InputDocument]) -> str:
        if not documents:
            return DEFAULT_LANGUAGE

        combined_text_parts: list[str] = []
        for document in documents[:3]:
            raw_html = self._read_html(document.path)
            declared_language = self._detect_declared_language(raw_html)
            if declared_language:
                return declared_language
            combined_text_parts.append(self._extract_visible_text(raw_html))

        return self._detect_by_stopwords(" ".join(combined_text_parts))

    @staticmethod
    def _read_html(path: Path) -> str:
        encodings = ("utf-8", "utf-8-sig", "cp1252", "latin-1")
        for encoding in encodings:
            try:
                return path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue
        return path.read_text(encoding="utf-8", errors="ignore")

    def _detect_declared_language(self, raw_html: str) -> str:
        for pattern in DECLARED_LANGUAGE_PATTERNS:
            match = pattern.search(raw_html)
            if match:
                language_code = self._normalize_language_code(match.group("code"))
                if language_code:
                    return language_code
        return ""

    def _detect_by_stopwords(self, text: str) -> str:
        words = re.findall(r"[A-Za-zÀ-ÿ]+", text.lower())
        if not words:
            return DEFAULT_LANGUAGE

        scores = {
            code: sum(1 for word in words if word in stopwords)
            for code, stopwords in LANGUAGE_STOPWORDS.items()
        }
        best_code, best_score = max(scores.items(), key=lambda item: item[1])
        if best_score < 3:
            return DEFAULT_LANGUAGE
        return best_code

    @staticmethod
    def _extract_visible_text(raw_html: str) -> str:
        without_tags = re.sub(r"(?is)<script.*?</script>|<style.*?</style>|<[^>]+>", " ", raw_html)
        normalized = unescape(without_tags).replace("\xa0", " ")
        return re.sub(r"\s+", " ", normalized)

    @staticmethod
    def _normalize_language_code(value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned:
            return ""
        primary_code = cleaned.split("-", 1)[0]
        return primary_code if re.fullmatch(r"[a-z]{2,3}", primary_code) else ""
