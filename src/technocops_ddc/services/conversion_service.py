from __future__ import annotations

import json
import shutil
from pathlib import Path

from technocops_ddc.models import ConversionIssue, ConversionResult, DTBookMetadata, InputDocument, PageRangeSelection, SavedOutput, Severity
from technocops_ddc.services.dtbook_converter import DTBookConverter
from technocops_ddc.services.validation import DTBookValidator


class ConversionService:
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
