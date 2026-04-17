from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path
from typing import Callable

from lxml import etree, html

from technocops_ddc.models import (
    ConversionIssue,
    ConversionResult,
    DTBookMetadata,
    ImageAsset,
    InputDocument,
    PageRangeSelection,
    Severity,
)

DTBOOK_NAMESPACE = "http://www.daisy.org/z3986/2005/dtbook/"
SCHEMATRON_HREF = "https://epubshowcase.dedicontest.nl/schematron/dtbook-ext.sch"
SCHEMATRON_NAMESPACE = "http://purl.oclc.org/dsdl/schematron"
BLOCK_MARKER_TAG_PATTERN = r"(?:page|pm|hsd\d*|sd|ol|ul|fig)"
INLINE_OUTPUT_TAGS = {"strong", "em", "linenum"}
INLINE_FORMATTING_TAGS = INLINE_OUTPUT_TAGS | {"b", "i", "span"}
PARAGRAPH_MERGE_PREFIXES = {
    "a",
    "an",
    "and",
    "but",
    "dat",
    "de",
    "den",
    "der",
    "die",
    "dit",
    "een",
    "en",
    "het",
    "in",
    "maar",
    "met",
    "naar",
    "of",
    "om",
    "te",
    "the",
    "to",
    "van",
    "voor",
    "want",
    "without",
    "zonder",
}

PAGE_MARKER_PATTERN = re.compile(r"(?is)<page>\s*([^<]*?)\s*</page>")
LINE_NUMBER_PATTERN = re.compile(r"(\[\s*\d+\s*\])")
SPECIAL_MARKER_VALUES = {"T1", "T2", "I", "R"}
VOID_TAGS = {"br"}
TABLE_SECTION_TAGS = {"thead", "tbody", "tfoot", "tr", "td", "th", "caption", "colgroup", "col"}
BLOCK_MARKER_PATTERN = re.compile(rf"^\s*<(?P<closing>/)?(?P<tag>{BLOCK_MARKER_TAG_PATTERN})>\s*$", re.IGNORECASE)
HEADING_MARKER_PATTERN = re.compile(r"^\s*<h(?P<level>[1-6])>\s*(?P<text>.*?)\s*</h(?P=level)>\s*$", re.IGNORECASE | re.DOTALL)
HEADING_TOKEN_PATTERN = re.compile(r"<h(?P<level>[1-6])>", re.IGNORECASE)
SIDEBAR_HEADING_PATTERN = re.compile(r"^\s*<(?P<tag>hsd\d*|sd)>\s*(?P<text>.*?)\s*$", re.IGNORECASE | re.DOTALL)
MARKUP_TOKEN_PATTERN = re.compile(rf"</?(?:{BLOCK_MARKER_TAG_PATTERN}|figure|fig|h[1-6])\s*>", re.IGNORECASE)
BRACKET_PAIRS = {"(": ")", "[": "]", "{": "}", "<": ">"}
OPENING_BRACKETS = set(BRACKET_PAIRS)
CLOSING_BRACKETS = set(BRACKET_PAIRS.values())
REVERSE_BRACKET_PAIRS = {value: key for key, value in BRACKET_PAIRS.items()}


@dataclass
class ConversionContext:
    bodymatter: etree._Element
    issues: list[ConversionIssue] = field(default_factory=list)
    image_assets: list[ImageAsset] = field(default_factory=list)
    current_file: str = ""
    current_document_path: Path | None = None
    level_stack: list[tuple[int, etree._Element]] = field(default_factory=list)
    sidebar_stack: list[etree._Element] = field(default_factory=list)
    list_stack: list[etree._Element] = field(default_factory=list)
    list_item_stack: list[etree._Element | None] = field(default_factory=list)
    active_linegroup: etree._Element | None = None
    current_page_number: str = ""
    page_counter: int = 0
    level_counter: int = 0
    page_image_counter: dict[str, int] = field(default_factory=dict)
    used_output_names: set[str] = field(default_factory=set)
    book_id: str = ""
    page_range: PageRangeSelection | None = None
    range_started: bool = True
    range_finished: bool = False
    detected_pages: set[int] = field(default_factory=set)
    range_start_found: bool = False
    range_end_found: bool = False

    @property
    def active_parent(self) -> etree._Element:
        return self.level_stack[-1][1] if self.level_stack else self.bodymatter

    @property
    def base_parent(self) -> etree._Element:
        return self.sidebar_stack[-1] if self.sidebar_stack else self.active_parent

    @property
    def current_list_item(self) -> etree._Element | None:
        return self.list_item_stack[-1] if self.list_item_stack else None

    @property
    def current_content_parent(self) -> etree._Element:
        if self.current_list_item is not None:
            return self.current_list_item
        return self.base_parent

    @property
    def capture_enabled(self) -> bool:
        if self.page_range is None:
            return True
        return self.range_started and not self.range_finished

    def open_level(self, level_number: int, line_number: int | None = None) -> etree._Element:
        while self.level_stack and self.level_stack[-1][0] >= level_number:
            self.level_stack.pop()

        if self.level_stack and level_number > self.level_stack[-1][0] + 1:
            self.issues.append(
                ConversionIssue(
                    severity=Severity.WARNING,
                    message=f"Heading level jumped from h{self.level_stack[-1][0]} to h{level_number}.",
                    file_name=self.current_file,
                    line=line_number,
                    code="heading-level-gap",
                )
            )

        parent = self.level_stack[-1][1] if self.level_stack else self.bodymatter
        self.level_counter += 1
        level_element = etree.SubElement(parent, f"level{level_number}", id=f"l-{self.level_counter}")
        self.level_stack.append((level_number, level_element))
        return level_element


class DTBookConverter:
    KNOWN_CUSTOM_TAG_WARNINGS = {
        "tag pm invalid",
        "tag page invalid",
        "tag hsd invalid",
        "tag fig invalid",
        "unexpected end tag : fig",
    }

    def convert(
        self,
        documents: list[InputDocument],
        metadata: DTBookMetadata,
        page_range: PageRangeSelection | None = None,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> ConversionResult:
        root = etree.Element(
            "dtbook",
            attrib={
                "version": "2005-3",
                "{http://www.w3.org/XML/1998/namespace}lang": metadata.language or "en",
            },
            nsmap={None: DTBOOK_NAMESPACE},
        )
        head = etree.SubElement(root, "head")
        self._populate_metadata(head, metadata)

        book = etree.SubElement(root, "book")
        frontmatter = etree.SubElement(book, "frontmatter")
        self._populate_frontmatter(frontmatter, metadata)
        bodymatter = etree.SubElement(book, "bodymatter")
        rearmatter = etree.SubElement(book, "rearmatter")

        context = ConversionContext(
            bodymatter=bodymatter,
            book_id=self._derive_book_id(metadata, documents),
            page_range=page_range,
            range_started=page_range is None or page_range.start_page <= 1,
            range_start_found=page_range is None or page_range.start_page <= 1,
        )
        total_files = max(len(documents), 1)

        for index, document in enumerate(documents, start=1):
            context.current_file = document.name
            context.current_document_path = document.path
            if progress_callback:
                progress_callback(self._progress_value(index - 1, total_files), f"Parsing {document.name}")

            raw_html = self._read_html(document.path)
            prepared_html = self._prepare_source_markup(raw_html)
            parser = html.HTMLParser(recover=True)
            parsed = html.fromstring(prepared_html, parser=parser)

            for parser_entry in parser.error_log:
                lowered_message = parser_entry.message.lower()
                if parser_entry.level_name in {"ERROR", "FATAL"} and lowered_message not in self.KNOWN_CUSTOM_TAG_WARNINGS:
                    context.issues.append(
                        ConversionIssue(
                            severity=Severity.WARNING,
                            message=parser_entry.message,
                            file_name=document.name,
                            line=parser_entry.line,
                            code="html-parser",
                        )
                    )

            source_body = parsed.find("body")
            if source_body is None:
                source_body = parsed
            self._convert_container(source_body, context)

            if progress_callback:
                progress_callback(self._progress_value(index, total_files), f"Converted {document.name}")

        self._promote_frontmatter_sections(frontmatter, bodymatter)
        self._promote_rearmatter_sections(bodymatter, rearmatter)
        self._finalize_page_range(context)
        self._cleanup_empty_elements(root)
        self._renumber_levels(root)
        self._normalize_output_tree(root)
        self._cleanup_empty_elements(root)
        xml_text = self._build_xml_text(root)
        return ConversionResult(xml_text=xml_text, issues=context.issues, image_assets=context.image_assets)

    @staticmethod
    def _progress_value(current: int, total: int) -> int:
        return int((current / total) * 100)

    @staticmethod
    def _populate_frontmatter(frontmatter: etree._Element, metadata: DTBookMetadata) -> None:
        if metadata.title.strip():
            etree.SubElement(frontmatter, "doctitle").text = metadata.title.strip()
        for author in metadata.frontmatter_authors:
            etree.SubElement(frontmatter, "docauthor").text = author

    @staticmethod
    def _populate_metadata(head: etree._Element, metadata: DTBookMetadata) -> None:
        for name, value in metadata.to_meta_pairs():
            etree.SubElement(head, "meta", name=name, content=value or "")

    @staticmethod
    def _derive_book_id(metadata: DTBookMetadata, documents: list[InputDocument]) -> str:
        candidates = [metadata.identifier, metadata.uid]
        if documents:
            candidates.append(documents[0].path.stem)
        for candidate in candidates:
            cleaned = candidate.strip()
            if not cleaned:
                continue
            first_token = cleaned.split("_", 1)[0]
            first_token = first_token.rsplit(".", 1)[0]
            if first_token:
                return re.sub(r"[^0-9A-Za-z_-]+", "", first_token)
        return "document"

    @staticmethod
    def _build_xml_text(root: etree._Element) -> str:
        xml_body = etree.tostring(root, pretty_print=False, encoding="unicode")
        xml_body = re.sub(r">\s*<", ">\n<", xml_body).strip() + "\n"
        return (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            f'<?xml-model href="{SCHEMATRON_HREF}" type="application/xml" schematypens="{SCHEMATRON_NAMESPACE}"?>\n'
            '<!DOCTYPE dtbook PUBLIC "-//NISO//DTD dtbook 2005-3//EN" "http://www.daisy.org/z3986/2005/dtbook-2005-3.dtd">\n'
            + xml_body
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

    @staticmethod
    def _prepare_source_markup(raw_html: str) -> str:
        return raw_html.replace("\r\n", "\n")

    @staticmethod
    def _parse_numeric_page(value: str) -> int | None:
        digit_match = re.search(r"\d+", value)
        if digit_match is None:
            return None
        return int(digit_match.group(0))

    def _resolve_effective_page_number(self, raw_value: str, context: ConversionContext) -> int:
        numeric_page = self._parse_numeric_page(raw_value)
        if numeric_page is not None:
            context.page_counter = numeric_page
            return numeric_page

        context.page_counter += 1
        return context.page_counter

    def _should_skip_node_outside_range(self, source_node: etree._Element, context: ConversionContext) -> bool:
        if context.page_range is None:
            return False
        if context.range_finished:
            return True
        if context.capture_enabled:
            return False
        return not self._node_contains_page_marker(source_node)

    @staticmethod
    def _node_contains_page_marker(source_node: etree._Element) -> bool:
        for node in source_node.iter():
            if isinstance(node.tag, str) and node.tag.lower().endswith("page"):
                return True
        try:
            serialized = etree.tostring(source_node, encoding="unicode", with_tail=False).lower()
        except Exception:  # noqa: BLE001
            return False
        return "<page" in serialized

    def _convert_container(
        self,
        source_parent: etree._Element,
        context: ConversionContext,
        destination_parent: etree._Element | None = None,
    ) -> None:
        if source_parent.text and source_parent.text.strip():
            self._append_text_paragraph(destination_parent or context.current_content_parent, source_parent.text, context)

        for child in source_parent:
            self._convert_block(child, context, destination_parent)
            if child.tail and child.tail.strip():
                self._append_text_paragraph(destination_parent or context.current_content_parent, child.tail, context)

    def _convert_block(
        self,
        source_node: etree._Element,
        context: ConversionContext,
        destination_parent: etree._Element | None = None,
    ) -> None:
        tag = self._tag_name(source_node)
        if not tag:
            return

        parent = destination_parent if destination_parent is not None else context.current_content_parent
        if self._should_skip_node_outside_range(source_node, context):
            return

        if tag in {"html", "body", "div"}:
            if self._convert_figure_like_container(source_node, parent, context):
                return
            self._convert_container(source_node, context, destination_parent=parent)
            return

        if tag in {"style", "script", "head", "title"}:
            return

        if tag in VOID_TAGS:
            return

        if tag == "a" and source_node.get("name"):
            self._append_inline_content(parent, source_node, context, strip_markup_tokens=True)
            return

        if tag == "page":
            self._append_pagenum(context.base_parent, "".join(source_node.itertext()).strip(), context)
            return

        if re.fullmatch(r"h[1-6]", tag):
            self._convert_heading(source_node, context)
            return

        if tag == "p":
            self._convert_paragraph(source_node, context)
            return

        if tag in {"ol", "ul"}:
            self._convert_list(source_node, context.current_content_parent, context)
            return

        if tag == "img":
            self._convert_image_group(source_node, parent, context)
            return

        if tag == "table":
            self._convert_table(source_node, parent, context)
            return

        if tag == "pm":
            self._convert_pm_block(source_node, parent, context)
            return

        if tag == "hsd":
            self._convert_sidebar(source_node, parent, context)
            return

        if tag in {"figure", "fig"} and self._convert_figure_like_container(source_node, parent, context):
            return

        context.issues.append(
            ConversionIssue(
                severity=Severity.WARNING,
                message=f"Unsupported element <{tag}> was flattened into the DTBook output.",
                file_name=context.current_file,
                line=source_node.sourceline,
                tag=tag,
                code="unsupported-element",
            )
        )
        self._convert_container(source_node, context, destination_parent=parent)

    def _convert_paragraph(self, source_node: etree._Element, context: ConversionContext) -> None:
        paragraph_text = self._normalized_paragraph_text(source_node)
        heading_match = HEADING_MARKER_PATTERN.match(paragraph_text)
        if heading_match:
            self._convert_heading_from_paragraph(source_node, int(heading_match.group("level")), context)
            return

        block_match = BLOCK_MARKER_PATTERN.match(paragraph_text)
        if block_match:
            self._handle_block_marker(context, block_match.group("tag").lower(), bool(block_match.group("closing")))
            return

        if context.active_linegroup is not None:
            line = etree.SubElement(context.active_linegroup, "line")
            self._append_inline_content(line, source_node, context, pm_mode=True, strip_markup_tokens=True)
            if not self._has_meaningful_content(line):
                context.active_linegroup.remove(line)
            return

        if context.list_stack:
            list_item = etree.SubElement(context.list_stack[-1], "li")
            context.list_item_stack[-1] = list_item
            self._append_inline_content(list_item, source_node, context, strip_markup_tokens=True)
            if not self._has_meaningful_content(list_item):
                context.list_stack[-1].remove(list_item)
                context.list_item_stack[-1] = None
            return

        paragraph = etree.SubElement(context.current_content_parent, "p")
        self._append_inline_content(paragraph, source_node, context, strip_markup_tokens=True)
        if not self._has_meaningful_content(paragraph):
            context.current_content_parent.remove(paragraph)

    def _handle_block_marker(self, context: ConversionContext, tag: str, is_closing: bool) -> None:
        normalized_tag = tag.lower()
        if normalized_tag.startswith("hsd"):
            normalized_tag = "sd"

        if normalized_tag == "page" and not is_closing:
            self._append_pagenum(context.base_parent, "", context)
            return

        if normalized_tag == "pm":
            if is_closing:
                context.active_linegroup = None
            else:
                context.active_linegroup = etree.SubElement(context.current_content_parent, "linegroup")
            return

        if normalized_tag == "sd":
            if is_closing:
                if context.sidebar_stack:
                    context.sidebar_stack.pop()
            else:
                self._open_sidebar(context, move_previous_heading=True)
            return

        if normalized_tag in {"ol", "ul"}:
            if is_closing:
                if context.list_stack:
                    context.list_stack.pop()
                    context.list_item_stack.pop()
            else:
                attributes = {"type": "pl"}
                if normalized_tag == "ul":
                    attributes["class"] = "ul-nobullets"
                elif self._is_within_print_toc(context.base_parent):
                    attributes["class"] = "toc"
                parent = context.current_list_item if context.current_list_item is not None else context.base_parent
                new_list = etree.SubElement(parent, "list", **attributes)
                context.list_stack.append(new_list)
                context.list_item_stack.append(None)

    @staticmethod
    def _close_open_lists(context: ConversionContext) -> None:
        context.list_stack.clear()
        context.list_item_stack.clear()

    def _convert_heading(self, source_node: etree._Element, context: ConversionContext) -> None:
        self._close_open_lists(context)
        heading_text = self._normalized_paragraph_text(source_node)
        block_match = BLOCK_MARKER_PATTERN.match(heading_text)
        if block_match:
            self._handle_block_marker(context, block_match.group("tag").lower(), bool(block_match.group("closing")))
            return

        if SIDEBAR_HEADING_PATTERN.match(heading_text):
            self._convert_sidebar_heading(source_node, context)
            return

        level_number = self._resolve_heading_level(source_node, heading_text)
        level = context.open_level(level_number, source_node.sourceline)
        self._apply_level_semantics(level, heading_text, level_number)
        heading = etree.SubElement(level, f"h{level_number}")
        self._append_heading_text(heading, source_node)

    def _convert_heading_from_paragraph(
        self,
        source_node: etree._Element,
        level_number: int,
        context: ConversionContext,
    ) -> None:
        self._close_open_lists(context)
        heading_text = self._normalized_paragraph_text(source_node)
        if SIDEBAR_HEADING_PATTERN.match(heading_text):
            self._convert_sidebar_heading(source_node, context)
            return

        level = context.open_level(level_number, source_node.sourceline)
        self._apply_level_semantics(level, heading_text, level_number)
        heading = etree.SubElement(level, f"h{level_number}")
        self._append_heading_text(heading, source_node)

    def _resolve_heading_level(self, source_node: etree._Element, normalized_text: str) -> int:
        embedded_heading = HEADING_MARKER_PATTERN.match(normalized_text)
        if embedded_heading:
            return int(embedded_heading.group("level"))

        embedded_heading_token = HEADING_TOKEN_PATTERN.search(normalized_text)
        if embedded_heading_token:
            return int(embedded_heading_token.group("level"))

        return int(self._tag_name(source_node)[1])

    def _apply_level_semantics(self, level: etree._Element, heading_text: str, level_number: int) -> None:
        clean_heading = self._strip_markup_tokens(heading_text).lower()
        if level_number == 1 and clean_heading == "inhoud":
            level.set("class", "print_toc")
        elif level_number == 1 and re.match(r"^\d+[ .]", clean_heading):
            level.set("class", "chapter")

    def _convert_list(self, source_node: etree._Element, parent: etree._Element, context: ConversionContext) -> None:
        tag = self._tag_name(source_node)
        attributes = {"type": "pl"}
        if tag == "ul":
            attributes["class"] = self._list_class_attribute(source_node, parent)
        elif self._is_within_print_toc(parent):
            attributes["class"] = "toc"

        list_element = etree.SubElement(parent, "list", **attributes)
        last_item: etree._Element | None = None

        for child in source_node:
            child_tag = self._tag_name(child)
            if child_tag in {"li", "p"}:
                last_item = etree.SubElement(list_element, "li")
                self._append_list_item_content(last_item, child, context)
                if not self._has_meaningful_content(last_item):
                    list_element.remove(last_item)
                    last_item = None
            elif child_tag in {"ol", "ul"} and last_item is not None:
                self._convert_list(child, last_item, context)
            else:
                last_item = etree.SubElement(list_element, "li")
                self._append_inline_content(last_item, child, context, strip_markup_tokens=True)

        if not self._has_meaningful_content(list_element):
            parent.remove(list_element)

    def _list_class_attribute(self, source_node: etree._Element, parent: etree._Element) -> str:
        class_tokens = [token for token in (source_node.get("class") or "").split() if token]
        class_tokens.append("ul-nobullets")
        if self._is_within_print_toc(parent):
            class_tokens.append("toc")

        unique_tokens: list[str] = []
        for token in class_tokens:
            if token not in unique_tokens:
                unique_tokens.append(token)
        return " ".join(unique_tokens)

    def _append_list_item_content(self, target_item: etree._Element, source_item: etree._Element, context: ConversionContext) -> None:
        if source_item.text:
            self._append_text_fragments(target_item, source_item.text, context, strip_markup_tokens=True)

        for child in source_item:
            tag = self._tag_name(child)
            if tag in {"ol", "ul"}:
                self._convert_list(child, target_item, context)
            elif tag == "table":
                self._convert_table(child, target_item, context)
            elif tag == "img":
                self._convert_image_group(child, target_item, context)
            elif tag == "p":
                self._append_inline_content(target_item, child, context, strip_markup_tokens=True)
            elif tag == "pm":
                self._convert_pm_block(child, target_item, context)
            elif tag == "hsd":
                self._convert_sidebar(child, target_item, context)
            else:
                self._append_inline_node(target_item, child, context, strip_markup_tokens=True)

            if child.tail:
                self._append_text_fragments(target_item, child.tail, context, strip_markup_tokens=True)

    def _convert_image_group(self, source_node: etree._Element, parent: etree._Element, context: ConversionContext) -> etree._Element:
        image_group = etree.SubElement(parent, "imggroup")
        raw_source = (source_node.get("src") or "").strip()
        source_path = self._resolve_image_source_path(raw_source, context)
        output_name = self._build_output_image_name(source_path, raw_source, context)

        if source_path is not None and source_path.exists():
            context.image_assets.append(
                ImageAsset(
                    source_path=source_path,
                    output_name=output_name,
                    original_reference=raw_source,
                )
            )
        else:
            context.issues.append(
                ConversionIssue(
                    severity=Severity.WARNING,
                    message=f"Referenced image could not be found: {raw_source or '[missing src]'}",
                    file_name=context.current_file,
                    code="missing-image",
                    tag="img",
                )
            )

        etree.SubElement(image_group, "img", src=f"img/{output_name}", alt="afbeelding")
        return image_group

    def _resolve_image_source_path(self, raw_source: str, context: ConversionContext) -> Path | None:
        if not raw_source:
            return None
        candidate = Path(raw_source)
        if candidate.is_absolute():
            return candidate
        if context.current_document_path is None:
            return None
        return (context.current_document_path.parent / candidate).resolve()

    def _build_output_image_name(self, source_path: Path | None, raw_source: str, context: ConversionContext) -> str:
        suffix = ".jpg"
        if source_path is not None and source_path.suffix:
            suffix = source_path.suffix.lower()
        elif raw_source:
            raw_suffix = Path(raw_source).suffix.lower()
            if raw_suffix:
                suffix = raw_suffix

        if not context.image_assets and context.current_page_number in {"", "1"}:
            return self._ensure_unique_output_name("cover", suffix, context)

        if context.current_page_number:
            page_digits = re.sub(r"\D+", "", context.current_page_number)
            if page_digits:
                page_key = f"p{int(page_digits):03d}"
            else:
                page_key = f"p{re.sub(r'[^0-9A-Za-z]+', '', context.current_page_number.lower()) or 'x'}"
            image_index = context.page_image_counter.get(page_key, 0) + 1
            context.page_image_counter[page_key] = image_index
            base_name = f"{context.book_id}_{page_key}-{image_index:02d}"
            return self._ensure_unique_output_name(base_name, suffix, context)

        fallback_index = len(context.image_assets) + 1
        base_name = f"{context.book_id}_img-{fallback_index:02d}"
        return self._ensure_unique_output_name(base_name, suffix, context)

    @staticmethod
    def _ensure_unique_output_name(base_name: str, suffix: str, context: ConversionContext) -> str:
        candidate = f"{base_name}{suffix}"
        attempt = 1
        while candidate in context.used_output_names:
            attempt += 1
            candidate = f"{base_name}-{attempt:02d}{suffix}"
        context.used_output_names.add(candidate)
        return candidate

    def _promote_frontmatter_sections(self, frontmatter: etree._Element, bodymatter: etree._Element) -> None:
        body_children = list(bodymatter)
        first_chapter_index = next(
            (
                index
                for index, child in enumerate(body_children)
                if self._tag_name(child) == "level1" and child.get("class") == "chapter"
            ),
            None,
        )
        if first_chapter_index in {None, 0}:
            return

        leading_nodes = body_children[:first_chapter_index]
        for child in leading_nodes:
            bodymatter.remove(child)

        staged_frontmatter_nodes: list[etree._Element] = []
        buffered_nodes: list[etree._Element] = []

        for child in leading_nodes:
            if self._tag_name(child) == "level1":
                staged_frontmatter_nodes.extend(self._wrap_frontmatter_nodes(buffered_nodes))
                buffered_nodes = []

                if child.get("class") == "print_toc":
                    self._merge_leading_toc_seed_nodes(child, staged_frontmatter_nodes)
                    self._convert_toc_tables_in_subtree(child)
                staged_frontmatter_nodes.append(child)
                continue

            buffered_nodes.append(child)

        staged_frontmatter_nodes.extend(self._wrap_frontmatter_nodes(buffered_nodes))

        for child in staged_frontmatter_nodes:
            frontmatter.append(child)

        self._merge_standalone_toc_page_marker(frontmatter)

    def _merge_leading_toc_seed_nodes(
        self,
        toc_level: etree._Element,
        staged_frontmatter_nodes: list[etree._Element],
    ) -> None:
        if not staged_frontmatter_nodes:
            return

        toc_seed_index = next(
            (
                index
                for index in range(len(staged_frontmatter_nodes) - 1, -1, -1)
                if self._tag_name(staged_frontmatter_nodes[index]) == "level1"
                and any(
                    self._looks_like_toc_table(child)
                    for child in staged_frontmatter_nodes[index]
                    if self._tag_name(child) == "table"
                )
            ),
            None,
        )
        if toc_seed_index is None:
            return

        toc_seed_level = staged_frontmatter_nodes.pop(toc_seed_index)
        toc_seed_children = list(toc_seed_level)
        first_toc_child_index = next(
            (
                index
                for index, child in enumerate(toc_seed_children)
                if self._tag_name(child) == "table" and self._looks_like_toc_table(child)
            ),
            None,
        )
        if first_toc_child_index is None:
            staged_frontmatter_nodes.insert(toc_seed_index, toc_seed_level)
            return

        kept_children = toc_seed_children[:first_toc_child_index]
        moved_children = toc_seed_children[first_toc_child_index:]
        for child in toc_seed_children:
            toc_seed_level.remove(child)
        for child in kept_children:
            toc_seed_level.append(child)
        next_seed_index = toc_seed_index
        if self._has_meaningful_content(toc_seed_level):
            staged_frontmatter_nodes.insert(toc_seed_index, toc_seed_level)
            next_seed_index += 1

        nodes_before_heading: list[etree._Element] = []
        nodes_after_heading: list[etree._Element] = []

        while next_seed_index < len(staged_frontmatter_nodes):
            candidate_level = staged_frontmatter_nodes[next_seed_index]
            if not self._level_contains_only_pagenums(candidate_level):
                break
            staged_frontmatter_nodes.pop(next_seed_index)
            for child in list(candidate_level):
                candidate_level.remove(child)
                nodes_before_heading.append(child)

        for child in moved_children:
            if self._tag_name(child) == "table" and self._looks_like_toc_table(child):
                toc_list = self._build_toc_list_from_table(child)
                if toc_list is not None:
                    nodes_after_heading.append(toc_list)
                continue
            nodes_before_heading.append(child)

        heading_index = next(
            (
                index
                for index, child in enumerate(toc_level)
                if self._tag_name(child) in {"h1", "h2", "h3", "h4", "h5", "h6"}
            ),
            0,
        )
        insert_at = 0
        for child in nodes_before_heading:
            toc_level.insert(insert_at, child)
            insert_at += 1

        insert_after_heading = min(len(toc_level), heading_index + 1 + len(nodes_before_heading))
        for offset, child in enumerate(nodes_after_heading):
            toc_level.insert(insert_after_heading + offset, child)

    def _wrap_frontmatter_nodes(self, nodes: list[etree._Element]) -> list[etree._Element]:
        if not nodes:
            return []

        wrapped_levels: list[etree._Element] = []
        current_level: etree._Element | None = None

        for node in nodes:
            if self._tag_name(node) == "pagenum" and current_level is not None and len(current_level):
                self._apply_frontmatter_level_semantics(current_level)
                wrapped_levels.append(current_level)
                current_level = None

            if current_level is None:
                current_level = etree.Element("level1")

            current_level.append(node)

        if current_level is not None and len(current_level):
            self._apply_frontmatter_level_semantics(current_level)
            wrapped_levels.append(current_level)

        return wrapped_levels

    def _apply_frontmatter_level_semantics(self, level: etree._Element) -> None:
        visible_text = " ".join(part.strip() for part in level.itertext() if part.strip()).lower()
        if any(token in visible_text for token in {"methodeconcept/redactie", "met dank aan", "auteurs"}):
            level.set("class", "colophon")

    def _merge_standalone_toc_page_marker(self, frontmatter: etree._Element) -> None:
        children = list(frontmatter)
        for index, child in enumerate(children):
            if self._tag_name(child) != "level1" or child.get("class") != "print_toc":
                continue
            if index == 0:
                return
            previous_level = children[index - 1]
            if self._tag_name(previous_level) != "level1" or not self._level_contains_only_pagenums(previous_level):
                return
            page_markers = list(previous_level)
            for marker in reversed(page_markers):
                previous_level.remove(marker)
                child.insert(0, marker)
            frontmatter.remove(previous_level)
            return

    def _promote_rearmatter_sections(self, bodymatter: etree._Element, rearmatter: etree._Element) -> None:
        body_children = list(bodymatter)
        start_index = next(
            (
                index
                for index, child in enumerate(body_children)
                if self._tag_name(child) == "level1"
                and self._level_heading_text(child).strip().lower() == "verantwoording illustraties"
            ),
            None,
        )
        if start_index is None:
            return

        moving_nodes = body_children[start_index:]
        for child in moving_nodes:
            bodymatter.remove(child)
            rearmatter.append(child)

        for child in moving_nodes:
            if self._tag_name(child) == "level1" and self._level_heading_text(child).strip().lower() == "verantwoording illustraties":
                self._normalize_illustration_credit_section(child)

    def _normalize_illustration_credit_section(self, level: etree._Element) -> None:
        children = list(level)
        heading_seen = False
        intro_seen = False
        credit_paragraphs: list[etree._Element] = []

        for child in children:
            tag = self._tag_name(child)
            if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                heading_seen = True
                continue
            if not heading_seen:
                continue
            if tag == "p" and not intro_seen:
                intro_seen = True
                continue
            if tag == "pagenum":
                break
            if tag == "p" and self._looks_like_credit_line(child):
                credit_paragraphs.append(child)
                continue
            if credit_paragraphs:
                break

        if not credit_paragraphs:
            return

        insert_index = level.index(credit_paragraphs[0])
        credit_list = etree.Element("list", type="pl")
        credit_list.set("class", "ul-nobullets")
        for paragraph in credit_paragraphs:
            text_value = self._strip_markup_tokens(" ".join(part.strip() for part in paragraph.itertext() if part.strip()))
            list_item = etree.SubElement(credit_list, "li")
            self._append_inline_content(list_item, paragraph, ConversionContext(bodymatter=level), strip_markup_tokens=True)
            if not self._has_meaningful_content(list_item):
                list_item.text = text_value
            level.remove(paragraph)

        level.insert(insert_index, credit_list)

    def _level_heading_text(self, level: etree._Element) -> str:
        for child in level:
            if self._tag_name(child) in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                return self._strip_markup_tokens(" ".join(part.strip() for part in child.itertext() if part.strip()))
        return ""

    def _looks_like_credit_line(self, paragraph: etree._Element) -> bool:
        text = self._strip_markup_tokens(" ".join(part.strip() for part in paragraph.itertext() if part.strip()))
        if not text:
            return False
        return bool(
            re.match(r"^(?:\d+|\([a-z]\)|©|ISBN\b)", text, re.IGNORECASE)
            or " / " in text
            or "Shutterstock" in text
            or "ComicHouse" in text
        )

    def _level_contains_only_pagenums(self, level: etree._Element) -> bool:
        children = list(level)
        if not children:
            return False
        return all(self._tag_name(child) == "pagenum" for child in children)

    def _convert_toc_tables_in_subtree(self, container: etree._Element) -> None:
        for table in list(container.iterfind(".//table")):
            if not self._looks_like_toc_table(table):
                continue
            toc_list = self._build_toc_list_from_table(table)
            if toc_list is None:
                continue
            parent = table.getparent()
            if parent is None:
                continue
            insertion_index = parent.index(table)
            parent.remove(table)
            parent.insert(insertion_index, toc_list)

    def _looks_like_toc_table(self, table: etree._Element) -> bool:
        rows = [child for child in table if self._tag_name(child) == "tr"]
        if len(rows) < 3:
            return False

        header_cells = self._table_row_cells(rows[0])
        if len(header_cells) < 3:
            return False

        chapter_titles = [self._table_cell_primary_text(cell) for cell in header_cells[1:]]
        if not any(re.match(r"^\d+[\s.]", title) for title in chapter_titles):
            return False

        section_labels = [
            self._table_cell_primary_text(self._table_row_cells(row)[0])
            for row in rows[1:]
            if self._table_row_cells(row)
        ]
        uppercase_labels = [label for label in section_labels if label and label == label.upper()]
        return len(uppercase_labels) >= 2

    def _build_toc_list_from_table(self, table: etree._Element) -> etree._Element | None:
        rows = [child for child in table if self._tag_name(child) == "tr"]
        if len(rows) < 2:
            return None

        header_cells = self._table_row_cells(rows[0])
        if len(header_cells) < 3:
            return None

        top_level_list = etree.Element("list", type="pl")
        top_level_list.set("class", "toc")

        for column_index in range(1, len(header_cells)):
            chapter_title = self._table_cell_primary_text(header_cells[column_index])
            if not chapter_title:
                continue

            chapter_item = etree.SubElement(top_level_list, "li")
            chapter_label = etree.SubElement(chapter_item, "strong")
            chapter_label.text = chapter_title

            chapter_sections = etree.SubElement(chapter_item, "list", type="pl")
            chapter_sections.set("class", "toc")

            for row in rows[1:]:
                cells = self._table_row_cells(row)
                if len(cells) <= column_index:
                    continue

                section_title = self._table_cell_primary_text(cells[0])
                cell_entries = self._table_cell_entries(cells[column_index])
                if not section_title and not cell_entries:
                    continue

                section_item = etree.SubElement(chapter_sections, "li")
                if section_title:
                    section_item.text = section_title

                if cell_entries:
                    section_list = etree.SubElement(section_item, "list", type="pl")
                    section_list.set("class", "toc")
                    for entry in cell_entries:
                        entry_item = etree.SubElement(section_list, "li")
                        self._append_toc_entry(entry_item, entry)

            if not self._has_meaningful_content(chapter_sections):
                chapter_item.remove(chapter_sections)

        return top_level_list if self._has_meaningful_content(top_level_list) else None

    @staticmethod
    def _table_row_cells(row: etree._Element) -> list[etree._Element]:
        cells: list[etree._Element] = []
        for child in row:
            if not isinstance(child.tag, str):
                continue
            local_name = child.tag.split("}", 1)[-1].lower()
            if local_name in {"td", "th"}:
                cells.append(child)
        return cells

    def _table_cell_primary_text(self, cell: etree._Element) -> str:
        return self._strip_markup_tokens(" ".join(part.strip() for part in cell.itertext() if part.strip()))

    def _table_cell_entries(self, cell: etree._Element) -> list[str]:
        paragraph_texts = [
            self._strip_markup_tokens(" ".join(part.strip() for part in paragraph.itertext() if part.strip()))
            for paragraph in cell
            if self._tag_name(paragraph) == "p"
        ]
        paragraph_texts = [text for text in paragraph_texts if text]
        if paragraph_texts:
            return paragraph_texts

        fallback_text = self._table_cell_primary_text(cell)
        return [fallback_text] if fallback_text else []

    def _append_toc_entry(self, target: etree._Element, value: str) -> None:
        entry_match = re.match(r"^(?P<label>[A-Za-z])\s+(?P<title>.+?)(?:\s+(?P<page>\d+))?$", value)
        if entry_match:
            strong = etree.SubElement(target, "strong")
            strong.text = f"{entry_match.group('label')} "
            title_text = entry_match.group("title").strip()
            page_text = entry_match.group("page")
            suffix = f" {page_text}" if page_text else ""
            strong.tail = f"{title_text}{suffix}"
            return

        target.text = value

    def _renumber_levels(self, root: etree._Element) -> None:
        counter = 0
        for element in root.iter():
            if re.fullmatch(r"level[1-6]", self._tag_name(element)):
                counter += 1
                element.set("id", f"l-{counter}")

    def _finalize_page_range(self, context: ConversionContext) -> None:
        page_range = context.page_range
        if page_range is None:
            return

        if not context.detected_pages:
            context.issues.append(
                ConversionIssue(
                    severity=Severity.WARNING,
                    message=f"{page_range.label} was requested, but no page markers were detected in the source HTML.",
                    code="page-range-no-markers",
                )
            )
            return

        highest_page = max(context.detected_pages)
        if page_range.start_page > highest_page:
            context.issues.append(
                ConversionIssue(
                    severity=Severity.WARNING,
                    message=f"{page_range.label} starts after the highest detected page ({highest_page}). Output is empty for the requested range.",
                    code="page-range-start-exceeds-document",
                )
            )
            return

        if not context.range_start_found:
            context.issues.append(
                ConversionIssue(
                    severity=Severity.WARNING,
                    message=f"Start page {page_range.start_page} was not found. Conversion used the nearest available content after the requested boundary.",
                    code="page-range-start-missing",
                )
            )

        if page_range.end_page > highest_page:
            context.issues.append(
                ConversionIssue(
                    severity=Severity.WARNING,
                    message=f"End page {page_range.end_page} exceeds the highest detected page ({highest_page}). Conversion stopped at the final available page.",
                    code="page-range-end-exceeds-document",
                )
            )

    def _convert_table(self, source_node: etree._Element, parent: etree._Element, context: ConversionContext) -> None:
        table = etree.SubElement(parent, "table")
        self._copy_table_children(source_node, table, context)
        if not self._has_meaningful_content(table):
            parent.remove(table)

    def _copy_table_children(self, source_node: etree._Element, target_node: etree._Element, context: ConversionContext) -> None:
        if source_node.text:
            self._append_text_fragments(target_node, source_node.text, context, strip_markup_tokens=True)

        for child in source_node:
            tag = self._tag_name(child)
            if tag not in TABLE_SECTION_TAGS:
                self._append_inline_content(target_node, child, context, strip_markup_tokens=True)
                continue

            cleaned_attributes = {
                key: value
                for key, value in child.attrib.items()
                if self._is_allowed_table_attribute(tag, key, value)
            }
            target_child = etree.SubElement(target_node, tag, **cleaned_attributes)
            if tag in {"td", "th"}:
                self._copy_table_cell_content(child, target_child, context)
            else:
                self._copy_table_children(child, target_child, context)

            if child.tail:
                self._append_text_fragments(target_node, child.tail, context, strip_markup_tokens=True)

    @staticmethod
    def _is_allowed_table_attribute(tag: str, key: str, value: str) -> bool:
        lowered_key = key.lower()
        lowered_value = value.lower()
        if tag == "table" and lowered_key == "border":
            return False
        if tag in {"td", "th"} and lowered_key == "style" and "vertical-align" in lowered_value:
            return False
        return True

    def _copy_table_cell_content(self, source_node: etree._Element, target_node: etree._Element, context: ConversionContext) -> None:
        if source_node.text:
            self._append_text_fragments(target_node, source_node.text, context, strip_markup_tokens=True)

        for child in source_node:
            tag = self._tag_name(child)
            if tag == "p":
                if self._has_meaningful_content(target_node):
                    self._append_text_to_element(target_node, " ")
                self._append_inline_content(target_node, child, context, strip_markup_tokens=True)
            elif tag in {"ol", "ul"}:
                self._convert_list(child, target_node, context)
            elif tag == "img":
                self._convert_image_group(child, target_node, context)
            else:
                self._append_inline_node(target_node, child, context, strip_markup_tokens=True)

            if child.tail:
                self._append_text_fragments(target_node, child.tail, context, strip_markup_tokens=True)

    def _convert_pm_block(self, source_node: etree._Element, parent: etree._Element, context: ConversionContext) -> None:
        original_linegroup = context.active_linegroup
        line_group = etree.SubElement(parent, "linegroup")
        context.active_linegroup = line_group

        if source_node.text and source_node.text.strip():
            self._append_pm_line(line_group, source_node.text, context)

        for child in source_node:
            tag = self._tag_name(child)
            if tag == "p":
                line = etree.SubElement(line_group, "line")
                self._append_inline_content(line, child, context, pm_mode=True, strip_markup_tokens=True)
                if not self._has_meaningful_content(line):
                    line_group.remove(line)
            else:
                line = etree.SubElement(line_group, "line")
                self._append_inline_node(line, child, context, pm_mode=True, strip_markup_tokens=True)
                if child.tail:
                    self._append_text_fragments(line, child.tail, context, pm_mode=True, strip_markup_tokens=True)
                if not self._has_meaningful_content(line):
                    line_group.remove(line)

        context.active_linegroup = original_linegroup
        if not self._has_meaningful_content(line_group):
            parent.remove(line_group)

    def _append_pm_line(self, parent: etree._Element, text: str, context: ConversionContext) -> None:
        line = etree.SubElement(parent, "line")
        self._append_text_fragments(line, text, context, pm_mode=True, strip_markup_tokens=True)
        if not self._has_meaningful_content(line):
            parent.remove(line)

    def _convert_sidebar(self, source_node: etree._Element, parent: etree._Element, context: ConversionContext) -> None:
        sidebar = etree.SubElement(parent, "sidebar", render="required")
        context.sidebar_stack.append(sidebar)
        self._convert_container(source_node, context, destination_parent=sidebar)
        context.sidebar_stack.pop()
        if not self._has_meaningful_content(sidebar):
            parent.remove(sidebar)

    def _convert_sidebar_heading(self, source_node: etree._Element, context: ConversionContext) -> None:
        sidebar = self._open_sidebar(context)
        heading = etree.SubElement(sidebar, "hd")
        heading.text = self._strip_markup_tokens(self._normalized_paragraph_text(source_node))
        if not self._has_meaningful_content(heading):
            sidebar.remove(heading)

    def _open_sidebar(self, context: ConversionContext, move_previous_heading: bool = False) -> etree._Element:
        parent = context.current_content_parent
        heading_text = ""
        if move_previous_heading and len(parent):
            previous_sibling = parent[-1]
            if self._tag_name(previous_sibling) in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                heading_text = self._strip_markup_tokens("".join(previous_sibling.itertext()))
                parent.remove(previous_sibling)

        sidebar = etree.SubElement(parent, "sidebar", render="required")
        if heading_text:
            etree.SubElement(sidebar, "hd").text = heading_text
        context.sidebar_stack.append(sidebar)
        return sidebar

    def _convert_figure_like_container(
        self,
        source_node: etree._Element,
        parent: etree._Element,
        context: ConversionContext,
    ) -> bool:
        direct_children = [child for child in source_node if self._tag_name(child)]
        image_nodes = [child for child in direct_children if self._tag_name(child) == "img"]
        if len(image_nodes) != 1:
            return False

        caption_source = next(
            (
                child
                for child in direct_children
                if self._tag_name(child) in {"figcaption", "caption", "p"} and self._is_caption_candidate(child)
            ),
            None,
        )

        image_group = self._convert_image_group(image_nodes[0], parent, context)
        if caption_source is not None:
            caption = etree.SubElement(image_group, "caption")
            paragraph = etree.SubElement(caption, "p")
            emphasis = etree.SubElement(paragraph, "em")
            self._append_inline_content(emphasis, caption_source, context, strip_markup_tokens=True)
            if not self._has_meaningful_content(emphasis):
                paragraph.remove(emphasis)
        return True

    def _append_inline_content(
        self,
        target: etree._Element,
        source_node: etree._Element,
        context: ConversionContext,
        pm_mode: bool = False,
        strip_markup_tokens: bool = False,
    ) -> None:
        if source_node.text:
            self._append_text_fragments(target, source_node.text, context, pm_mode=pm_mode, strip_markup_tokens=strip_markup_tokens)

        for child in source_node:
            self._append_inline_node(target, child, context, pm_mode=pm_mode, strip_markup_tokens=strip_markup_tokens)
            if child.tail:
                self._append_text_fragments(target, child.tail, context, pm_mode=pm_mode, strip_markup_tokens=strip_markup_tokens)

    def _append_inline_node(
        self,
        target: etree._Element,
        source_node: etree._Element,
        context: ConversionContext,
        pm_mode: bool = False,
        strip_markup_tokens: bool = False,
    ) -> None:
        tag = self._tag_name(source_node)
        if not tag:
            return

        if tag in VOID_TAGS:
            return

        if tag == "a" and source_node.get("name"):
            self._append_inline_content(target, source_node, context, pm_mode=pm_mode, strip_markup_tokens=True)
            return

        if tag == "page":
            self._append_pagenum(target, "".join(source_node.itertext()).strip(), context)
            return

        if tag in {"strong", "b"} or self._is_bold_span(source_node):
            special_marker = self._extract_special_marker(source_node)
            if special_marker:
                self._append_text_fragments(target, f"({special_marker})", context, pm_mode=pm_mode)
                return

            strong = etree.SubElement(target, "strong")
            self._append_inline_content(strong, source_node, context, pm_mode=pm_mode, strip_markup_tokens=strip_markup_tokens)
            if not self._has_meaningful_content(strong):
                target.remove(strong)
            return

        if tag in {"em", "i"} or self._is_italic_span(source_node):
            emphasis = etree.SubElement(target, "em")
            self._append_inline_content(emphasis, source_node, context, pm_mode=pm_mode, strip_markup_tokens=strip_markup_tokens)
            if not self._has_meaningful_content(emphasis):
                target.remove(emphasis)
            return

        if tag == "img":
            self._convert_image_group(source_node, target, context)
            return

        if tag == "span":
            self._append_inline_content(target, source_node, context, pm_mode=pm_mode, strip_markup_tokens=strip_markup_tokens)
            return

        self._append_inline_content(target, source_node, context, pm_mode=pm_mode, strip_markup_tokens=strip_markup_tokens)

    def _append_text_fragments(
        self,
        target: etree._Element,
        text: str,
        context: ConversionContext,
        pm_mode: bool = False,
        strip_markup_tokens: bool = False,
    ) -> None:
        if not text:
            return

        decoded_text = unescape(text).replace("\xa0", " ")
        if strip_markup_tokens:
            decoded_text = MARKUP_TOKEN_PATTERN.sub("", decoded_text)

        last_index = 0

        for match in PAGE_MARKER_PATTERN.finditer(decoded_text):
            self._append_text_segment(target, decoded_text[last_index:match.start()], context)
            self._append_pagenum(target, match.group(1).strip(), context)
            last_index = match.end()

        remaining_text = decoded_text[last_index:]
        if pm_mode:
            pm_index = 0
            for match in LINE_NUMBER_PATTERN.finditer(remaining_text):
                self._append_text_segment(target, remaining_text[pm_index:match.start()], context)
                line_number = match.group(1).strip("[] ").strip()
                self._append_linenum(target, line_number, context)
                pm_index = match.end()
            self._append_text_segment(target, remaining_text[pm_index:], context)
            return

        self._append_text_segment(target, remaining_text, context)

    @staticmethod
    def _append_text_segment(target: etree._Element, text: str, context: ConversionContext) -> None:
        if not context.capture_enabled:
            return
        normalized = re.sub(r"[ \t\f\v]+", " ", text.replace("\n", " "))
        normalized = re.sub(r"\s{2,}", " ", normalized)
        if not normalized.strip():
            return
        if len(target):
            target[-1].tail = f"{target[-1].tail or ''}{normalized}"
        else:
            target.text = f"{target.text or ''}{normalized}"

    def _append_pagenum(self, target: etree._Element, value: str, context: ConversionContext) -> None:
        cleaned = value.strip()
        effective_page_number = self._resolve_effective_page_number(cleaned, context)
        if not cleaned:
            cleaned = str(effective_page_number)

        context.detected_pages.add(effective_page_number)

        if context.page_range is not None:
            if effective_page_number < context.page_range.start_page:
                context.range_started = False
                context.current_page_number = cleaned
                return
            if effective_page_number > context.page_range.end_page:
                context.range_finished = True
                context.range_started = False
                context.current_page_number = cleaned
                return
            context.range_started = True
            context.range_start_found = True
            if effective_page_number == context.page_range.end_page:
                context.range_end_found = True

        context.current_page_number = cleaned
        page_id = re.sub(r"[^0-9A-Za-z_-]+", "-", cleaned).strip("-") or "unknown"
        page_number = etree.SubElement(target, "pagenum", page="normal", id=f"page-{page_id}")
        page_number.text = cleaned

    def _append_heading_text(self, target: etree._Element, source_node: etree._Element) -> None:
        heading_text = " ".join(part.strip() for part in source_node.itertext() if part.strip())
        target.text = self._strip_markup_tokens(heading_text)

    @staticmethod
    def _append_text_to_element(target: etree._Element, text: str) -> None:
        if not text:
            return
        if len(target):
            target[-1].tail = f"{target[-1].tail or ''}{text}"
        else:
            target.text = f"{target.text or ''}{text}"

    @staticmethod
    def _append_linenum(target: etree._Element, value: str, context: ConversionContext) -> None:
        if not context.capture_enabled:
            return
        cleaned = value.strip()
        if not cleaned:
            return
        line_number = etree.SubElement(target, "linenum")
        line_number.text = f"({cleaned})"

    def _append_text_paragraph(self, parent: etree._Element, text: str, context: ConversionContext) -> None:
        cleaned_text = MARKUP_TOKEN_PATTERN.sub("", unescape(text))
        if not cleaned_text.strip():
            return
        paragraph = etree.SubElement(parent, "p")
        self._append_text_fragments(paragraph, cleaned_text, context, strip_markup_tokens=True)
        if not self._has_meaningful_content(paragraph):
            parent.remove(paragraph)

    @staticmethod
    def _has_meaningful_content(element: etree._Element) -> bool:
        if element.attrib and element.tag == "meta":
            return True
        text_content = "".join(part.strip() for part in element.itertext())
        return bool(text_content or len(element))

    @staticmethod
    def _tag_name(node: etree._Element) -> str:
        if not isinstance(node.tag, str):
            return ""
        if "}" in node.tag:
            return node.tag.split("}", 1)[1].lower()
        return node.tag.lower()

    def _is_within_print_toc(self, element: etree._Element | None) -> bool:
        current = element
        while current is not None:
            if self._tag_name(current) == "level1" and current.get("class") == "print_toc":
                return True
            current = current.getparent()
        return False

    @staticmethod
    def _is_bold_span(node: etree._Element) -> bool:
        tag = node.tag.lower() if isinstance(node.tag, str) else ""
        if tag != "span":
            return False
        style = (node.get("style") or "").replace(" ", "").lower()
        return "font-weight:bold" in style or "bold" in node.attrib

    @staticmethod
    def _is_italic_span(node: etree._Element) -> bool:
        tag = node.tag.lower() if isinstance(node.tag, str) else ""
        if tag != "span":
            return False
        style = (node.get("style") or "").replace(" ", "").lower()
        return "font-style:italic" in style

    def _extract_special_marker(self, node: etree._Element) -> str:
        candidate = MARKUP_TOKEN_PATTERN.sub("", "".join(node.itertext())).strip()
        return candidate if candidate in SPECIAL_MARKER_VALUES else ""

    @staticmethod
    def _is_caption_candidate(node: etree._Element) -> bool:
        tag = node.tag.lower() if isinstance(node.tag, str) else ""
        if tag in {"figcaption", "caption"}:
            return True
        if tag != "p":
            return False

        visible_children = [child for child in node if isinstance(child.tag, str)]
        if not visible_children:
            return False
        return all(child.tag.lower() in {"em", "i", "span"} for child in visible_children)

    @staticmethod
    def _normalized_paragraph_text(node: etree._Element) -> str:
        combined = unescape("".join(node.itertext())).replace("\xa0", " ")
        combined = re.sub(r"\s+", " ", combined)
        return combined.strip()

    @staticmethod
    def _strip_markup_tokens(text: str) -> str:
        stripped = MARKUP_TOKEN_PATTERN.sub("", unescape(text))
        return re.sub(r"\s+", " ", stripped).strip()

    def _normalize_output_tree(self, root: etree._Element) -> None:
        changed = True
        while changed:
            changed = False
            for element in list(root.iter()):
                if self._merge_adjacent_emphasis(element):
                    changed = True
                if self._merge_broken_paragraphs(element):
                    changed = True
                if self._merge_broken_list_items(element):
                    changed = True

        for element in root.iter():
            self._remove_heading_formatting(element)

        for element in root.iter():
            self._fix_misplaced_bracketed_inline_markup(element)

        for element in root.iter():
            self._normalize_element_text_nodes(element)

    def _merge_adjacent_emphasis(self, parent: etree._Element) -> bool:
        changed = False
        index = 0
        while index < len(parent) - 1:
            current = parent[index]
            following = parent[index + 1]
            if self._tag_name(current) != "em" or self._tag_name(following) != "em":
                index += 1
                continue

            separator = " "
            if current.tail and current.tail.strip():
                separator = current.tail
            current.tail = None
            self._append_text_to_element(current, separator)
            self._append_element_contents(current, following)
            current.tail = self._merge_tail_text(current.tail, following.tail)
            parent.remove(following)
            changed = True
        return changed

    def _merge_broken_paragraphs(self, parent: etree._Element) -> bool:
        changed = False
        index = 0
        while index < len(parent) - 1:
            current = parent[index]
            following = parent[index + 1]
            if self._tag_name(current) != "p" or self._tag_name(following) != "p":
                index += 1
                continue
            if not self._should_merge_text_blocks(current, following):
                index += 1
                continue

            self._append_text_to_element(current, " ")
            self._append_element_contents(current, following)
            current.tail = self._merge_tail_text(current.tail, following.tail)
            parent.remove(following)
            changed = True
        return changed

    def _merge_broken_list_items(self, parent: etree._Element) -> bool:
        if self._tag_name(parent) != "list":
            return False

        changed = False
        index = 0
        while index < len(parent) - 1:
            current = parent[index]
            following = parent[index + 1]
            if self._tag_name(current) != "li" or self._tag_name(following) != "li":
                index += 1
                continue
            if not self._should_merge_text_blocks(current, following):
                index += 1
                continue

            self._append_text_to_element(current, " ")
            self._append_element_contents(current, following)
            current.tail = self._merge_tail_text(current.tail, following.tail)
            parent.remove(following)
            changed = True
        return changed

    def _should_merge_text_blocks(self, current: etree._Element, following: etree._Element) -> bool:
        if not self._is_mergeable_text_block(current) or not self._is_mergeable_text_block(following):
            return False

        current_text = self._normalized_visible_text(current)
        following_text = self._normalized_visible_text(following)
        if not current_text or not following_text:
            return False

        next_token = following_text.split(maxsplit=1)[0].strip("([{\"'").lower()
        starts_lowercase = following_text[:1].islower()
        current_incomplete = (
            current_text.endswith("...")
            or current_text.endswith("-")
            or current_text.endswith("/")
            or current_text.endswith("(")
            or current_text.endswith("[")
            or current_text.endswith("{")
            or current_text[-1].isalnum()
        )
        return starts_lowercase or next_token in PARAGRAPH_MERGE_PREFIXES or current_incomplete

    def _is_mergeable_text_block(self, element: etree._Element) -> bool:
        if self._tag_name(element) not in {"p", "li"}:
            return False

        blocked_tags = {"pagenum", "list", "table", "linegroup", "sidebar", "imggroup"}
        return not any(self._tag_name(child) in blocked_tags for child in element.iterdescendants())

    def _remove_heading_formatting(self, element: etree._Element) -> None:
        tag = self._tag_name(element)
        if tag not in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            return

        plain_text = self._normalized_visible_text(element)
        for child in list(element):
            element.remove(child)
        element.text = plain_text

    def _fix_misplaced_bracketed_inline_markup(self, element: etree._Element) -> None:
        for index, child in enumerate(list(element)):
            if self._tag_name(child) not in {"strong", "em"}:
                continue

            self._move_leading_opening_brackets_outside_inline(element, child, index)
            self._move_leading_closing_brackets_outside_inline(element, child, index)
            self._move_trailing_closing_brackets_outside_inline(child)

    def _move_leading_opening_brackets_outside_inline(
        self,
        parent: etree._Element,
        child: etree._Element,
        child_index: int,
    ) -> None:
        moved = self._extract_leading_brackets_from_inline(
            child,
            lambda character, _moved_text: character in OPENING_BRACKETS,
        )
        if not moved:
            return
        self._append_text_before_child(parent, child_index, moved)

    def _move_leading_closing_brackets_outside_inline(
        self,
        parent: etree._Element,
        child: etree._Element,
        child_index: int,
    ) -> None:
        anchor_text = self._text_before_child(parent, child_index)
        moved = self._extract_leading_brackets_from_inline(
            child,
            lambda character, moved_text: (
                character in CLOSING_BRACKETS
                and (anchor_text + moved_text).count(REVERSE_BRACKET_PAIRS[character]) > (anchor_text + moved_text).count(character)
            ),
        )
        if not moved:
            return
        self._append_text_before_child(parent, child_index, moved)

    def _move_trailing_closing_brackets_outside_inline(self, child: etree._Element) -> None:
        moved = self._pop_trailing_brackets_from_inline(child)
        if moved:
            child.tail = f"{moved}{child.tail or ''}"

    @staticmethod
    def _text_before_child(parent: etree._Element, child_index: int) -> str:
        if child_index == 0:
            return parent.text or ""
        return parent[child_index - 1].tail or ""

    @staticmethod
    def _append_text_before_child(parent: etree._Element, child_index: int, text: str) -> None:
        if not text:
            return
        if child_index == 0:
            parent.text = f"{parent.text or ''}{text}"
            return
        previous = parent[child_index - 1]
        previous.tail = f"{previous.tail or ''}{text}"

    def _extract_leading_brackets_from_inline(
        self,
        element: etree._Element,
        predicate,
        moved_text: str = "",
    ) -> str:
        text = element.text or ""
        if text:
            extracted = ""
            while text and predicate(text[0], moved_text + extracted):
                extracted += text[0]
                text = text[1:]
            if extracted:
                element.text = text
            return extracted

        if len(element):
            return self._extract_leading_brackets_from_inline(element[0], predicate, moved_text)
        return ""

    def _pop_trailing_brackets_from_inline(self, element: etree._Element) -> str:
        moved = ""
        if len(element):
            moved = self._pop_trailing_brackets_from_inline(element[-1])
            if moved:
                return moved
            tail = element[-1].tail or ""
            trimmed_tail = tail.rstrip("".join(CLOSING_BRACKETS))
            moved = tail[len(trimmed_tail):]
            if moved:
                element[-1].tail = trimmed_tail
                return moved

        text = element.text or ""
        trimmed_text = text.rstrip("".join(CLOSING_BRACKETS))
        moved = text[len(trimmed_text):]
        if moved:
            element.text = trimmed_text
        return moved

    def _normalize_element_text_nodes(self, element: etree._Element) -> None:
        element.text = self._normalize_text_fragment(element.text)
        for child in element:
            child.tail = self._normalize_text_fragment(child.tail)

        self._trim_closing_tag_spacing(element)
        self._ensure_inline_tail_spacing(element)

    def _trim_closing_tag_spacing(self, element: etree._Element) -> None:
        trailing_space_found = False
        if len(element):
            last = element[-1]
            if last.tail:
                stripped = last.tail.rstrip()
                trailing_space_found = stripped != last.tail
                last.tail = stripped
        elif element.text:
            stripped = element.text.rstrip()
            trailing_space_found = stripped != element.text
            element.text = stripped

        if trailing_space_found and self._tag_name(element) in INLINE_OUTPUT_TAGS:
            element.tail = self._merge_tail_text(" ", element.tail)

    def _ensure_inline_tail_spacing(self, element: etree._Element) -> None:
        if self._tag_name(element) not in {"strong", "em", "linenum"} or not element.tail:
            return
        if element.tail[0].isspace() or element.tail[0] in ",.;:!?)]}>":
            return
        element.tail = f" {element.tail}"

    @staticmethod
    def _append_element_contents(target: etree._Element, source: etree._Element) -> None:
        if source.text:
            DTBookConverter._append_text_to_element(target, source.text)
        for child in list(source):
            source.remove(child)
            target.append(child)

    @staticmethod
    def _merge_tail_text(existing: str | None, incoming: str | None) -> str | None:
        if not incoming:
            return existing
        if not existing:
            return incoming
        return f"{existing}{incoming}"

    def _normalized_visible_text(self, element: etree._Element) -> str:
        return self._normalize_text_fragment(" ".join(part.strip() for part in element.itertext() if part.strip())).strip()

    @staticmethod
    def _normalize_text_fragment(text: str | None) -> str | None:
        if text is None:
            return None

        normalized = text.replace("\xa0", " ")
        normalized = re.sub(r"([)\]}>])(?=[A-Za-z0-9])", r"\1 ", normalized)
        normalized = re.sub(r"\s{2,}", " ", normalized)
        return normalized

    def _cleanup_empty_elements(self, root: etree._Element) -> None:
        removable_tags = {
            "p",
            "line",
            "caption",
            "list",
            "li",
            "imggroup",
            "sidebar",
            "strong",
            "em",
            "table",
            "tr",
            "td",
            "th",
            "linegroup",
        }
        changed = True
        while changed:
            changed = False
            for element in list(root.iter()):
                local_name = self._tag_name(element)
                if local_name not in removable_tags:
                    continue
                if self._has_meaningful_content(element):
                    continue
                parent = element.getparent()
                if parent is not None:
                    parent.remove(element)
                    changed = True
