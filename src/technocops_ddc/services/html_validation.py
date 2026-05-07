from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from shutil import copy2
from tempfile import TemporaryDirectory

from lxml import etree, html

from technocops_ddc.config import TEMP_DIR_PREFIX
from technocops_ddc.models import ConversionIssue, HtmlValidationResult, InputDocument, Severity


@dataclass(slots=True)
class _TagState:
    tag: str
    line: int


@dataclass(slots=True)
class _VisibleTextChunk:
    text: str
    line: int


@dataclass(slots=True)
class _SemanticToken:
    tag: str
    line: int
    is_closing: bool = False
    is_self_closing: bool = False


class HtmlSourceValidator:
    ACTUAL_TOKEN_PATTERN = re.compile(
        r"<\s*(?P<actual_closing>/)?\s*(?P<actual_tag>[A-Za-z][A-Za-z0-9:_-]*)(?P<actual_attrs>[^<>]*)>",
        re.IGNORECASE,
    )
    SEMANTIC_TOKEN_PATTERN = re.compile(r"^<(?P<closing>/)?(?P<tag>[A-Za-z][A-Za-z0-9:_-]*)(?P<self_closing>/)?>$", re.IGNORECASE)
    HTML_VOID_TAGS = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
    SEMANTIC_VOID_TAGS = {"page", "hr", "br"}
    ISSUE_SEVERITY_RANK = {
        Severity.CRITICAL: 0,
        Severity.ERROR: 1,
        Severity.WARNING: 2,
        Severity.INFO: 3,
    }

    def validate_documents(
        self,
        documents: list[InputDocument],
        progress_callback: callable | None = None,
    ) -> HtmlValidationResult:
        issues: list[ConversionIssue] = []
        with TemporaryDirectory(prefix=f"{TEMP_DIR_PREFIX}html_validator_") as temp_dir:
            temp_root = Path(temp_dir)
            total = len(documents)
            for index, document in enumerate(documents, start=1):
                temp_copy = temp_root / f"{index:03d}_{document.name}"
                try:
                    copy2(document.path, temp_copy)
                    source_text = self._read_html(temp_copy)
                except OSError as exc:
                    issues.append(
                        ConversionIssue(
                            severity=Severity.CRITICAL,
                            message=f"Unable to prepare a temporary validation copy: {exc}",
                            file_name=document.name,
                            code="html-validation-copy-failed",
                        )
                    )
                    continue

                issues.extend(self._validate_text(source_text, document.name))
                if progress_callback is not None:
                    progress_callback(
                        int((index / max(total, 1)) * 100),
                        f"Validated {document.name}",
                    )

        issues.sort(key=self._issue_sort_key)
        report_text = self._build_report_text(documents, issues)
        report_path = self._write_report(documents, report_text)
        return HtmlValidationResult(
            issues=issues,
            checked_file_count=len(documents),
            report_text=report_text,
            report_path=report_path,
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

    def _validate_text(self, source_text: str, file_name: str) -> list[ConversionIssue]:
        issues: list[ConversionIssue] = []
        actual_stack: list[_TagState] = []
        semantic_stack: list[_TagState] = []
        line_starts = self._build_line_starts(source_text)

        for match in self.ACTUAL_TOKEN_PATTERN.finditer(source_text):
            line_number = self._line_number(line_starts, match.start())
            tag = (match.group("actual_tag") or "").lower()
            attrs = match.group("actual_attrs") or ""
            is_closing = bool(match.group("actual_closing"))
            if not tag:
                continue
            if not is_closing and self._is_actual_void_tag(tag, attrs):
                continue
            self._handle_token(
                stack=actual_stack,
                tag=tag,
                is_closing=is_closing,
                line_number=line_number,
                file_name=file_name,
                issues=issues,
                label="HTML tag",
            )

        for semantic_token in self._extract_semantic_tokens(source_text):
            if not semantic_token.is_closing and self._is_semantic_void_tag(semantic_token.tag, semantic_token.is_self_closing):
                continue
            self._handle_token(
                stack=semantic_stack,
                tag=semantic_token.tag,
                is_closing=semantic_token.is_closing,
                line_number=semantic_token.line,
                file_name=file_name,
                issues=issues,
                label="Escaped semantic tag",
            )

        self._report_unclosed_tags(actual_stack, issues, file_name, "HTML tag")
        self._report_unclosed_tags(semantic_stack, issues, file_name, "Escaped semantic tag")
        return issues

    def _handle_token(
        self,
        *,
        stack: list[_TagState],
        tag: str,
        is_closing: bool,
        line_number: int,
        file_name: str,
        issues: list[ConversionIssue],
        label: str,
    ) -> None:
        if not is_closing:
            stack.append(_TagState(tag=tag, line=line_number))
            return

        if not stack:
            issues.append(
                ConversionIssue(
                    severity=Severity.ERROR,
                    message=f"{label} </{tag}> was found without a matching opening tag.",
                    file_name=file_name,
                    line=line_number,
                    tag=tag,
                    code="html-tag-unexpected-close",
                )
            )
            return

        top = stack[-1]
        if top.tag == tag:
            stack.pop()
            return

        matching_index = next((index for index in range(len(stack) - 1, -1, -1) if stack[index].tag == tag), None)
        if matching_index is None:
            issues.append(
                ConversionIssue(
                    severity=Severity.ERROR,
                    message=(
                        f"{label} mismatch: expected </{top.tag}> to close <{top.tag}> opened at line {top.line}, "
                        f"but found </{tag}>."
                    ),
                    file_name=file_name,
                    line=line_number,
                    tag=tag,
                    code="html-tag-mismatch",
                )
            )
            return

        issues.append(
            ConversionIssue(
                severity=Severity.ERROR,
                message=(
                    f"{label} nesting error: <{top.tag}> opened at line {top.line} must be closed before </{tag}> "
                    f"at line {line_number}."
                ),
                file_name=file_name,
                line=line_number,
                tag=tag,
                code="html-tag-nesting-error",
            )
        )
        del stack[matching_index:]

    def _report_unclosed_tags(
        self,
        stack: list[_TagState],
        issues: list[ConversionIssue],
        file_name: str,
        label: str,
    ) -> None:
        for state in reversed(stack):
            issues.append(
                ConversionIssue(
                    severity=Severity.ERROR,
                    message=f"{label} <{state.tag}> opened at line {state.line} was not closed before the end of the file.",
                    file_name=file_name,
                    line=state.line,
                    tag=state.tag,
                    code="html-tag-unclosed",
                )
            )

    @staticmethod
    def _is_actual_void_tag(tag: str, attrs: str) -> bool:
        if tag in HtmlSourceValidator.HTML_VOID_TAGS:
            return True
        return attrs.rstrip().endswith("/")

    @staticmethod
    def _is_semantic_void_tag(tag: str, is_self_closing: bool) -> bool:
        return tag in HtmlSourceValidator.SEMANTIC_VOID_TAGS or is_self_closing

    def _extract_semantic_tokens(self, source_text: str) -> list[_SemanticToken]:
        tokens: list[_SemanticToken] = []
        token_buffer: list[str] = []
        token_line = 1
        capturing = False

        for chunk in self._extract_visible_text_chunks(source_text):
            if not chunk.text:
                continue
            for character in chunk.text:
                if not capturing:
                    if character == "<":
                        capturing = True
                        token_buffer = ["<"]
                        token_line = chunk.line
                    continue

                if character == "<":
                    token_buffer = ["<"]
                    token_line = chunk.line
                    continue

                token_buffer.append(character)
                if character != ">":
                    continue

                token = self._parse_semantic_token("".join(token_buffer), token_line)
                if token is not None:
                    tokens.append(token)
                token_buffer = []
                capturing = False

        return tokens

    def _extract_visible_text_chunks(self, source_text: str) -> list[_VisibleTextChunk]:
        parser = html.HTMLParser(recover=True)
        try:
            root = html.fromstring(source_text, parser=parser)
        except (etree.ParserError, ValueError):
            return []

        chunks: list[_VisibleTextChunk] = []
        for text_node in root.xpath("//text()"):
            parent = text_node.getparent()
            if parent is None or self._should_skip_text_node(parent):
                continue
            text = str(text_node)
            if not text:
                continue
            chunks.append(_VisibleTextChunk(text=text, line=getattr(parent, "sourceline", None) or 1))
        return chunks

    def _parse_semantic_token(self, raw_text: str, line_number: int) -> _SemanticToken | None:
        compact_text = re.sub(r"\s+", "", raw_text)
        match = self.SEMANTIC_TOKEN_PATTERN.match(compact_text)
        if match is None:
            return None
        return _SemanticToken(
            tag=(match.group("tag") or "").lower(),
            line=line_number,
            is_closing=bool(match.group("closing")),
            is_self_closing=bool(match.group("self_closing")),
        )

    @staticmethod
    def _should_skip_text_node(element) -> bool:
        current = element
        while current is not None:
            tag = getattr(current, "tag", None)
            if not isinstance(tag, str):
                return True
            if tag.lower() in {"head", "title", "script", "style", "meta", "link", "noscript"}:
                return True
            current = current.getparent()
        return False

    @staticmethod
    def _build_line_starts(source_text: str) -> list[int]:
        line_starts = [0]
        line_starts.extend(match.end() for match in re.finditer(r"\n", source_text))
        return line_starts

    @staticmethod
    def _line_number(line_starts: list[int], position: int) -> int:
        return bisect_right(line_starts, position)

    def _build_report_text(self, documents: list[InputDocument], issues: list[ConversionIssue]) -> str:
        timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        source_note = "Source files were not modified. Validation was performed on temporary copies."
        checked_files = len(documents)
        if not issues:
            return (
                "HTML Source Validation Report\n"
                f"Generated: {timestamp}\n"
                f"Checked Files: {checked_files}\n"
                "Status: Validation successful 100%.\n"
                f"{source_note}\n"
            )

        report_lines = [
            "HTML Source Validation Report",
            f"Generated: {timestamp}",
            f"Checked Files: {checked_files}",
            "Status: Validation failed. Check the error log below.",
            source_note,
            "",
            f"Total Issues: {len(issues)}",
            "",
        ]
        report_lines.extend(issue.display_text for issue in issues)
        report_lines.append("")
        return "\n".join(report_lines)

    def _write_report(self, documents: list[InputDocument], report_text: str) -> Path | None:
        if not documents:
            return None
        report_path = self._report_path(documents)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_text, encoding="utf-8")
        return report_path

    def _report_path(self, documents: list[InputDocument]) -> Path:
        first_document = documents[0]
        origin_value = (first_document.origin or "").strip()
        if origin_value:
            origin_path = Path(origin_value)
            if origin_path.suffix.lower() == ".zip":
                return origin_path.parent / f"{origin_path.stem}_html_validation.report.txt"

        series_key = self._series_key(first_document.path.stem) or first_document.path.stem
        return first_document.path.parent / f"{series_key}_html_validation.report.txt"

    @staticmethod
    def _series_key(document_name: str) -> str:
        cleaned = document_name.strip()
        if not cleaned:
            return ""
        return cleaned.split("_", 1)[0]

    def _issue_sort_key(self, issue: ConversionIssue) -> tuple[int, str, int]:
        return (
            self.ISSUE_SEVERITY_RANK.get(issue.severity, 99),
            issue.file_name,
            issue.line or 0,
        )
