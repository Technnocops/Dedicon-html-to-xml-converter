from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from lxml import etree

from technocops_ddc.models import ConversionIssue, ConversionResult, DTBookMetadata, InputDocument, PageRangeSelection, SavedOutput, Severity
from technocops_ddc.services.dtbook_converter import DTBookConverter
from technocops_ddc.services.validation import DTBookValidator


class ConversionService:
    PAGENUM_TAG_PATTERN = re.compile(r"<pagenum\b(?P<attrs>[^>]*)>(?P<content>.*?)</pagenum>", re.IGNORECASE | re.DOTALL)
    LEVEL_TOKEN_PATTERN = re.compile(r"<(?P<closing>/)?(?P<tag>level[1-6])\b(?P<attrs>[^>]*)>", re.IGNORECASE)

    def __init__(
        self,
        converter: DTBookConverter | None = None,
        validator: DTBookValidator | None = None,
    ) -> None:
        self.converter = converter or DTBookConverter()
        self.validator = validator or DTBookValidator()

    def convert(
        self,
        documents: list[InputDocument],
        metadata: DTBookMetadata,
        page_range: PageRangeSelection | None = None,
        progress_callback: callable | None = None,
    ) -> ConversionResult:
        result = self.converter.convert(documents, metadata, page_range=page_range, progress_callback=progress_callback)
        validation_issues = self.validator.validate(result.xml_text)
        result.issues.extend(validation_issues)
        result.issues.sort(key=self._issue_sort_key)
        return result

    def save_output(self, destination: Path, result: ConversionResult) -> SavedOutput:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(result.xml_text, encoding="utf-8")

        report_payload = self.build_error_report(result)
        json_report_path = destination.with_suffix(".report.json")
        text_report_path = destination.with_suffix(".report.txt")
        image_output_dir: Path | None = None

        json_report_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
        text_report_path.write_text(self._build_text_report(result.issues), encoding="utf-8")

        if result.image_assets:
            image_output_dir = destination.parent / "img"
            image_output_dir.mkdir(parents=True, exist_ok=True)
            for asset in result.image_assets:
                if asset.source_path.exists():
                    shutil.copy2(asset.source_path, image_output_dir / asset.output_name)

        return SavedOutput(
            xml_path=destination,
            json_report_path=json_report_path,
            text_report_path=text_report_path,
            image_output_dir=image_output_dir,
        )

    def finalize_xml_ids(
        self,
        xml_text: str,
        *,
        regenerate_page_ids: bool = False,
        regenerate_level_ids: bool = False,
    ) -> str:
        if not regenerate_page_ids and not regenerate_level_ids:
            return xml_text

        if regenerate_page_ids:
            xml_text = self._regenerate_page_ids_in_text(xml_text)
        if regenerate_level_ids:
            xml_text = self._regenerate_level_ids_in_text(xml_text)

        return xml_text

    def extract_uid_from_xml(self, xml_text: str) -> str:
        parser = etree.XMLParser(remove_blank_text=False, recover=True)
        try:
            root = etree.fromstring(xml_text.encode("utf-8"), parser=parser)
        except etree.XMLSyntaxError:
            name_first = re.search(r'<meta\b[^>]*\bname="dtb:uid"[^>]*\bcontent="([^"]*)"', xml_text)
            if name_first:
                return name_first.group(1).strip()
            content_first = re.search(r'<meta\b[^>]*\bcontent="([^"]*)"[^>]*\bname="dtb:uid"', xml_text)
            return content_first.group(1).strip() if content_first else ""

        matches = root.xpath(".//*[local-name()='meta'][@name='dtb:uid']")
        if not matches:
            return ""
        return (matches[0].get("content") or "").strip()

    @staticmethod
    def build_error_report(result: ConversionResult) -> dict:
        return {
            "summary": {
                "totalIssues": len(result.issues),
                "critical": sum(issue.severity == Severity.CRITICAL for issue in result.issues),
                "errors": sum(issue.severity == Severity.ERROR for issue in result.issues),
                "warnings": sum(issue.severity == Severity.WARNING for issue in result.issues),
                "info": sum(issue.severity == Severity.INFO for issue in result.issues),
            },
            "issues": [
                {
                    "severity": issue.severity.value,
                    "code": issue.code,
                    "message": issue.message,
                    "file": issue.file_name,
                    "line": issue.line,
                    "tag": issue.tag,
                }
                for issue in result.issues
            ],
        }

    @staticmethod
    def validate_metadata(metadata: DTBookMetadata) -> list[str]:
        required_fields = {
            "UID": metadata.uid,
            "Title": metadata.title,
            "Author": "ok" if metadata.normalized_authors else "",
            "Document Type": metadata.doc_type,
            "Publisher": metadata.publisher,
            "Language": metadata.language,
            "Identifier": metadata.identifier,
            "Source Publisher": metadata.source_publisher,
            "Producer": metadata.producer,
        }
        return [label for label, value in required_fields.items() if not value.strip()]

    @staticmethod
    def validate_page_range(page_range: PageRangeSelection | None) -> list[str]:
        if page_range is None:
            return []
        return page_range.validate()

    @staticmethod
    def _issue_sort_key(issue: ConversionIssue) -> tuple[int, str, int]:
        severity_rank = {
            Severity.CRITICAL: 0,
            Severity.ERROR: 1,
            Severity.WARNING: 2,
            Severity.INFO: 3,
        }
        return (severity_rank[issue.severity], issue.file_name, issue.line or 0)

    @staticmethod
    def _build_text_report(issues: list[ConversionIssue]) -> str:
        if not issues:
            return "No validation issues were detected.\n"
        return "\n".join(issue.display_text for issue in issues) + "\n"

    def _regenerate_page_ids_in_text(self, xml_text: str) -> str:
        def replace_match(match: re.Match[str]) -> str:
            attrs = match.group("attrs")
            content = match.group("content")
            visible_text = re.sub(r"<[^>]+>", "", content)
            page_value = visible_text.strip()
            page_type, page_id = self._page_attributes(page_value)
            attrs = self._set_attribute(attrs, "id", page_id)
            attrs = self._set_attribute(attrs, "page", page_type)
            return f"<pagenum{attrs}>{content}</pagenum>"

        return self.PAGENUM_TAG_PATTERN.sub(replace_match, xml_text)

    def _regenerate_level_ids_in_text(self, xml_text: str) -> str:
        sequence = 0
        stack: list[str] = []
        rebuilt_parts: list[str] = []
        cursor = 0

        for match in self.LEVEL_TOKEN_PATTERN.finditer(xml_text):
            rebuilt_parts.append(xml_text[cursor:match.start()])
            cursor = match.end()

            is_closing = bool(match.group("closing"))
            attrs = match.group("attrs") or ""
            if is_closing:
                tag_name = stack.pop() if stack else "level1"
                rebuilt_parts.append(f"</{tag_name}>")
                continue

            normalized_depth = min(len(stack) + 1, 6)
            tag_name = f"level{normalized_depth}"
            stack.append(tag_name)
            sequence += 1
            attrs = self._set_attribute(attrs, "id", f"l-{sequence}")
            rebuilt_parts.append(f"<{tag_name}{attrs}>")

        rebuilt_parts.append(xml_text[cursor:])
        return "".join(rebuilt_parts)

    @staticmethod
    def _page_attributes(page_value: str) -> tuple[str, str]:
        cleaned = page_value.strip()
        normalized_identifier = re.sub(r"[^0-9A-Za-z_-]+", "-", cleaned.lower()).strip("-") or "unknown"
        if re.fullmatch(r"\d+[A-Za-z]+", cleaned):
            return ("special", f"page-{normalized_identifier}")
        if re.fullmatch(r"[ivxlcdm]+", cleaned, re.IGNORECASE):
            return ("front", f"page-{normalized_identifier}")
        return ("normal", f"page-{normalized_identifier}")

    @staticmethod
    def _local_name(element: etree._Element) -> str:
        if not isinstance(element.tag, str):
            return ""
        if "}" in element.tag:
            return element.tag.split("}", 1)[1]
        return element.tag

    @staticmethod
    def _set_attribute(attrs: str, name: str, value: str) -> str:
        pattern = re.compile(rf'(\s{name}\s*=\s*")([^"]*)(")', re.IGNORECASE)
        if pattern.search(attrs):
            return pattern.sub(rf'\1{value}\3', attrs, count=1)
        return f'{attrs} {name}="{value}"'
