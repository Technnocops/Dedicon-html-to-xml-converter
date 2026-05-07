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
BLOCK_MARKER_TAG_PATTERN = r"(?:page|pm|bl|ft|hsd\d*|sd|ol|ul|fig|img)"
INLINE_OUTPUT_TAGS = {"strong", "em", "linenum"}
INLINE_FORMATTING_TAGS = INLINE_OUTPUT_TAGS | {"b", "i", "span"}
INLINE_PRESERVE_HINT_TAGS = {
    "a",
    "abbr",
    "acronym",
    "b",
    "bdi",
    "bdo",
    "big",
    "button",
    "cite",
    "code",
    "data",
    "del",
    "dfn",
    "em",
    "i",
    "img",
    "ins",
    "kbd",
    "label",
    "mark",
    "meter",
    "object",
    "output",
    "picture",
    "progress",
    "q",
    "ruby",
    "rp",
    "rt",
    "s",
    "samp",
    "small",
    "span",
    "strong",
    "sub",
    "sup",
    "time",
    "u",
    "var",
    "wbr",
}
FIXED_LINE_BREAK_REPLACEMENTS = (
    ("<p>\n<strong>", "<p><strong>"),
    ("<p>\n<em>", "<p><em>"),
    ("<strong>\n<em>", "<strong><em>"),
    ("<li>\n<strong>", "<li><strong>"),
    ("</strong>\n<em>", "</strong><em>"),
    ("<li>\n<em>", "<li><em>"),
    ("<line>\n<strong>", "<line><strong>"),
    ("<line>\n<linenum>", "<line><linenum>"),
    ("<line>\n<em>", "<line><em>"),
    ("</linenum>\n<strong>", "</linenum><strong>"),
    ("</strong>\n</p>", "</strong></p>"),
    ("</strong>\n</line>", "</strong></line>"),
    ("</em>\n</strong>", "</em></strong>"),
    ("</em>\n</line>", "</em></line>"),
    ("</em>\n</p>", "</em></p>"),
    ("</sup>\n</p>", "</sup></p>"),
    ("</sup>\n</line>", "</sup></line>"),
    ("</sub>\n</p>", "</sub></p>"),
    ("</sub>\n</line>", "</sub></line>"),
    ("<td>\n<strong>", "<td><strong>"),
    ("</strong>\n</td>", "</strong></td>"),
    ("</em>\n<sup>", "</em><sup>"),
    ("</em>\n<sub>", "</em><sub>"),
    ("</strong>\n<sup>", "</strong><sup>"),
    ("</strong>\n<sub>", "</strong><sub>"),
)
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
HTML_VOID_PRESERVE_TAGS = {"area", "base", "col", "embed", "input", "link", "meta", "param", "source", "track", "wbr"}
TABLE_SECTION_TAGS = {"thead", "tbody", "tfoot", "tr", "td", "th", "caption", "colgroup", "col"}
BLOCK_PRESERVE_HINT_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "body",
    "caption",
    "colgroup",
    "dd",
    "details",
    "dialog",
    "div",
    "dl",
    "dt",
    "fieldset",
    "figcaption",
    "figure",
    "footer",
    "form",
    "head",
    "header",
    "hgroup",
    "hr",
    "html",
    "legend",
    "li",
    "main",
    "menu",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "summary",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "ul",
}
BLOCK_MARKER_PATTERN = re.compile(rf"^\s*<(?P<closing>/)?(?P<tag>{BLOCK_MARKER_TAG_PATTERN})>\s*$", re.IGNORECASE)
LEADING_BLOCK_MARKER_PATTERN = re.compile(rf"^\s*<(?P<closing>/)?(?P<tag>{BLOCK_MARKER_TAG_PATTERN})>\s*", re.IGNORECASE)
HR_MARKER_PATTERN = re.compile(r"^\s*<hr\s*/>\s*$", re.IGNORECASE)
LEADING_HR_MARKER_PATTERN = re.compile(r"^\s*<hr\s*/>\s*", re.IGNORECASE)
HEADING_MARKER_PATTERN = re.compile(r"^\s*<h(?P<level>[1-6])>\s*(?P<text>.*?)\s*</h(?P=level)>\s*$", re.IGNORECASE | re.DOTALL)
HEADING_WRAPPER_SEARCH_PATTERN = re.compile(r"<h(?P<level>[1-6])>\s*(?P<text>.*?)\s*</h(?P=level)>", re.IGNORECASE | re.DOTALL)
HEADING_TOKEN_PATTERN = re.compile(r"<h(?P<level>[1-6])>", re.IGNORECASE)
OPEN_HEADING_FRAGMENT_PATTERN = re.compile(r"^\s*<h(?P<level>[1-6])>\s*(?P<text>.*?)\s*$", re.IGNORECASE | re.DOTALL)
HEADING_CLOSING_TOKEN_PATTERN = re.compile(r"</h(?P<level>[1-6])>\s*$", re.IGNORECASE)
DOCUMENT_RANGE_PATTERN = re.compile(r"_(?P<start>\d+)-(?P<end>\d+)$")
SIDEBAR_HEADING_PATTERN = re.compile(r"^\s*<(?P<tag>hsd\d*|sd)>\s*(?P<text>.*?)\s*$", re.IGNORECASE | re.DOTALL)
MARKUP_TOKEN_PATTERN = re.compile(rf"(?:</?(?:{BLOCK_MARKER_TAG_PATTERN}|figure|fig|h[1-6])\s*>|<hr\s*/>)", re.IGNORECASE)
SEMANTIC_TOKEN_TEXT_PATTERN = re.compile(rf"</?(?:{BLOCK_MARKER_TAG_PATTERN}|figure|h[1-6])>|<hr\s*/>", re.IGNORECASE)
OPEN_PAGE_MARKER_PATTERN = re.compile(r"^\s*<page>\s*", re.IGNORECASE | re.DOTALL)
INLINE_PAGE_MARKER_PATTERN = re.compile(r"(?is)<page>\s*(?P<content>[^<]*?)\s*</page>|<page>")
TRAILING_CLOSING_BLOCK_MARKER_PATTERN = re.compile(r"\s*</(?P<tag>ft|pm|bl|sd|hsd\d*|fig|img|ol|ul)>\s*$", re.IGNORECASE)
BRACKET_PAIRS = {"(": ")", "[": "]", "{": "}", "<": ">"}
OPENING_BRACKETS = set(BRACKET_PAIRS)
CLOSING_BRACKETS = set(BRACKET_PAIRS.values())
REVERSE_BRACKET_PAIRS = {value: key for key, value in BRACKET_PAIRS.items()}
INTERNAL_PRESERVED_ATTR = "_tc_preserved"


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
    active_poem: etree._Element | None = None
    active_linegroup: etree._Element | None = None
    active_blockquote: etree._Element | None = None
    active_footnote: etree._Element | None = None
    active_footnote_sequence: int | None = None
    active_figure: etree._Element | None = None
    active_figure_line: int | None = None
    active_figure_marker_tag: str = ""
    pending_split_heading_level: int | None = None
    pending_split_heading_text: str = ""
    pending_split_heading_line: int | None = None
    current_page_number: str = ""
    page_counter: int = 0
    footnote_counter: int = 0
    footnote_symbol_counter: int = 0
    level_counter: int = 0
    page_image_counter: dict[str, int] = field(default_factory=dict)
    used_output_names: set[str] = field(default_factory=set)
    book_id: str = ""
    page_range: PageRangeSelection | None = None
    detected_pages: set[int] = field(default_factory=set)
    pending_precedingemptyline: bool = False
    preserved_tag_reports: set[tuple[str, str]] = field(default_factory=set)
    dropped_text_reports: set[tuple[str, int | None, str, str]] = field(default_factory=set)

    @property
    def active_parent(self) -> etree._Element:
        return self.level_stack[-1][1] if self.level_stack else self.bodymatter

    @property
    def base_parent(self) -> etree._Element:
        if self.active_footnote is not None:
            return self.active_footnote
        if self.sidebar_stack:
            return self.sidebar_stack[-1]
        if self.active_blockquote is not None:
            return self.active_blockquote
        return self.active_parent

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
        return True

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
        "tag bl invalid",
        "tag ft invalid",
        "tag pm invalid",
        "tag page invalid",
        "tag sd invalid",
        "tag hsd invalid",
        "tag fig invalid",
        "unexpected end tag : bl",
        "unexpected end tag : ft",
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
            page_counter=(page_range.start_page - 1) if page_range is not None else 0,
        )
        total_files = max(len(documents), 1)
        previous_document_range: tuple[int, int] | None = None

        for index, document in enumerate(documents, start=1):
            context.current_file = document.name
            context.current_document_path = document.path
            if progress_callback:
                progress_callback(self._progress_value(index - 1, total_files), f"Parsing {document.name}")

            current_document_range = self._extract_document_page_range(document)
            reset_for_document_gap = self._should_reset_for_document_gap(previous_document_range, current_document_range)
            if reset_for_document_gap:
                self._reset_document_state_for_new_sequence(context)

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
            if not self._document_contains_any_heading(source_body) and not context.level_stack:
                self._open_dummy_root_level(context)
            self._convert_container(source_body, context)
            previous_document_range = current_document_range

            if progress_callback:
                progress_callback(self._progress_value(index, total_files), f"Converted {document.name}")

        self._promote_frontmatter_sections(frontmatter, bodymatter)
        self._promote_rearmatter_sections(bodymatter, rearmatter)
        self._finalize_page_range(context)
        self._cleanup_empty_elements(root)
        self._renumber_levels(root)
        self._normalize_output_tree(root)
        self._cleanup_empty_elements(root)
        self._clear_internal_preservation_markers(root)
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
        xml_body = xml_body.replace("><", ">\n<").strip() + "\n"
        xml_body = DTBookConverter._normalize_xml_line_breaks(xml_body)
        return (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            f'<?xml-model href="{SCHEMATRON_HREF}" type="application/xml" schematypens="{SCHEMATRON_NAMESPACE}"?>\n'
            '<!DOCTYPE dtbook PUBLIC "-//NISO//DTD dtbook 2005-3//EN" "http://www.daisy.org/z3986/2005/dtbook-2005-3.dtd">\n'
            + xml_body
        )

    @staticmethod
    def _normalize_xml_line_breaks(xml_body: str) -> str:
        normalized = re.sub(r"</strong>\s*<strong>", " ", xml_body)
        for source, target in FIXED_LINE_BREAK_REPLACEMENTS:
            normalized = normalized.replace(source, target)
        normalized = re.sub(r"(<a\b[^>]*>)\n(<(?:strong|em|sup|sub)>)", r"\1\2", normalized)
        normalized = re.sub(r"(</(?:strong|em|sup|sub)>)\n(</a>)", r"\1\2", normalized)
        normalized = re.sub(r"(</(?:strong|em)>)\n(<(?:sup|sub)>)", r"\1\2", normalized)
        normalized = re.sub(r"<caption>\s*</caption>", "<caption></caption>", normalized)
        return normalized

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
    def _extract_document_page_range(document: InputDocument) -> tuple[int, int] | None:
        match = DOCUMENT_RANGE_PATTERN.search(document.path.stem)
        if match is None:
            return None
        return (int(match.group("start")), int(match.group("end")))

    @staticmethod
    def _should_reset_for_document_gap(
        previous_document_range: tuple[int, int] | None,
        current_document_range: tuple[int, int] | None,
    ) -> bool:
        if previous_document_range is None or current_document_range is None:
            return False
        return current_document_range[0] > previous_document_range[1] + 1

    def _reset_document_state_for_new_sequence(self, context: ConversionContext) -> None:
        self._close_active_poem(context)
        self._close_active_blockquote(context)
        self._close_active_footnote(context)
        self._close_active_figure(context)
        self._close_open_lists(context)
        context.level_stack.clear()
        context.sidebar_stack.clear()
        context.active_poem = None
        context.active_linegroup = None
        context.active_blockquote = None
        context.active_footnote = None
        context.active_footnote_sequence = None
        context.active_figure = None
        context.active_figure_line = None
        context.active_figure_marker_tag = ""
        context.pending_split_heading_level = None
        context.pending_split_heading_text = ""
        context.pending_split_heading_line = None

    def _document_contains_any_heading(self, source_body: etree._Element) -> bool:
        for node in source_body.iter():
            tag = self._tag_name(node)
            if not tag:
                continue
            if re.fullmatch(r"h[1-6]", tag):
                return True
            if HEADING_WRAPPER_SEARCH_PATTERN.search(self._normalized_paragraph_text(node)):
                return True
        return False

    def _open_dummy_root_level(self, context: ConversionContext) -> None:
        level = context.open_level(1)
        etree.SubElement(level, "h1")

    @staticmethod
    def _parse_numeric_page(value: str) -> int | None:
        digit_match = re.search(r"\d+", value)
        if digit_match is None:
            return None
        return int(digit_match.group(0))

    def _resolve_effective_page_number(self, raw_value: str, context: ConversionContext) -> int:
        if context.page_range is not None:
            context.page_counter += 1
            return context.page_counter

        numeric_page = self._parse_numeric_page(raw_value)
        if numeric_page is not None:
            context.page_counter = numeric_page
            return numeric_page

        context.page_counter += 1
        return context.page_counter

    def _should_skip_node_outside_range(self, source_node: etree._Element, context: ConversionContext) -> bool:
        return False

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
            if context.active_figure is None and self._convert_figure_like_container(source_node, parent, context):
                return
            self._convert_container(source_node, context, destination_parent=destination_parent)
            return

        if tag in {"style", "script", "head", "title"}:
            return

        if tag in VOID_TAGS:
            return

        if tag == "a" and source_node.get("name") and not source_node.get("href"):
            self._append_inline_content(parent, source_node, context, strip_markup_tokens=True)
            return

        if tag == "page":
            self._append_pagenum(context.base_parent, "".join(source_node.itertext()).strip(), context)
            return

        if tag == "hr":
            context.pending_precedingemptyline = True
            return

        if self._try_complete_pending_split_heading(source_node, context):
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
            image_parent = context.active_figure if context.active_figure is not None else parent
            image_group = self._convert_image_group(source_node, image_parent, context)
            if context.active_figure is None:
                self._ensure_image_group_accessibility_placeholders(image_group)
            return

        if tag == "table":
            self._convert_table(source_node, parent, context)
            return

        if tag == "pm":
            self._convert_pm_block(source_node, parent, context)
            return

        if tag == "ft":
            self._convert_footnote_block(source_node, parent, context)
            return

        if tag in {"hsd", "sd"}:
            self._convert_sidebar(source_node, parent, context)
            return

        if tag == "bl":
            self._convert_blockquote(source_node, parent, context)
            return

        if tag in {"figure", "fig"} and context.active_figure is None and self._convert_figure_like_container(source_node, parent, context):
            return

        self._preserve_block_source_element(parent, source_node, context, strip_markup_tokens=True)

    def _convert_paragraph(
        self,
        source_node: etree._Element,
        context: ConversionContext,
        *,
        normalized_text: str | None = None,
        consume_leading_markers: bool = True,
        convert_inline_page_markers_override: bool | None = None,
    ) -> None:
        paragraph_text = normalized_text if normalized_text is not None else self._normalized_paragraph_text(source_node)
        leading_markers_consumed = False
        if self._starts_semantic_heading_after_leading_markers(paragraph_text):
            self._close_heading_boundary_contexts(context)
        if consume_leading_markers:
            paragraph_text, leading_markers_consumed = self._consume_leading_semantic_markers(
                paragraph_text,
                context,
                source_line=source_node.sourceline,
            )
        paragraph_text, trailing_closing_markers = self._consume_trailing_closing_block_markers(paragraph_text)
        if self._convert_semantic_heading(
            source_node,
            paragraph_text,
            context,
            convert_inline_page_markers=not leading_markers_consumed,
        ):
            self._apply_trailing_closing_markers(context, trailing_closing_markers, source_node.sourceline)
            return

        if not paragraph_text and not self._has_renderable_inline_content(source_node):
            self._apply_trailing_closing_markers(context, trailing_closing_markers, source_node.sourceline)
            return

        if self._capture_split_heading_prefix(source_node, paragraph_text, context):
            self._apply_trailing_closing_markers(context, trailing_closing_markers, source_node.sourceline)
            return

        if HR_MARKER_PATTERN.match(paragraph_text):
            context.pending_precedingemptyline = True
            self._apply_trailing_closing_markers(context, trailing_closing_markers, source_node.sourceline)
            return

        block_match = BLOCK_MARKER_PATTERN.match(paragraph_text)
        if block_match:
            self._handle_block_marker(
                context,
                block_match.group("tag").lower(),
                bool(block_match.group("closing")),
                source_line=source_node.sourceline,
            )
            self._apply_trailing_closing_markers(context, trailing_closing_markers, source_node.sourceline)
            return

        convert_inline_page_markers = (
            convert_inline_page_markers_override
            if convert_inline_page_markers_override is not None
            else not leading_markers_consumed
        )

        if context.active_linegroup is not None:
            line = etree.SubElement(context.active_linegroup, "line")
            self._append_inline_content(
                line,
                source_node,
                context,
                pm_mode=True,
                strip_markup_tokens=True,
                convert_inline_page_markers=convert_inline_page_markers,
            )
            if not self._has_meaningful_content(line):
                context.active_linegroup.remove(line)
            self._apply_trailing_closing_markers(context, trailing_closing_markers, source_node.sourceline)
            return

        if context.active_footnote is not None:
            self._assign_active_footnote_id(source_node, context)
            paragraph = etree.SubElement(context.active_footnote, "p")
            self._append_inline_content(
                paragraph,
                source_node,
                context,
                strip_markup_tokens=True,
                convert_inline_page_markers=convert_inline_page_markers,
            )
            if not self._has_meaningful_content(paragraph):
                self._report_dropped_source_text(source_node, context, reason="footnote content")
                context.active_footnote.remove(paragraph)
            self._apply_trailing_closing_markers(context, trailing_closing_markers, source_node.sourceline)
            return

        if context.active_figure is not None:
            caption_parent = self._ensure_figure_caption(context.active_figure)
            paragraph = etree.SubElement(caption_parent, "p")
            self._append_inline_content(
                paragraph,
                source_node,
                context,
                strip_markup_tokens=True,
                convert_inline_page_markers=convert_inline_page_markers,
            )
            if not self._has_meaningful_content(paragraph):
                self._report_dropped_source_text(source_node, context, reason="figure caption content")
                caption_parent.remove(paragraph)
                if not len(caption_parent):
                    context.active_figure.remove(caption_parent)
            self._apply_trailing_closing_markers(context, trailing_closing_markers, source_node.sourceline)
            return

        if context.list_stack:
            list_item = etree.SubElement(context.list_stack[-1], "li")
            context.list_item_stack[-1] = list_item
            self._append_inline_content(
                list_item,
                source_node,
                context,
                strip_markup_tokens=True,
                convert_inline_page_markers=convert_inline_page_markers,
            )
            if not self._has_meaningful_content(list_item):
                context.list_stack[-1].remove(list_item)
                context.list_item_stack[-1] = None
            self._apply_trailing_closing_markers(context, trailing_closing_markers, source_node.sourceline)
            return

        paragraph = self._create_paragraph(context.current_content_parent, context)
        self._append_inline_content(
            paragraph,
            source_node,
            context,
            strip_markup_tokens=True,
            convert_inline_page_markers=convert_inline_page_markers,
        )
        if not self._has_meaningful_content(paragraph):
            self._report_dropped_source_text(source_node, context, reason="paragraph content")
            context.current_content_parent.remove(paragraph)
        self._apply_trailing_closing_markers(context, trailing_closing_markers, source_node.sourceline)

    def _handle_block_marker(
        self,
        context: ConversionContext,
        tag: str,
        is_closing: bool,
        *,
        source_line: int | None = None,
    ) -> None:
        normalized_tag = tag.lower()
        if normalized_tag.startswith("hsd"):
            normalized_tag = "sd"

        if normalized_tag == "page" and not is_closing:
            self._append_pagenum(context.base_parent, "", context)
            return

        if normalized_tag == "pm":
            if is_closing:
                self._close_active_poem(context)
            else:
                self._open_poem(context)
            return

        if normalized_tag == "ft":
            if is_closing:
                self._close_active_footnote(context)
            elif context.active_footnote is None:
                self._open_footnote(context)
            return

        if normalized_tag == "sd":
            if is_closing:
                if context.sidebar_stack:
                    context.sidebar_stack.pop()
            else:
                self._open_sidebar(context, move_previous_heading=True)
            return

        if normalized_tag == "bl":
            if is_closing:
                self._close_active_blockquote(context)
            else:
                context.active_blockquote = etree.SubElement(context.current_content_parent, "blockquote")
            return

        if normalized_tag in {"fig", "img"}:
            if is_closing:
                self._close_active_figure(context)
            elif context.active_figure is None:
                context.active_figure = etree.SubElement(context.current_content_parent, "imggroup")
                context.active_figure_line = source_line
                context.active_figure_marker_tag = normalized_tag
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
        if self._starts_semantic_heading_after_leading_markers(heading_text):
            self._close_heading_boundary_contexts(context)
        heading_text, leading_markers_consumed = self._consume_leading_semantic_markers(
            heading_text,
            context,
            source_line=source_node.sourceline,
        )
        if not heading_text:
            return

        block_match = BLOCK_MARKER_PATTERN.match(heading_text)
        if block_match:
            self._handle_block_marker(
                context,
                block_match.group("tag").lower(),
                bool(block_match.group("closing")),
                source_line=source_node.sourceline,
            )
            return

        if SIDEBAR_HEADING_PATTERN.match(heading_text):
            self._convert_sidebar_heading(source_node, context)
            return

        if self._convert_semantic_heading(source_node, heading_text, context, convert_inline_page_markers=not leading_markers_consumed):
            return

        self._convert_paragraph(
            source_node,
            context,
            normalized_text=heading_text,
            consume_leading_markers=False,
            convert_inline_page_markers_override=not leading_markers_consumed,
        )

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

        self._create_heading_from_source(source_node, heading_text, level_number, context)

    def _convert_semantic_heading(
        self,
        source_node: etree._Element,
        normalized_text: str,
        context: ConversionContext,
        *,
        convert_inline_page_markers: bool = True,
    ) -> bool:
        heading_match = HEADING_WRAPPER_SEARCH_PATTERN.search(normalized_text)
        if heading_match is None:
            return False

        self._emit_leading_page_markers(normalized_text[: heading_match.start()], context)
        self._create_heading_from_source(
            source_node,
            normalized_text,
            int(heading_match.group("level")),
            context,
            convert_inline_page_markers=convert_inline_page_markers,
        )
        return True

    def _try_complete_pending_split_heading(self, source_node: etree._Element, context: ConversionContext) -> bool:
        level_number = context.pending_split_heading_level
        if level_number is None:
            return False
        source_tag = self._tag_name(source_node)
        normalized_text = self._normalized_paragraph_text(source_node)
        closes_pending_heading = bool(re.search(rf"</h{level_number}>\s*$", normalized_text, re.IGNORECASE))
        if source_tag != f"h{level_number}" and not closes_pending_heading:
            return False

        combined_heading_text = " ".join(
            part
            for part in (context.pending_split_heading_text.strip(), self._strip_markup_tokens(normalized_text).strip())
            if part
        )
        level = context.open_level(level_number, context.pending_split_heading_line or source_node.sourceline)
        self._apply_level_semantics(level, combined_heading_text, level_number)
        heading = etree.SubElement(level, f"h{level_number}")
        heading.text = f"{context.pending_split_heading_text.strip()} "
        self._append_heading_text(heading, source_node, context, convert_inline_page_markers=False)
        if heading.text and len(heading) and not heading.text[-1].isspace():
            heading.text = f"{heading.text} "
        if heading.text:
            heading.text = re.sub(r"\s{2,}", " ", heading.text).strip()
        for child in heading:
            if child.tail:
                child.tail = re.sub(r"\s{2,}", " ", child.tail)
        context.pending_split_heading_level = None
        context.pending_split_heading_text = ""
        context.pending_split_heading_line = None
        return True

    def _create_heading_from_source(
        self,
        source_node: etree._Element,
        heading_text: str,
        level_number: int,
        context: ConversionContext,
        *,
        convert_inline_page_markers: bool = True,
    ) -> None:
        level = context.open_level(level_number, source_node.sourceline)
        self._apply_level_semantics(level, heading_text, level_number)
        heading = etree.SubElement(level, f"h{level_number}")
        self._append_heading_text(
            heading,
            source_node,
            context,
            convert_inline_page_markers=convert_inline_page_markers,
        )

    def _emit_leading_page_markers(self, text: str, context: ConversionContext) -> None:
        remaining = text
        while remaining.strip():
            page_match = PAGE_MARKER_PATTERN.match(remaining)
            if page_match is not None:
                self._append_pagenum(context.base_parent, page_match.group(1).strip(), context)
                remaining = remaining[page_match.end() :]
                continue

            open_match = OPEN_PAGE_MARKER_PATTERN.match(remaining)
            if open_match is not None:
                self._append_pagenum(context.base_parent, "", context)
                remaining = remaining[open_match.end() :]
                continue
            break

    def _consume_leading_semantic_markers(
        self,
        text: str,
        context: ConversionContext,
        *,
        source_line: int | None = None,
    ) -> tuple[str, bool]:
        remaining = text
        consumed_markers = False
        while remaining.strip():
            page_match = PAGE_MARKER_PATTERN.match(remaining)
            if page_match is not None:
                self._append_pagenum(context.base_parent, page_match.group(1).strip(), context)
                remaining = remaining[page_match.end() :]
                consumed_markers = True
                continue

            hr_match = LEADING_HR_MARKER_PATTERN.match(remaining)
            if hr_match is not None:
                context.pending_precedingemptyline = True
                remaining = remaining[hr_match.end() :]
                consumed_markers = True
                continue

            block_match = LEADING_BLOCK_MARKER_PATTERN.match(remaining)
            if block_match is None:
                break

            self._handle_block_marker(
                context,
                block_match.group("tag").lower(),
                bool(block_match.group("closing")),
                source_line=source_line,
            )
            remaining = remaining[block_match.end() :]
            consumed_markers = True

        return remaining.strip(), consumed_markers

    def _consume_trailing_closing_block_markers(self, text: str) -> tuple[str, list[str]]:
        remaining = text
        closing_tags: list[str] = []
        while remaining.strip():
            closing_match = TRAILING_CLOSING_BLOCK_MARKER_PATTERN.search(remaining)
            if closing_match is None:
                break
            closing_tags.insert(0, closing_match.group("tag").lower())
            remaining = remaining[: closing_match.start()]
        return remaining.strip(), closing_tags

    def _apply_trailing_closing_markers(
        self,
        context: ConversionContext,
        closing_tags: list[str],
        source_line: int | None,
    ) -> None:
        for tag in closing_tags:
            self._handle_block_marker(context, tag, True, source_line=source_line)

    def _capture_split_heading_prefix(
        self,
        source_node: etree._Element,
        paragraph_text: str,
        context: ConversionContext,
    ) -> bool:
        if context.pending_split_heading_level is not None:
            return False
        opening_match = OPEN_HEADING_FRAGMENT_PATTERN.match(paragraph_text)
        if opening_match is None:
            return False
        level_number = int(opening_match.group("level"))
        if re.search(rf"</h{level_number}>\s*$", paragraph_text, re.IGNORECASE):
            return False
        prefix_text = self._strip_markup_tokens(paragraph_text)
        if not prefix_text:
            return False
        next_sibling = source_node.getnext()
        if next_sibling is None:
            return False
        next_tag = self._tag_name(next_sibling)
        next_text = self._normalized_paragraph_text(next_sibling)
        if next_tag != f"h{level_number}" and not re.search(rf"</h{level_number}>\s*$", next_text, re.IGNORECASE):
            return False
        context.pending_split_heading_level = level_number
        context.pending_split_heading_text = prefix_text
        context.pending_split_heading_line = source_node.sourceline
        return True

    def _starts_semantic_heading_after_leading_markers(self, text: str) -> bool:
        candidate = self._strip_leading_semantic_markers_for_detection(text)
        return HEADING_WRAPPER_SEARCH_PATTERN.search(candidate) is not None

    def _strip_leading_semantic_markers_for_detection(self, text: str) -> str:
        remaining = text
        while remaining.strip():
            page_match = PAGE_MARKER_PATTERN.match(remaining)
            if page_match is not None:
                remaining = remaining[page_match.end() :]
                continue

            open_match = OPEN_PAGE_MARKER_PATTERN.match(remaining)
            if open_match is not None:
                remaining = remaining[open_match.end() :]
                continue

            hr_match = LEADING_HR_MARKER_PATTERN.match(remaining)
            if hr_match is not None:
                remaining = remaining[hr_match.end() :]
                continue

            block_match = LEADING_BLOCK_MARKER_PATTERN.match(remaining)
            if block_match is None:
                break

            remaining = remaining[block_match.end() :]
        return remaining.strip()

    def _close_heading_boundary_contexts(self, context: ConversionContext) -> None:
        self._close_open_lists(context)
        self._close_active_poem(context)
        self._close_active_blockquote(context)
        self._close_active_footnote(context)
        self._close_active_figure(context)
        context.sidebar_stack.clear()

    def _resolve_heading_level(self, source_node: etree._Element, normalized_text: str) -> int:
        tag_name = self._tag_name(source_node)
        if re.fullmatch(r"h[1-6]", tag_name):
            return int(tag_name[1])

        embedded_heading = HEADING_MARKER_PATTERN.match(normalized_text)
        if embedded_heading:
            return int(embedded_heading.group("level"))

        embedded_heading_token = HEADING_TOKEN_PATTERN.search(normalized_text)
        if embedded_heading_token:
            return int(embedded_heading_token.group("level"))

        return 1

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
        image_group = parent if self._tag_name(parent) == "imggroup" else etree.SubElement(parent, "imggroup")
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
                    line=source_node.sourceline,
                    code="missing-image",
                    tag="img",
                )
            )

        image_element = self._ensure_figure_image(image_group)
        image_element.set("src", f"img/{output_name}")
        image_element.set("alt", "afbeelding")
        return image_group

    def _ensure_figure_image(self, image_group: etree._Element) -> etree._Element:
        for child in image_group:
            if self._tag_name(child) == "img":
                image_group.remove(child)
                image_group.insert(0, child)
                return child

        image_element = etree.Element("img")
        image_group.insert(0, image_element)
        return image_element

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
                    message=(
                        f"{page_range.label} was requested, but no HTML `<page>` markers were detected. "
                        "Content was still converted without generated page numbers."
                    ),
                    code="page-range-no-markers",
                )
            )

    def _convert_table(self, source_node: etree._Element, parent: etree._Element, context: ConversionContext) -> None:
        table = etree.SubElement(parent, "table")
        self._copy_table_children(source_node, table, context)
        if not self._has_meaningful_content(table):
            self._report_dropped_source_text(source_node, context, reason="table content")
            parent.remove(table)

    def _copy_table_children(self, source_node: etree._Element, target_node: etree._Element, context: ConversionContext) -> None:
        if source_node.text:
            self._append_text_fragments(target_node, source_node.text, context, strip_markup_tokens=True)

        for child in source_node:
            tag = self._tag_name(child)
            if tag not in TABLE_SECTION_TAGS:
                if self._is_likely_block_tag(tag):
                    self._preserve_block_source_element(target_node, child, context, strip_markup_tokens=True)
                else:
                    self._append_inline_node(target_node, child, context, strip_markup_tokens=True)
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
        if lowered_key in {"colspan", "rowspan"}:
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
                image_group = self._convert_image_group(child, target_node, context)
                self._ensure_image_group_accessibility_placeholders(image_group)
            else:
                if self._is_likely_block_tag(tag):
                    self._preserve_block_source_element(target_node, child, context, strip_markup_tokens=True)
                else:
                    self._append_inline_node(target_node, child, context, strip_markup_tokens=True)

            if child.tail:
                self._append_text_fragments(target_node, child.tail, context, strip_markup_tokens=True)

    def _convert_pm_block(self, source_node: etree._Element, parent: etree._Element, context: ConversionContext) -> None:
        original_poem = context.active_poem
        original_linegroup = context.active_linegroup
        poem = etree.SubElement(parent, "poem")
        line_group = etree.SubElement(poem, "linegroup")
        context.active_poem = poem
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

        context.active_poem = original_poem
        context.active_linegroup = original_linegroup
        if not self._has_meaningful_content(poem):
            parent.remove(poem)

    def _convert_footnote_block(self, source_node: etree._Element, parent: etree._Element, context: ConversionContext) -> None:
        original_footnote = context.active_footnote
        original_footnote_sequence = context.active_footnote_sequence
        footnote = self._open_footnote(context, parent)
        self._convert_container(source_node, context, destination_parent=footnote)
        context.active_footnote = original_footnote
        context.active_footnote_sequence = original_footnote_sequence
        if not self._has_meaningful_content(footnote):
            self._report_dropped_source_text(source_node, context, reason="footnote block")
            parent.remove(footnote)

    def _open_footnote(self, context: ConversionContext, parent: etree._Element | None = None) -> etree._Element:
        context.footnote_counter += 1
        sequence = context.footnote_counter
        note_parent = parent if parent is not None else context.current_content_parent
        note = etree.SubElement(note_parent, "note", id=f"fn_{sequence}_x")
        context.active_footnote = note
        context.active_footnote_sequence = sequence
        return note

    def _assign_active_footnote_id(self, source_node: etree._Element, context: ConversionContext) -> None:
        footnote = context.active_footnote
        sequence = context.active_footnote_sequence
        if footnote is None or sequence is None:
            return
        if footnote.get("id") and not footnote.get("id", "").endswith("_x"):
            return
        marker = self._footnote_id_marker(source_node, context)
        footnote.set("id", f"fn_{sequence}_{marker}")

    def _footnote_id_marker(self, source_node: etree._Element, context: ConversionContext) -> str:
        visible_text = self._strip_markup_tokens(" ".join(part.strip() for part in source_node.itertext() if part.strip()))
        if not visible_text:
            return "x"
        token_match = re.match(r"^\s*(\S+)", visible_text)
        if token_match is None:
            return "x"
        token = token_match.group(1)
        if token and token[0].isalnum():
            return re.sub(r"[^0-9A-Za-z]+$", "", token).lower() or "x"
        context.footnote_symbol_counter += 1
        return str(context.footnote_symbol_counter)

    def _append_pm_line(self, parent: etree._Element, text: str, context: ConversionContext) -> None:
        line = etree.SubElement(parent, "line")
        self._append_text_fragments(line, text, context, pm_mode=True, strip_markup_tokens=True)
        if not self._has_meaningful_content(line):
            parent.remove(line)

    def _open_poem(self, context: ConversionContext) -> None:
        if context.active_poem is not None and context.active_linegroup is not None:
            return
        poem = etree.SubElement(context.current_content_parent, "poem")
        context.active_poem = poem
        context.active_linegroup = etree.SubElement(poem, "linegroup")

    def _close_active_poem(self, context: ConversionContext) -> None:
        poem = context.active_poem
        line_group = context.active_linegroup
        if poem is None and line_group is None:
            return
        if poem is None and line_group is not None:
            poem = line_group.getparent()
        if poem is not None and not self._has_meaningful_content(poem):
            parent = poem.getparent()
            if parent is not None:
                parent.remove(poem)
        context.active_linegroup = None
        context.active_poem = None

    def _close_active_footnote(self, context: ConversionContext) -> None:
        footnote = context.active_footnote
        if footnote is None:
            return
        if not self._has_meaningful_content(footnote):
            parent = footnote.getparent()
            if parent is not None:
                parent.remove(footnote)
        elif footnote.get("id", "").endswith("_x") and context.active_footnote_sequence is not None:
            footnote.set("id", f"fn_{context.active_footnote_sequence}_x")
        context.active_footnote = None
        context.active_footnote_sequence = None

    def _convert_sidebar(self, source_node: etree._Element, parent: etree._Element, context: ConversionContext) -> None:
        sidebar = etree.SubElement(parent, "sidebar", render="required")
        context.sidebar_stack.append(sidebar)
        self._convert_container(source_node, context, destination_parent=sidebar)
        context.sidebar_stack.pop()
        if not self._has_meaningful_content(sidebar):
            parent.remove(sidebar)

    def _convert_blockquote(self, source_node: etree._Element, parent: etree._Element, context: ConversionContext) -> None:
        original_blockquote = context.active_blockquote
        blockquote = etree.SubElement(parent, "blockquote")
        context.active_blockquote = blockquote
        self._convert_container(source_node, context, destination_parent=blockquote)
        context.active_blockquote = original_blockquote
        if not self._has_meaningful_content(blockquote):
            parent.remove(blockquote)

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

        image_group = self._convert_image_group(image_nodes[0], parent, context)
        caption_sources = [
            child
            for child in direct_children
            if self._tag_name(child) in {"figcaption", "caption", "p"} and self._is_caption_candidate(child)
        ]
        for caption_source in caption_sources:
            self._append_figure_caption_candidate(image_group, caption_source, context)
        for child in direct_children:
            if child in image_nodes or child in caption_sources:
                continue
            child_tag = self._tag_name(child)
            if self._is_likely_block_tag(child_tag):
                self._convert_block(child, context, destination_parent=image_group)
            else:
                self._append_inline_node(image_group, child, context, strip_markup_tokens=True)
            if child.tail:
                self._append_raw_text_to_element(image_group, child.tail)
        self._ensure_image_group_accessibility_placeholders(image_group)
        return True

    def _ensure_figure_caption(self, image_group: etree._Element) -> etree._Element:
        for child in image_group:
            if self._tag_name(child) == "caption":
                return child
        caption = etree.Element("caption")
        insert_at = 1 if len(image_group) and self._tag_name(image_group[0]) == "img" else len(image_group)
        image_group.insert(insert_at, caption)
        return caption

    def _append_figure_caption_candidate(
        self,
        image_group: etree._Element,
        caption_source: etree._Element,
        context: ConversionContext,
    ) -> None:
        caption = self._ensure_figure_caption(image_group)
        paragraph = etree.SubElement(caption, "p")
        self._append_inline_content(paragraph, caption_source, context, strip_markup_tokens=True)
        if not self._has_meaningful_content(paragraph):
            self._report_dropped_source_text(caption_source, context, reason="figure caption content")
            caption.remove(paragraph)
            if not len(caption):
                image_group.remove(caption)

    def _close_active_figure(self, context: ConversionContext) -> None:
        figure = context.active_figure
        if figure is None:
            return
        has_image = any(self._tag_name(child) == "img" for child in figure)
        if has_image:
            self._ensure_image_group_accessibility_placeholders(figure)
        elif self._has_meaningful_content(figure):
            self._report_figure_without_image(context)
        if not self._has_meaningful_content(figure):
            parent = figure.getparent()
            if parent is not None:
                parent.remove(figure)
        context.active_figure = None
        context.active_figure_line = None
        context.active_figure_marker_tag = ""

    def _report_figure_without_image(self, context: ConversionContext) -> None:
        marker_tag = context.active_figure_marker_tag or "fig"
        report_key = (context.current_file, context.active_figure_line, marker_tag, "missing-figure-image-call")
        if report_key in context.dropped_text_reports:
            return
        context.dropped_text_reports.add(report_key)
        context.issues.append(
            ConversionIssue(
                severity=Severity.WARNING,
                message=(
                    f"Image wrapper <{marker_tag}> was preserved as <imggroup>, but no <img src=\"...\"> call was found inside it."
                ),
                file_name=context.current_file,
                line=context.active_figure_line,
                code="missing-figure-image-call",
                tag="imggroup",
            )
        )

    def _ensure_image_group_accessibility_placeholders(self, image_group: etree._Element) -> None:
        if self._figure_has_caption_or_prodnote_text(image_group):
            return

        caption = self._ensure_figure_caption(image_group)
        if caption.text is None and not len(caption):
            caption.text = ""
        prodnote = next((child for child in image_group if self._tag_name(child) == "prodnote"), None)
        if prodnote is None:
            insert_at = 2 if len(image_group) >= 2 and self._tag_name(image_group[1]) == "caption" else len(image_group)
            prodnote = etree.Element("prodnote", render="required")
            image_group.insert(insert_at, prodnote)

        if not "".join(part.strip() for part in prodnote.itertext()):
            for child in list(prodnote):
                prodnote.remove(child)
            prodnote.text = None
            placeholder_paragraph = etree.SubElement(prodnote, "p")
            placeholder_paragraph.text = "Tekst in afbeelding:"

    def _figure_has_caption_or_prodnote_text(self, image_group: etree._Element) -> bool:
        for child in image_group:
            if self._tag_name(child) not in {"caption", "prodnote"}:
                continue
            if "".join(part.strip() for part in child.itertext()):
                return True
        return False

    def _close_active_blockquote(self, context: ConversionContext) -> None:
        blockquote = context.active_blockquote
        if blockquote is None:
            return
        if not self._has_meaningful_content(blockquote):
            parent = blockquote.getparent()
            if parent is not None:
                parent.remove(blockquote)
        context.active_blockquote = None

    def _append_inline_content(
        self,
        target: etree._Element,
        source_node: etree._Element,
        context: ConversionContext,
        pm_mode: bool = False,
        strip_markup_tokens: bool = False,
        convert_inline_page_markers: bool = True,
    ) -> None:
        parts = self._iter_inline_parts(source_node)
        if strip_markup_tokens:
            parts = self._trim_semantic_marker_edge_parts(parts)

        for part_type, value in parts:
            if part_type == "text":
                self._append_text_fragments(
                    target,
                    value,
                    context,
                    pm_mode=pm_mode,
                    strip_markup_tokens=strip_markup_tokens,
                    convert_inline_page_markers=convert_inline_page_markers,
                )
            else:
                self._append_inline_node(
                    target,
                    value,
                    context,
                    pm_mode=pm_mode,
                    strip_markup_tokens=strip_markup_tokens,
                    convert_inline_page_markers=convert_inline_page_markers,
                )

    def _iter_inline_parts(self, source_node: etree._Element) -> list[tuple[str, str | etree._Element]]:
        parts: list[tuple[str, str | etree._Element]] = []
        text_buffer = source_node.text or ""

        for child in source_node:
            if self._is_named_anchor_without_href(child):
                text_buffer += "".join(child.itertext()) + (child.tail or "")
                continue

            if text_buffer:
                parts.append(("text", text_buffer))
                text_buffer = ""

            parts.append(("element", child))
            if child.tail:
                text_buffer += child.tail

        if text_buffer:
            parts.append(("text", text_buffer))
        return parts

    def _trim_semantic_marker_edge_parts(
        self,
        parts: list[tuple[str, str | etree._Element]],
    ) -> list[tuple[str, str | etree._Element]]:
        if not parts:
            return parts

        leading_skip = self._semantic_marker_edge_skip_count(parts, from_start=True)
        trimmed_parts = parts[leading_skip:]
        if not trimmed_parts:
            return []

        trailing_skip = self._semantic_marker_edge_skip_count(trimmed_parts, from_start=False)
        if trailing_skip:
            trimmed_parts = trimmed_parts[:-trailing_skip]
        return trimmed_parts

    def _semantic_marker_edge_skip_count(
        self,
        parts: list[tuple[str, str | etree._Element]],
        *,
        from_start: bool,
    ) -> int:
        accumulated_text = ""
        last_complete_boundary = 0
        iterable = parts if from_start else list(reversed(parts))

        for index, part in enumerate(iterable, start=1):
            visible_text = self._inline_part_visible_text(part)
            if not visible_text and part[0] == "element":
                break

            if from_start:
                accumulated_text += visible_text
                compact_text = self._compact_semantic_marker_text(accumulated_text)
                consumed_length = self._leading_semantic_token_text_length(compact_text)
            else:
                accumulated_text = f"{visible_text}{accumulated_text}"
                compact_text = self._compact_semantic_marker_text(accumulated_text)
                consumed_length = self._trailing_semantic_token_text_length(compact_text)

            if not compact_text:
                last_complete_boundary = index
                continue

            if consumed_length == len(compact_text):
                last_complete_boundary = index
                continue

            if last_complete_boundary:
                break

        return last_complete_boundary

    @staticmethod
    def _compact_semantic_marker_text(text: str) -> str:
        return re.sub(r"\s+", "", unescape(text).replace("\xa0", " "))

    @staticmethod
    def _leading_semantic_token_text_length(text: str) -> int:
        position = 0
        while position < len(text):
            match = SEMANTIC_TOKEN_TEXT_PATTERN.match(text, position)
            if match is None:
                break
            position = match.end()
        return position

    @staticmethod
    def _trailing_semantic_token_text_length(text: str) -> int:
        end_position = len(text)
        while end_position > 0:
            match_at_end: re.Match[str] | None = None
            for match in SEMANTIC_TOKEN_TEXT_PATTERN.finditer(text, 0, end_position):
                if match.end() == end_position:
                    match_at_end = match
            if match_at_end is None:
                break
            end_position = match_at_end.start()
        return len(text) - end_position

    def _inline_part_visible_text(self, part: tuple[str, str | etree._Element]) -> str:
        part_type, value = part
        if part_type == "text":
            return str(value)
        return "".join(value.itertext())

    def _append_inline_node(
        self,
        target: etree._Element,
        source_node: etree._Element,
        context: ConversionContext,
        pm_mode: bool = False,
        strip_markup_tokens: bool = False,
        convert_inline_page_markers: bool = True,
    ) -> None:
        tag = self._tag_name(source_node)
        if not tag:
            return

        if tag == "br":
            self._append_break_space(target)
            return

        if tag in VOID_TAGS:
            return

        if tag == "a" and source_node.get("name") and not source_node.get("href"):
            self._append_inline_content(
                target,
                source_node,
                context,
                pm_mode=pm_mode,
                strip_markup_tokens=True,
                convert_inline_page_markers=convert_inline_page_markers,
            )
            return

        if tag == "a":
            self._append_inline_content(
                target,
                source_node,
                context,
                pm_mode=pm_mode,
                strip_markup_tokens=strip_markup_tokens,
                convert_inline_page_markers=convert_inline_page_markers,
            )
            return

        if tag == "page":
            self._append_pagenum(target, "".join(source_node.itertext()).strip(), context)
            return

        font0_replacement = self._extract_font0_span_replacement(source_node)
        if font0_replacement is not None:
            if font0_replacement == " ":
                self._append_text_to_element(target, " ")
            else:
                self._append_text_fragments(target, font0_replacement, context, pm_mode=pm_mode)
            return

        if self._is_underlined_span(source_node):
            strong = etree.SubElement(target, "strong")
            emphasis = etree.SubElement(strong, "em")
            self._append_inline_content(emphasis, source_node, context, pm_mode=pm_mode, strip_markup_tokens=strip_markup_tokens)
            if not self._has_meaningful_content(emphasis):
                strong.remove(emphasis)
            if not self._has_meaningful_content(strong):
                target.remove(strong)
            return

        if tag in {"strong", "b"} or self._is_bold_span(source_node):
            special_marker = self._extract_special_marker(source_node)
            if special_marker:
                self._append_text_fragments(target, f"({special_marker})", context, pm_mode=pm_mode)
                return

            strong = etree.SubElement(target, "strong")
            self._append_inline_content(
                strong,
                source_node,
                context,
                pm_mode=pm_mode,
                strip_markup_tokens=strip_markup_tokens,
                convert_inline_page_markers=convert_inline_page_markers,
            )
            if not self._has_meaningful_content(strong):
                target.remove(strong)
            return

        if tag in {"em", "i"} or self._is_italic_span(source_node):
            emphasis = etree.SubElement(target, "em")
            self._append_inline_content(
                emphasis,
                source_node,
                context,
                pm_mode=pm_mode,
                strip_markup_tokens=strip_markup_tokens,
                convert_inline_page_markers=convert_inline_page_markers,
            )
            if not self._has_meaningful_content(emphasis):
                target.remove(emphasis)
            return

        if tag == "img":
            image_group = self._convert_image_group(source_node, target, context)
            self._ensure_image_group_accessibility_placeholders(image_group)
            return

        if tag == "span":
            self._append_inline_content(
                target,
                source_node,
                context,
                pm_mode=pm_mode,
                strip_markup_tokens=strip_markup_tokens,
                convert_inline_page_markers=convert_inline_page_markers,
            )
            return

        self._preserve_inline_source_element(
            target,
            source_node,
            context,
            pm_mode=pm_mode,
            strip_markup_tokens=strip_markup_tokens,
        )

    def _preserve_inline_source_element(
        self,
        target: etree._Element,
        source_node: etree._Element,
        context: ConversionContext,
        pm_mode: bool = False,
        strip_markup_tokens: bool = False,
    ) -> etree._Element:
        _ = pm_mode
        _ = strip_markup_tokens
        return self._clone_source_element_as_is(target, source_node, context, mark_root=True)

    def _preserve_block_source_element(
        self,
        parent: etree._Element,
        source_node: etree._Element,
        context: ConversionContext,
        strip_markup_tokens: bool = False,
    ) -> etree._Element:
        _ = strip_markup_tokens
        return self._clone_source_element_as_is(parent, source_node, context, mark_root=True)

    def _clone_source_element_as_is(
        self,
        parent: etree._Element,
        source_node: etree._Element,
        context: ConversionContext,
        mark_root: bool = False,
    ) -> etree._Element:
        tag = self._tag_name(source_node)
        preserved = etree.SubElement(parent, tag, **self._preserved_attributes(source_node))
        if mark_root:
            preserved.set(INTERNAL_PRESERVED_ATTR, "1")
        self._report_preserved_html_tag(tag, source_node, context)
        if source_node.text:
            self._append_raw_text_to_element(preserved, source_node.text)

        for child in source_node:
            if not self._tag_name(child):
                continue
            preserved_child = self._clone_source_element_as_is(preserved, child, context)
            if child.tail:
                preserved_child.tail = f"{preserved_child.tail or ''}{child.tail}"
        return preserved

    @staticmethod
    def _preserved_attributes(source_node: etree._Element) -> dict[str, str]:
        return {str(key): value for key, value in source_node.attrib.items()}

    def _report_preserved_html_tag(self, tag: str, source_node: etree._Element, context: ConversionContext) -> None:
        report_key = (context.current_file, tag)
        if report_key in context.preserved_tag_reports:
            return
        context.preserved_tag_reports.add(report_key)
        context.issues.append(
            ConversionIssue(
                severity=Severity.INFO,
                message=f"HTML tag <{tag}> has no dedicated DTBook rule and was preserved as-is in the XML output.",
                file_name=context.current_file,
                line=source_node.sourceline,
                tag=tag,
                code="preserved-html-tag",
            )
        )

    def _report_dropped_source_text(
        self,
        source_node: etree._Element,
        context: ConversionContext,
        *,
        reason: str,
    ) -> None:
        preview = self._source_text_preview(source_node)
        if not preview:
            return
        report_key = (context.current_file, source_node.sourceline, reason, preview)
        if report_key in context.dropped_text_reports:
            return
        context.dropped_text_reports.add(report_key)
        context.issues.append(
            ConversionIssue(
                severity=Severity.WARNING,
                message=f'Source text could not be converted and was removed from the XML output: "{preview}"',
                file_name=context.current_file,
                line=source_node.sourceline,
                code="dropped-source-text",
                tag=self._tag_name(source_node),
            )
        )

    def _source_text_preview(self, source_node: etree._Element) -> str:
        preview = self._strip_markup_tokens(" ".join(part.strip() for part in source_node.itertext() if part.strip()))
        if not preview:
            return ""
        return preview if len(preview) <= 140 else f"{preview[:137].rstrip()}..."

    @staticmethod
    def _is_likely_block_tag(tag: str) -> bool:
        if not tag:
            return False
        if tag in BLOCK_PRESERVE_HINT_TAGS or tag in TABLE_SECTION_TAGS:
            return True
        if tag in {"pm", "bl", "ft", "sd", "hsd", "figure", "fig", "page", "ol", "ul", "table"}:
            return True
        return bool(re.fullmatch(r"h[1-6]", tag))

    def _append_break_space(self, target: etree._Element) -> None:
        last_character = self._last_text_character(target)
        if not last_character or last_character.isspace():
            return
        self._append_text_to_element(target, " ")

    @classmethod
    def _last_text_character(cls, element: etree._Element) -> str:
        if len(element):
            last_child = element[-1]
            if last_child.tail:
                return last_child.tail[-1]
            return cls._last_text_character(last_child)
        if element.text:
            return element.text[-1]
        return ""

    def _append_text_fragments(
        self,
        target: etree._Element,
        text: str,
        context: ConversionContext,
        pm_mode: bool = False,
        strip_markup_tokens: bool = False,
        convert_inline_page_markers: bool = True,
    ) -> None:
        if not text:
            return

        decoded_text = unescape(text).replace("\xa0", " ")
        last_index = 0

        if convert_inline_page_markers:
            for match in INLINE_PAGE_MARKER_PATTERN.finditer(decoded_text):
                segment = decoded_text[last_index:match.start()]
                if strip_markup_tokens:
                    segment = MARKUP_TOKEN_PATTERN.sub("", segment)
                self._append_text_segment(target, segment, context)
                self._append_pagenum(target, (match.group("content") or "").strip(), context)
                last_index = match.end()

        remaining_text = decoded_text[last_index:]
        if strip_markup_tokens:
            remaining_text = MARKUP_TOKEN_PATTERN.sub("", remaining_text)
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
            if normalized and DTBookConverter._last_text_character(target) and not DTBookConverter._last_text_character(target).isspace():
                DTBookConverter._append_text_to_element(target, " ")
            return
        if len(target):
            target[-1].tail = f"{target[-1].tail or ''}{normalized}"
        else:
            target.text = f"{target.text or ''}{normalized}"

    def _append_pagenum(self, target: etree._Element, value: str, context: ConversionContext) -> None:
        cleaned = value.strip()
        effective_page_number = self._resolve_effective_page_number(cleaned, context)
        if context.page_range is not None:
            cleaned = str(effective_page_number)
        elif not cleaned:
            cleaned = str(effective_page_number)

        context.detected_pages.add(effective_page_number)

        context.current_page_number = cleaned
        page_type, page_id = self._build_page_attributes(cleaned)
        page_number = etree.SubElement(target, "pagenum", page=page_type, id=page_id)
        page_number.text = cleaned

    def _append_heading_text(
        self,
        target: etree._Element,
        source_node: etree._Element,
        context: ConversionContext,
        *,
        convert_inline_page_markers: bool = True,
    ) -> None:
        for part_type, value in self._trim_semantic_marker_edge_parts(self._iter_inline_parts(source_node)):
            if part_type == "text":
                self._append_text_fragments(
                    target,
                    value,
                    context,
                    strip_markup_tokens=True,
                    convert_inline_page_markers=convert_inline_page_markers,
                )
                continue

            child = value
            tag = self._tag_name(child)
            if tag == "br":
                self._append_break_space(target)
            elif tag == "page":
                self._append_text_fragments(
                    target,
                    "".join(child.itertext()),
                    context,
                    strip_markup_tokens=True,
                    convert_inline_page_markers=convert_inline_page_markers,
                )
            else:
                self._append_inline_node(
                    target,
                    child,
                    context,
                    strip_markup_tokens=True,
                    convert_inline_page_markers=convert_inline_page_markers,
                )

    def _has_renderable_inline_content(self, source_node: etree._Element) -> bool:
        for part_type, value in self._trim_semantic_marker_edge_parts(self._iter_inline_parts(source_node)):
            if part_type == "text":
                cleaned_text = MARKUP_TOKEN_PATTERN.sub("", unescape(str(value)).replace("\xa0", " "))
                if cleaned_text.strip():
                    return True
                continue

            child = value
            tag = self._tag_name(child)
            if tag == "span":
                if self._has_renderable_inline_content(child):
                    return True
                continue
            if tag == "br":
                continue
            return True

        return False

    @staticmethod
    def _append_text_to_element(target: etree._Element, text: str) -> None:
        if not text:
            return
        if len(target):
            target[-1].tail = f"{target[-1].tail or ''}{text}"
        else:
            target.text = f"{target.text or ''}{text}"

    @staticmethod
    def _append_raw_text_to_element(target: etree._Element, text: str) -> None:
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
        paragraph = self._create_paragraph(parent, context)
        self._append_text_fragments(paragraph, cleaned_text, context, strip_markup_tokens=True)
        if not self._has_meaningful_content(paragraph):
            parent.remove(paragraph)

    @staticmethod
    def _create_paragraph(parent: etree._Element, context: ConversionContext) -> etree._Element:
        attributes: dict[str, str] = {}
        if context.pending_precedingemptyline:
            attributes["class"] = "precedingemptyline"
            context.pending_precedingemptyline = False
        return etree.SubElement(parent, "p", **attributes)

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

    @classmethod
    def _is_named_anchor_without_href(cls, node: etree._Element) -> bool:
        return cls._tag_name(node) == "a" and bool(node.get("name")) and not node.get("href")

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

    @staticmethod
    def _is_underlined_span(node: etree._Element) -> bool:
        tag = node.tag.lower() if isinstance(node.tag, str) else ""
        if tag != "span":
            return False
        style = (node.get("style") or "").replace(" ", "").lower()
        return "text-decoration:underline" in style or "text-decoration-line:underline" in style

    def _extract_special_marker(self, node: etree._Element) -> str:
        candidate = MARKUP_TOKEN_PATTERN.sub("", "".join(node.itertext())).strip()
        return candidate if candidate in SPECIAL_MARKER_VALUES else ""

    def _extract_font0_span_replacement(self, node: etree._Element) -> str | None:
        tag = node.tag.lower() if isinstance(node.tag, str) else ""
        if tag != "span":
            return None

        classes = {part.strip().lower() for part in (node.get("class") or "").split() if part.strip()}
        if "font0" not in classes:
            return None

        raw_text = "".join(node.itertext())
        stripped_text = MARKUP_TOKEN_PATTERN.sub("", raw_text).strip()
        if stripped_text in SPECIAL_MARKER_VALUES:
            return f"({stripped_text})"
        if raw_text and not raw_text.strip():
            return " "
        return None

    @staticmethod
    def _is_caption_candidate(node: etree._Element) -> bool:
        tag = node.tag.lower() if isinstance(node.tag, str) else ""
        if tag in {"figcaption", "caption"}:
            return True
        if tag != "p":
            return False
        if not "".join(part.strip() for part in node.itertext()):
            return False
        blocked_tags = {"blockquote", "imggroup", "linegroup", "list", "pagenum", "poem", "sidebar", "table"}
        return not any(DTBookConverter._tag_name(child) in blocked_tags for child in node.iterdescendants())

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
                if self._is_within_preserved_subtree(element):
                    continue
                if self._merge_adjacent_emphasis(element):
                    changed = True

        for element in list(root.iter()):
            if self._is_within_preserved_subtree(element):
                continue
            self._remove_heading_formatting(element)

        for element in list(root.iter()):
            if self._is_within_preserved_subtree(element):
                continue
            self._fix_misplaced_bracketed_inline_markup(element)

        for element in list(root.iter()):
            if self._is_within_preserved_subtree(element):
                continue
            self._normalize_element_text_nodes(element)

        self._hoist_pagenums_outside_paragraphs(root)

    @staticmethod
    def _is_within_preserved_subtree(element: etree._Element) -> bool:
        current = element
        while current is not None:
            if current.get(INTERNAL_PRESERVED_ATTR) == "1":
                return True
            current = current.getparent()
        return False

    @staticmethod
    def _clear_internal_preservation_markers(root: etree._Element) -> None:
        for element in root.iter():
            element.attrib.pop(INTERNAL_PRESERVED_ATTR, None)

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
                index += 1
                continue
            if current.tail:
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

        blocked_tags = {"blockquote", "imggroup", "linegroup", "list", "pagenum", "poem", "sidebar", "table"}
        return not any(self._tag_name(child) in blocked_tags for child in element.iterdescendants())

    def _remove_heading_formatting(self, element: etree._Element) -> None:
        tag = self._tag_name(element)
        if tag not in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            return

        for child in list(element):
            if self._tag_name(child) not in {"strong", "span", "b"}:
                continue
            self._unwrap_heading_formatting_child(element, child)

    def _unwrap_heading_formatting_child(self, parent: etree._Element, child: etree._Element) -> None:
        child_index = parent.index(child)
        if child.text:
            self._append_text_before_child(parent, child_index, child.text)

        insertion_index = child_index
        for grandchild in list(child):
            child.remove(grandchild)
            parent.insert(insertion_index, grandchild)
            insertion_index += 1

        trailing_text = child.tail
        parent.remove(child)
        if trailing_text:
            self._append_text_before_child(parent, insertion_index, trailing_text)

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
            existing_text = parent.text or ""
        else:
            existing_text = parent[child_index - 1].tail or ""
        if (
            existing_text
            and not existing_text[-1].isspace()
            and not text[0].isspace()
            and text[0] not in ",.;:!?)]}>-–—/"
        ):
            text = f" {text}"
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
        if element.tail[0].isspace() or element.tail[0] in ",.;:!?)]}>-–—/":
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

    def _hoist_pagenums_outside_paragraphs(self, root: etree._Element) -> None:
        for paragraph in list(root.iter()):
            if self._tag_name(paragraph) != "p" or self._is_within_preserved_subtree(paragraph):
                continue
            if not any(self._tag_name(child) == "pagenum" for child in paragraph):
                continue
            self._split_paragraph_around_pagenums(paragraph)

    def _split_paragraph_around_pagenums(self, paragraph: etree._Element) -> None:
        parent = paragraph.getparent()
        if parent is None:
            return

        paragraph_attributes = dict(paragraph.attrib)
        fragments: list[etree._Element] = []
        insertion_nodes: list[etree._Element] = []

        def current_fragment() -> etree._Element:
            if fragments:
                return fragments[-1]
            fragment = etree.Element("p", **paragraph_attributes)
            fragments.append(fragment)
            return fragment

        if paragraph.text:
            current_fragment().text = paragraph.text

        for child in list(paragraph):
            paragraph.remove(child)
            if self._tag_name(child) == "pagenum":
                if fragments and self._has_meaningful_content(fragments[-1]):
                    insertion_nodes.append(fragments.pop())
                elif fragments:
                    fragments.pop()
                insertion_nodes.append(child)
                if child.tail:
                    next_fragment = etree.Element("p", **paragraph_attributes)
                    next_fragment.text = child.tail
                    fragments.append(next_fragment)
                    child.tail = None
                continue

            fragment = current_fragment()
            fragment.append(child)

        if fragments and self._has_meaningful_content(fragments[-1]):
            insertion_nodes.append(fragments.pop())

        paragraph_index = parent.index(paragraph)
        parent.remove(paragraph)
        for offset, node in enumerate(insertion_nodes):
            parent.insert(paragraph_index + offset, node)

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

    @staticmethod
    def _build_page_attributes(page_value: str) -> tuple[str, str]:
        cleaned = page_value.strip()
        normalized_identifier = re.sub(r"[^0-9A-Za-z_-]+", "-", cleaned.lower()).strip("-") or "unknown"
        if re.fullmatch(r"\d+[A-Za-z]+", cleaned):
            return ("special", f"page-{normalized_identifier}")
        if re.fullmatch(r"[ivxlcdm]+", cleaned, re.IGNORECASE):
            return ("front", f"page-{normalized_identifier}")
        return ("normal", f"page-{normalized_identifier}")

    def _cleanup_empty_elements(self, root: etree._Element) -> None:
        removable_tags = {
            "p",
            "line",
            "caption",
            "list",
            "li",
            "imggroup",
            "blockquote",
            "sidebar",
            "poem",
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
                if self._is_within_preserved_subtree(element):
                    continue
                if local_name == "caption" and self._should_preserve_empty_caption(element):
                    continue
                if self._has_meaningful_content(element):
                    continue
                parent = element.getparent()
                if parent is not None:
                    parent.remove(element)
                    changed = True

    def _should_preserve_empty_caption(self, element: etree._Element) -> bool:
        if self._tag_name(element) != "caption":
            return False
        parent = element.getparent()
        if parent is None or self._tag_name(parent) != "imggroup":
            return False
        return any(self._tag_name(child) == "prodnote" for child in parent)
