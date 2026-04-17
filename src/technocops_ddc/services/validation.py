from __future__ import annotations

from pathlib import Path

from lxml import etree

from technocops_ddc.config import DTBOOK_DTD_PATH
from technocops_ddc.models import ConversionIssue, Severity


class DTBookValidator:
    REQUIRED_TAGS = ("head", "book", "frontmatter", "bodymatter", "rearmatter")
    REQUIRED_META_NAMES = {
        "dtb:uid",
        "dc:Title",
        "dc:Creator",
        "dc:Date",
        "dc:Publisher",
        "dc:Language",
        "dc:Identifier",
        "dc:Format",
        "dc:Source",
        "dtb:producedDate",
        "dtb:sourcePublisher",
        "prod:docType",
        "prod:rawVersion",
        "prod:docHyphenate",
        "prod:producer",
        "prod:guidelineversion",
    }
    FORBIDDEN_TAGS = {"html", "body", "div", "span", "br"}

    def __init__(self, dtd_path: Path | None = None) -> None:
        self.dtd_path = dtd_path or DTBOOK_DTD_PATH

    def validate(self, xml_text: str) -> list[ConversionIssue]:
        issues: list[ConversionIssue] = []

        try:
            document = etree.fromstring(xml_text.encode("utf-8"))
        except etree.XMLSyntaxError as exc:
            return [
                ConversionIssue(
                    severity=Severity.CRITICAL,
                    message=f"Generated XML is not well-formed: {exc.msg}",
                    line=exc.lineno,
                    code="xml-not-well-formed",
                )
            ]

        issues.extend(self._validate_required_tags(document))
        issues.extend(self._validate_required_metadata(document))
        issues.extend(self._validate_forbidden_tags(document))
        issues.extend(self._validate_dtd(document))
        return issues

    def _validate_required_tags(self, document: etree._Element) -> list[ConversionIssue]:
        issues: list[ConversionIssue] = []
        if self._local_name(document.tag) != "dtbook":
            issues.append(
                ConversionIssue(
                    severity=Severity.CRITICAL,
                    message="Root element must be <dtbook>.",
                    tag=self._local_name(document.tag),
                    code="missing-dtbook-root",
                )
            )

        for tag in self.REQUIRED_TAGS:
            if self._find_first(document, tag) is None:
                issues.append(
                    ConversionIssue(
                        severity=Severity.ERROR,
                        message=f"Missing required tag <{tag}>.",
                        tag=tag,
                        code=f"missing-{tag}",
                    )
                )
        return issues

    def _validate_required_metadata(self, document: etree._Element) -> list[ConversionIssue]:
        issues: list[ConversionIssue] = []
        head = self._find_first(document, "head")
        if head is None:
            return issues

        present_names = {
            meta.get("name", "")
            for meta in head.xpath("./*[local-name()='meta']")
        }
        required_names = set(self.REQUIRED_META_NAMES)
        doc_type = self._meta_content(head, "prod:docType")
        if doc_type == "sv":
            required_names.add("prod:colophon")

        for name in sorted(required_names):
            if name not in present_names:
                issues.append(
                    ConversionIssue(
                        severity=Severity.ERROR,
                        message=f"Missing required metadata field {name}.",
                        tag="meta",
                        code="missing-meta",
                    )
                )
        return issues

    def _validate_forbidden_tags(self, document: etree._Element) -> list[ConversionIssue]:
        issues: list[ConversionIssue] = []
        for element in document.iter():
            local_name = self._local_name(element.tag)
            if local_name in self.FORBIDDEN_TAGS:
                issues.append(
                    ConversionIssue(
                        severity=Severity.ERROR,
                        message=f"Forbidden HTML tag <{local_name}> remained in output.",
                        tag=local_name,
                        line=element.sourceline,
                        code="forbidden-tag",
                    )
                )
        return issues

    def _validate_dtd(self, document: etree._Element) -> list[ConversionIssue]:
        if not self.dtd_path.exists():
            return [
                ConversionIssue(
                    severity=Severity.WARNING,
                    message="Bundled DTBook DTD file was not found. Structural validation was used instead.",
                    code="dtd-not-found",
                )
            ]

        issues: list[ConversionIssue] = []
        with self.dtd_path.open("rb") as handle:
            dtd = etree.DTD(handle)

        normalized_document = self._clone_without_namespaces(document)
        if dtd.validate(normalized_document):
            return issues

        for entry in dtd.error_log.filter_from_errors():
            issues.append(
                ConversionIssue(
                    severity=Severity.ERROR,
                    message=entry.message,
                    line=entry.line,
                    code="dtd-validation",
                )
            )
        return issues

    @staticmethod
    def _local_name(tag: str) -> str:
        if not isinstance(tag, str):
            return ""
        return etree.QName(tag).localname if tag.startswith("{") else tag

    def _find_first(self, document: etree._Element, tag_name: str) -> etree._Element | None:
        matches = document.xpath(f".//*[local-name()='{tag_name}']")
        return matches[0] if matches else None

    @staticmethod
    def _meta_content(head: etree._Element, meta_name: str) -> str:
        for meta in head.xpath("./*[local-name()='meta']"):
            if meta.get("name", "") == meta_name:
                return meta.get("content", "")
        return ""

    def _clone_without_namespaces(self, document: etree._Element) -> etree._Element:
        def clone_element(source: etree._Element) -> etree._Element:
            tag_name = self._local_name(source.tag)
            cloned_element = etree.Element(tag_name)
            cloned_element.text = source.text
            cloned_element.tail = source.tail
            for key, value in source.attrib.items():
                if isinstance(key, str) and key.startswith("{http://www.w3.org/XML/1998/namespace}"):
                    continue
                attr_name = self._local_name(key)
                cloned_element.set(attr_name, value)
            for child in source:
                cloned_element.append(clone_element(child))
            return cloned_element

        return clone_element(document)
