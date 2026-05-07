from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from PyQt6.QtWidgets import QApplication
from lxml import etree

from technocops_ddc.models import AuthorEntry, DEFAULT_PRODUCER, DTBookMetadata, InputDocument, PageRangeSelection
from technocops_ddc.services.conversion_service import ConversionService
from technocops_ddc.services.file_service import InputCollectionService
from technocops_ddc.services.html_validation import HtmlSourceValidator
from technocops_ddc.services.license_service import LicenseService, LicenseState
from technocops_ddc.services.security_service import SecurityService
from technocops_ddc.services.update_service import UpdateService
from technocops_ddc.ui.main_window import MainWindow
from technocops_ddc.ui.widgets import MetadataForm


def main() -> int:
    parser = argparse.ArgumentParser(description="Run release smoke checks for the Technocops desktop application.")
    parser.add_argument("--phase", choices=("prebuild", "postbuild"), required=True)
    parser.add_argument("--dist-root", help="Path to the built portable bundle for post-build checks.")
    args = parser.parse_args()

    print(f"[release-check] phase={args.phase}")
    app = QApplication.instance() or QApplication([])
    try:
        run_ui_smoke_test()
        run_conversion_smoke_test()
        run_license_smoke_test()
        run_security_smoke_test()
        run_update_service_smoke_test()
        if args.phase == "postbuild":
            if not args.dist_root:
                raise SystemExit("--dist-root is required for postbuild checks.")
            run_distribution_check(Path(args.dist_root))
    finally:
        app.quit()

    print("[release-check] all checks passed")
    return 0


def run_ui_smoke_test() -> None:
    window = MainWindow()
    metadata_form = MetadataForm()
    assert "Release-1.0.0" in window.windowTitle(), "Window title should expose the production release label."
    assert metadata_form.doc_type_input.itemText(0) == "Select document type", "Document type placeholder is missing."
    assert metadata_form.doc_type_input.itemText(1) == "Educational Books", "Educational Books option is missing."
    assert metadata_form.doc_type_input.itemText(2) == "Reading Books", "Reading Books option is missing."
    assert metadata_form.doc_type_input.currentData() == "", "Document type should not be preselected."
    assert window.page_range_widget.start_spin.value() == 1, "Generated page numbering should start at 1 by default."
    assert metadata_form.uid_input.text() == "", "UID should no longer be pre-populated."
    assert metadata_form.identifier_input.text() == "", "Identifier should no longer be pre-populated."
    assert metadata_form.title_input.text() == "", "Title should no longer be pre-populated."
    assert metadata_form.language_input.text() == "", "Language should no longer be pre-populated before detection."
    assert metadata_form.publisher_input.text() == "Dedicon", "Publisher should stay fixed as Dedicon in the editor."
    assert metadata_form.producer_input.text() == DEFAULT_PRODUCER, "Producer should be pre-filled for new documents."
    assert metadata_form.producer_input.placeholderText() == DEFAULT_PRODUCER, "Producer placeholder should guide the user."
    assert metadata_form.generate_ids_button.property("state") == "idle", "Generate IDs button should start in the default state."
    assert metadata_form.completion_date_input.calendarPopup(), "Completion date should use a calendar popup."
    assert metadata_form.produced_date_input.calendarPopup(), "Produced date should use a calendar popup."
    metadata_form.uid_input.setText("374388")
    metadata_form.identifier_input.setText("374388")
    metadata_form.generate_ids()
    assert metadata_form.uid_input.text() == "374388", "Generate IDs should not replace an existing UID with a random value."
    assert metadata_form.identifier_input.text() == "374388", "Generate IDs should not replace an existing Identifier with a random value."
    assert metadata_form.generate_ids_button.property("state") == "success", "Generate IDs should visibly confirm a successful click."
    assert window.stop_on_critical_checkbox.text(), "Main window checkbox should be present."
    assert window.validate_html_button.text() == "Validate HTML", "Main window should expose a dedicated HTML validation action."
    assert window.validate_html_button.property("variant") == "validator", "HTML validation action should use its dedicated accent styling."
    assert not window.id_regeneration_widget.page_ids_checkbox.isEnabled(), "ID regeneration should be disabled before XML is available."
    assert not window.id_regeneration_widget.apply_button.isEnabled(), "Apply ID finalizer should be disabled before XML is available."
    window.metadata_form.uid_input.setText("374388")
    window.metadata_form.title_input.setText("Temp title")
    window.clear_documents()
    assert window.metadata_form.uid_input.text() == "", "Clearing imported files should also clear metadata."
    assert window.metadata_form.title_input.text() == "", "Metadata reset should clear the previous document title."
    assert window.metadata_form.publisher_input.text() == "Dedicon", "Publisher should remain fixed after metadata reset."
    assert window.metadata_form.producer_input.text() == DEFAULT_PRODUCER, "Metadata reset should restore the default producer."
    assert window.metadata_form.generate_ids_button.property("state") == "idle", "Metadata reset should clear the Generate IDs success state."
    assert window.metadata_dialog.clean_button.text() == "Clean Metadata", "Metadata dialog should expose a clean button."
    window.xml_source_path = PROJECT_ROOT / "tmp_release_checks" / "sample.htm"
    auto_output_path = window._build_auto_output_path("374388")
    assert auto_output_path == PROJECT_ROOT / "tmp_release_checks" / "output" / "374388.xml", "Save XML should target an auto-created output folder beside the source file."
    window.close()
    print("[release-check] UI smoke test passed")


def run_conversion_smoke_test() -> None:
    temp_parent = PROJECT_ROOT / "tmp_release_checks"
    temp_parent.mkdir(parents=True, exist_ok=True)
    temp_root = temp_parent / "case"
    if temp_root.exists():
        shutil.rmtree(temp_root, ignore_errors=True)
    temp_root.mkdir(parents=True, exist_ok=True)
    try:
        html_path = temp_root / "sample.htm"
        image_path = temp_root / "sample.jpg"
        output_path = temp_root / "output" / "output.xml"

        image_path.write_bytes(b"\xff\xd8\xff\xd9")
        html_path.write_text(
            """
            <html>
              <body>
                <p><page>1</page></p>
                <h1><span class="font2">&lt;h1&gt;</span><strong>Chapter One</strong><span class="font2">&lt;/h1&gt;</span></h1>
                <p><span style="font-weight:bold;">Bold text</span> and <span style="font-style:italic;">Italic text</span>.</p>
                <p>Het <span class="font20" style="text-decoration:underline;">HANDBOEK</span> helpt.</p>
                <p><strong>Only Bold</strong></p>
                <p>(R)Ik weet wat...</p>
                <p>en niet-feitelijke zaken.</p>
                <p><strong>► </strong>Marker</p>
                <ul>
                  <li><strong>d </strong>Leg in je eigen</li>
                  <li>dichtvorm uit.</li>
                </ul>
                <pm><p>[1]Verse line</p></pm>
                <hsd><p>Sidebar note</p></hsd>
                <p><img src="sample.jpg"/></p>
                <table border="1"><tr><td colspan="2" rowspan="3"><p>Cell text</p></td></tr></table>
                <p><em>Joined</em><em>Emphasis</em></p>
                <p><page>2</page>Second page text.</p>
              </body>
            </html>
            """,
            encoding="utf-8",
        )

        metadata = DTBookMetadata(
            uid="374388",
            title="Release Smoke Test",
            creator_surname="Tester",
            creator_first_name="Release",
            completion_date="2026-04-17",
            publisher="Technocops Technology & Innovation",
            language="en",
            identifier="374388",
            source_isbn="978 12-3456 7890 1",
            produced_date="2026-04-17",
            source_publisher="Technocops Technology & Innovation",
            producer="Technocops Technology & Innovation",
            authors=[AuthorEntry(surname="Tester", first_name="Release")],
            doc_type="sv",
        )
        documents = [InputDocument(path=html_path, order=1, origin=str(temp_root))]
        xhtml_path = temp_root / "sample.xhtml"
        xhtml_path.write_text("<html><body><p>XHTML sample</p></body></html>", encoding="utf-8")
        assert InputCollectionService.is_supported_html(xhtml_path), "XHTML files should be accepted as supported input."
        relaxed_metadata = DTBookMetadata(
            uid="374388",
            title="",
            creator_surname="",
            creator_first_name="",
            completion_date="2026-04-17",
            publisher="Dedicon",
            language="",
            identifier="",
            source_isbn="",
            produced_date="2026-04-17",
            source_publisher="",
            producer="",
            doc_type="",
        )

        service = ConversionService()
        assert service.validate_metadata(relaxed_metadata) == [], "Only UID should remain required for XML generation."
        assert service.validate_metadata(DTBookMetadata(uid="", title="", creator_surname="", creator_first_name="", completion_date="2026-04-17", publisher="Dedicon", language="", identifier="", source_isbn="", produced_date="2026-04-17", source_publisher="", producer="", doc_type="")) == ["UID"], "Missing UID should still block conversion."
        result = service.convert(documents, metadata)
        saved_output = service.save_output(output_path, result)
        xml_text = result.xml_text
        xml_root = etree.fromstring(xml_text.encode("utf-8"))

        assert "<dtbook" in xml_text, "DTBook root tag missing."
        assert re.search(r"<strong>\s*Bold text\s*</strong>", xml_text), "Bold conversion missing."
        assert re.search(r"<em>\s*Italic text\s*</em>", xml_text), "Italic conversion missing."
        assert "<h1>Chapter One</h1>" in xml_text, "Heading cleanup failed."
        assert xml_root.xpath("count(.//*[local-name()='h1']/*[local-name()='strong'])") == 0.0, "Heading should not contain nested strong tags."
        assert "<strong><em>HANDBOEK</em></strong>" in xml_text, "Underlined text should convert to strong+em."
        assert "<p><strong>Only Bold</strong></p>" in xml_text, "Strong paragraph closing tag formatting failed."
        assert "<p>(R) Ik weet wat...</p>" in xml_text, "First paragraph should remain independent and preserve bracket spacing."
        assert "<p>en niet-feitelijke zaken.</p>" in xml_text, "Second paragraph should remain independent."
        assert re.search(r"<strong>.+?</strong>\s*Marker", xml_text, re.DOTALL), "Strong trailing-space cleanup failed."
        assert "<poem>" in xml_text and "<linegroup>" in xml_text, "PM block conversion should wrap lines inside a poem."
        assert re.search(r"<linenum>\(1\)</linenum>\s*Verse line", xml_text), "Line number spacing cleanup failed."
        assert '<sidebar render="required">' in xml_text, "Sidebar conversion missing."
        assert '<img src="img/cover.jpg" alt="afbeelding"/>' in xml_text, "Image conversion missing."
        assert xml_root.xpath("count(.//*[local-name()='list' and @class='ul-nobullets' and @type='pl'])") == 1.0, "List conversion missing."
        assert xml_root.xpath("count(.//*[local-name()='pagenum' and text()='1'])") >= 1.0, "Page number conversion missing."
        assert re.search(r"<td>\s*Cell text\s*</td>", xml_text), "Table cell paragraph cleanup failed."
        assert "<td><p>" not in xml_text, "Paragraph tags should not remain inside table cells."
        assert re.search(r"<li>\s*<strong>d</strong>\s*Leg in je eigen\s*</li>", xml_text), "First list item should remain independent."
        assert re.search(r"<li>\s*dichtvorm uit\.\s*</li>", xml_text), "Second list item should remain independent."
        assert re.search(r"<em>\s*Joined Emphasis\s*</em>", xml_text), "Adjacent emphasis cleanup failed."
        assert '<meta name="dc:Publisher" content="Dedicon"/>' in xml_text, "Publisher should always be fixed to Dedicon."
        assert '<meta name="dc:Source" content="97812345678901"/>' in xml_text, "ISBN should be saved without spaces and dashes."
        assert " </strong>" not in xml_text, "Space before strong closing tag should be removed."
        assert "\t" not in xml_text, "XML output should not contain tab indentation."
        assert not re.search(r"(?m)^[ ]+<", xml_text), "XML output should be left-aligned without leading spaces."
        assert 'colspan=' not in xml_text and 'rowspan=' not in xml_text, "Table span attributes should be removed."

        assert saved_output.xml_path.exists(), "Converted XML file was not written."
        assert saved_output.output_dir.exists(), "Output folder was not created automatically."
        assert saved_output.output_dir == temp_root / "output", "Converted XML should be saved inside the output folder."
        assert saved_output.text_report_path.exists(), "Text report was not written."
        assert not output_path.with_suffix(".report.json").exists(), "JSON report should no longer be generated."
        assert saved_output.image_output_dir is not None and any(saved_output.image_output_dir.iterdir()), "Image assets were not copied."
        assert not result.has_critical_errors, "Conversion smoke test produced critical errors."

        escaped_heading_html = temp_root / "escaped-heading.htm"
        escaped_heading_html.write_text(
            """
            <html><body>
              <h2>&lt;h2&gt; <strong>A De kunst van het redeneren</strong> &lt;/h2&gt;</h2>
              <ul class="existing-list"><li>Item one</li></ul>
            </body></html>
            """,
            encoding="utf-8",
        )
        escaped_heading_result = service.convert(
            [InputDocument(path=escaped_heading_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert "<h2>A De kunst van het redeneren</h2>" in escaped_heading_result.xml_text, "Escaped heading tokens were not removed."
        assert "&lt;h2&gt;" not in escaped_heading_result.xml_text and "&lt;/h2&gt;" not in escaped_heading_result.xml_text, "Heading output still contains escaped heading tags."
        assert '<list type="pl" class="existing-list ul-nobullets">' in escaped_heading_result.xml_text, "UL class appending did not preserve existing classes."

        bracket_inline_html = temp_root / "bracket-inline.htm"
        bracket_inline_html.write_text(
            """
            <html><body>
              <p>[<em>a]</em></p>
              <p><em>[b]</em></p>
              <p>(<strong>c)</strong></p>
              <p><strong>{d}</strong></p>
              <p>&lt;<em>e&gt;</em></p>
              <p><span style="font-style:italic;">&lt;[f]&gt;</span></p>
              <p><span style="font-style:italic;"><span style="font-weight:bold;">{g}</span></span></p>
            </body></html>
            """,
            encoding="utf-8",
        )
        bracket_inline_result = service.convert(
            [InputDocument(path=bracket_inline_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert "[<em>a</em>]" in bracket_inline_result.xml_text, "Closing square bracket should remain outside emphasis."
        assert "[<em>b</em>]" in bracket_inline_result.xml_text, "Opening and closing square brackets should remain outside emphasis."
        assert "(<strong>c</strong>)" in bracket_inline_result.xml_text, "Round brackets should remain outside strong formatting."
        assert "{<strong>d</strong>}" in bracket_inline_result.xml_text, "Curly brackets should remain outside strong formatting."
        assert "&lt;<em>e</em>&gt;" in bracket_inline_result.xml_text, "Angle brackets should remain outside emphasis."
        assert "&lt;[<em>f</em>]&gt;" in bracket_inline_result.xml_text, "Nested angle and square brackets should wrap the emphasized content."
        assert re.search(r"\{<em>\s*<strong>g</strong>\s*</em>\}", bracket_inline_result.xml_text), "Nested strong and emphasis should stay inside curly brackets."
        assert "<em>[" not in bracket_inline_result.xml_text and "]</em>" not in bracket_inline_result.xml_text, "Bracket characters should stay outside emphasis tags."
        assert "<strong>{" not in bracket_inline_result.xml_text and "}</strong>" not in bracket_inline_result.xml_text, "Bracket characters should stay outside strong tags."

        page_range_result = service.convert(documents, metadata, page_range=PageRangeSelection(start_page=1001))
        assert 'page-1001' in page_range_result.xml_text and 'page-1002' in page_range_result.xml_text, "Generated pages should start from the requested number and continue automatically."
        assert 'page-1"' not in page_range_result.xml_text and 'page-2"' not in page_range_result.xml_text, "Original source page numbers should not be reused when a generated start page is selected."
        assert "Chapter One" in page_range_result.xml_text and "Second page text." in page_range_result.xml_text, "Generated page numbering must not skip converted content."

        blank_marker_html = temp_root / "blank-pages.htm"
        blank_marker_html.write_text(
            """
            <html><body>
              <p><page></page></p>
              <p>Alpha</p>
              <p><page></page></p>
              <p>Beta</p>
              <p><page></page></p>
              <p>Gamma</p>
            </body></html>
            """,
            encoding="utf-8",
        )
        blank_documents = [InputDocument(path=blank_marker_html, order=1, origin=str(temp_root))]
        ranged_blank_result = service.convert(blank_documents, metadata, page_range=PageRangeSelection(start_page=1001))
        assert "page-1001" in ranged_blank_result.xml_text and "page-1002" in ranged_blank_result.xml_text and "page-1003" in ranged_blank_result.xml_text, "Blank page markers should continue automatically from the requested generated start page."

        br_spacing_html = temp_root / "br-spacing.htm"
        br_spacing_html.write_text(
            """
            <html><body>
              <p><span class="font1">Alle rechten voorbehouden, inclusief het recht van reproductie<br>in zijn geheel of in gedeelten, in welke vorm dan ook.</span></p>
            </body></html>
            """,
            encoding="utf-8",
        )
        br_spacing_result = service.convert(
            [InputDocument(path=br_spacing_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert "reproductie in zijn geheel" in br_spacing_result.xml_text, "Line breaks created by <br> should become a single visible space."

        marker_poem_html = temp_root / "marker-poem.htm"
        marker_poem_html.write_text(
            """
            <html><body>
              <p><span class="font5">&lt;pm&gt;</span></p>
              <p><span class="font2" style="font-style:italic;">Het leven van de kunstenaar, o vrouwe, is in</span></p>
              <p><span class="font2" style="font-style:italic;">zijn sterflijkheid van korter duur</span></p>
              <p><span class="font5">&lt;/pm&gt;</span></p>
            </body></html>
            """,
            encoding="utf-8",
        )
        marker_poem_result = service.convert(
            [InputDocument(path=marker_poem_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert re.search(r"<poem>\s*<linegroup>\s*<line><em>Het leven van de kunstenaar, o vrouwe, is in</em></line>\s*<line><em>zijn sterflijkheid van korter duur</em></line>\s*</linegroup>\s*</poem>", marker_poem_result.xml_text), "Marker-based poems should convert into poem > linegroup > line blocks."
        marker_poem_report = service._build_text_report(marker_poem_result.issues)
        assert "No declaration for element poem" not in marker_poem_report, "Poem declaration errors should be hidden from the text report."

        sidebar_html = temp_root / "sidebar.htm"
        sidebar_html.write_text(
            """
            <html><body>
              <sd><p>ABC</p></sd>
              <hsd><p>XYZ</p></hsd>
            </body></html>
            """,
            encoding="utf-8",
        )
        sidebar_result = service.convert(
            [InputDocument(path=sidebar_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert sidebar_result.xml_text.count('<sidebar render="required">') == 2, "Both sd and hsd blocks should convert into required sidebars."
        assert re.search(r"<sidebar render=\"required\">\s*<p>ABC</p>\s*</sidebar>", sidebar_result.xml_text), "Direct sd blocks should retain their paragraph content."

        blockquote_html = temp_root / "blockquote.htm"
        blockquote_html.write_text(
            """
            <html><body>
              <p><span class="font5">&lt;bl&gt;</span></p>
              <p><span class="font3">Michelangelo was een viespeuk die zelden van kleren wisselde en maanden in hetzelfde versleten plunje rondliep.</span></p>
              <p><span class="font5">&lt;/bl&gt;</span></p>
            </body></html>
            """,
            encoding="utf-8",
        )
        blockquote_result = service.convert(
            [InputDocument(path=blockquote_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert re.search(r"<blockquote>\s*<p>Michelangelo was een viespeuk die zelden van kleren wisselde en maanden in hetzelfde versleten plunje rondliep\.</p>\s*</blockquote>", blockquote_result.xml_text), "Blockquote markers should convert into DTBook blockquote elements."

        marker_figure_without_image_html = temp_root / "marker-figure-without-image.htm"
        marker_figure_without_image_html.write_text(
            """
            <html><body>
              <p><span class="font1">&lt;fig&gt;</span></p>
              <p><span class="font1" style="font-weight:bold;">Figuur 1.7 </span><span class="font1">Basson model<sup>24</sup></span></p>
              <div><p><span class="font0">Context = voorwaarden</span></p></div>
              <p><span class="font4">&lt;/fig&gt;</span></p>
            </body></html>
            """,
            encoding="utf-8",
        )
        marker_figure_without_image_result = service.convert(
            [InputDocument(path=marker_figure_without_image_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert "<imggroup>" in marker_figure_without_image_result.xml_text, "Figure wrappers without image calls should still produce an imggroup."
        assert "<caption>" in marker_figure_without_image_result.xml_text, "Text-only figure wrappers should keep their content inside a caption."
        assert "<sup>24</sup>" in marker_figure_without_image_result.xml_text, "Superscript content inside image wrappers should not be dropped."
        assert "Context = voorwaarden" in marker_figure_without_image_result.xml_text, "Figure wrapper text should stay in the caption when no image call exists."
        assert '<img src="' not in marker_figure_without_image_result.xml_text, "No synthetic image tag should be created when the wrapper has no image call."
        missing_figure_issue = next(
            (issue for issue in marker_figure_without_image_result.issues if issue.code == "missing-figure-image-call"),
            None,
        )
        assert missing_figure_issue is not None and missing_figure_issue.line is not None, "Missing-image wrappers should produce a warning with a line number."

        footnote_marker_html = temp_root / "footnote-marker.htm"
        footnote_marker_html.write_text(
            """
            <html><body>
              <p>&lt;ft&gt;</p>
              <p>1 Witte<em>, Belgische republikeinen. Radicalen tussen twee revoluties, 1830-1850</em>, Antwerpen, 2020.</p>
              <p>&lt;/ft&gt;</p>
            </body></html>
            """,
            encoding="utf-8",
        )
        footnote_marker_result = service.convert(
            [InputDocument(path=footnote_marker_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert re.search(r'<note id="fn_1_1">\s*<p>1 Witte<em>, Belgische republikeinen\. Radicalen tussen twee revoluties, 1830-1850</em>, Antwerpen, 2020\.</p>\s*</note>', footnote_marker_result.xml_text), "Footnote markers should convert into note blocks with generated IDs."

        inline_closed_footnote_html = temp_root / "footnote-inline-close.htm"
        inline_closed_footnote_html.write_text(
            """
            <html><body>
              <p><span class="font2">&lt;ft&gt;A first note.</span></p>
              <p><span class="font2">B second line.&lt;/ft&gt;</span></p>
              <p><span class="font3">Outside paragraph.</span></p>
            </body></html>
            """,
            encoding="utf-8",
        )
        inline_closed_footnote_result = service.convert(
            [InputDocument(path=inline_closed_footnote_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert re.search(r'<note id="fn_1_a">\s*<p>A first note\.</p>\s*<p>B second line\.</p>\s*</note>\s*<p>Outside paragraph\.</p>', inline_closed_footnote_result.xml_text), "Inline </ft> closers should end the note immediately and keep following paragraphs outside the footnote."

        multi_digit_footnote_html = temp_root / "footnote-multi-digit.htm"
        multi_digit_footnote_html.write_text(
            """
            <html><body>
              <p><span class="font10">&lt;ft&gt;</span></p>
              <p><span class="font0">12 </span><span class="font9">Janssens P., sample footnote.</span></p>
              <p><span class="font10">&lt;/ft&gt;</span></p>
            </body></html>
            """,
            encoding="utf-8",
        )
        multi_digit_footnote_result = service.convert(
            [InputDocument(path=multi_digit_footnote_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert '<note id="fn_1_12">' in multi_digit_footnote_result.xml_text, "Multi-digit footnote markers should be preserved fully in the note ID."

        symbol_footnote_html = temp_root / "footnote-symbol.htm"
        symbol_footnote_html.write_text(
            """
            <html><body>
              <p>&lt;ft&gt;</p>
              <p>* Symbol footnote</p>
              <p>&lt;/ft&gt;</p>
              <p>&lt;ft&gt;</p>
              <p>** Double symbol footnote</p>
              <p>&lt;/ft&gt;</p>
            </body></html>
            """,
            encoding="utf-8",
        )
        symbol_footnote_result = service.convert(
            [InputDocument(path=symbol_footnote_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert '<note id="fn_1_1">' in symbol_footnote_result.xml_text, "The first symbol-based footnote should use a numeric marker sequence."
        assert '<note id="fn_2_2">' in symbol_footnote_result.xml_text, "The second symbol-based footnote should increment the numeric marker sequence."

        hr_marker_html = temp_root / "hr-marker.htm"
        hr_marker_html.write_text(
            """
            <html><body>
              <p><span class="font2">&lt;hr/&gt;</span></p>
              <p><span class="font8">Bron: HANS DE BRUIJN, </span><span class="font8" style="font-style:italic;">Framing</span><span class="font8">. </span><span class="font8" style="font-style:italic;">Over de macht van taal in de politiek.</span><span class="font8"> Atlas Contact (2011).</span></p>
            </body></html>
            """,
            encoding="utf-8",
        )
        hr_marker_result = service.convert(
            [InputDocument(path=hr_marker_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert re.search(r'<p class="precedingemptyline">Bron: HANS DE BRUIJN, <em>Framing</em>\. <em>Over de macht van taal in de politiek\.</em> Atlas Contact \(2011\)\.</p>', hr_marker_result.xml_text), "Escaped hr markers should apply precedingemptyline to the next paragraph only."

        inline_preserve_html = temp_root / "inline-preserve.htm"
        inline_preserve_html.write_text(
            """
            <html><body>
              <p>I am Vikash<sup>10</sup> and H<sub>2</sub>O with <code class="chem">Na+</code> plus <a href="https://example.com">link</a>.</p>
            </body></html>
            """,
            encoding="utf-8",
        )
        inline_preserve_result = service.convert(
            [InputDocument(path=inline_preserve_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert "<sup>10</sup>" in inline_preserve_result.xml_text, "Superscript tags should be preserved as-is."
        assert "<sub>2</sub>" in inline_preserve_result.xml_text, "Subscript tags should be preserved as-is."
        assert "</sup>\n</p>" not in inline_preserve_result.xml_text, "Superscript closing tags should stay inline with the paragraph end tag."
        assert "</sub>\n</p>" not in inline_preserve_result.xml_text, "Subscript closing tags should stay inline with the paragraph end tag."
        assert '<code class="chem">Na+</code>' in inline_preserve_result.xml_text, "Inline code tags and attributes should be preserved as-is."
        assert "<p>I am Vikash<sup>10</sup> and H<sub>2</sub>O with <code class=\"chem\">Na+</code> plus link.</p>" in inline_preserve_result.xml_text, "Anchor hyperlinks should be removed while preserving the visible link text."
        preserved_inline_tags = {issue.tag for issue in inline_preserve_result.issues if issue.code == "preserved-html-tag"}
        assert "code" in preserved_inline_tags, "Non-suppressed preserved inline tags should still be reported in the issue log."
        assert not {"sup", "sub", "a"} & preserved_inline_tags, "Sup, sub, and anchor preservation messages should be hidden."
        inline_preserve_report = service._build_text_report(inline_preserve_result.issues)
        assert "HTML tag <code> has no dedicated DTBook rule and was preserved as-is in the XML output." in inline_preserve_report, "Other preserved inline tags should still be reported."
        assert "HTML tag <a> has no dedicated DTBook rule and was preserved as-is in the XML output." not in inline_preserve_report, "Anchor preservation report entries should be hidden."
        assert "HTML tag <sup> has no dedicated DTBook rule and was preserved as-is in the XML output." not in inline_preserve_report, "Sup preservation report entries should be hidden."
        assert "HTML tag <sub> has no dedicated DTBook rule and was preserved as-is in the XML output." not in inline_preserve_report, "Sub preservation report entries should be hidden."
        assert "No declaration" not in inline_preserve_report, "DTD no-declaration messages should not appear in the report."

        anchor_cleanup_html = temp_root / "anchor-cleanup.htm"
        anchor_cleanup_html.write_text(
            """
            <html><body>
              <p>6801 BA Arnhem <a href="http://www.loesje.nl">
<span class="font0">www.loesje.n</span>
</a>l</p>
            </body></html>
            """,
            encoding="utf-8",
        )
        anchor_cleanup_result = service.convert(
            [InputDocument(path=anchor_cleanup_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert '<p>6801 BA Arnhem www.loesje.nl</p>' in anchor_cleanup_result.xml_text, "Anchor hyperlinks should be removed while their inline text stays in place."

        anchor_strong_inline_html = temp_root / "anchor-strong-inline.htm"
        anchor_strong_inline_html.write_text(
            """
            <html><body>
              <p>Meer achtergrondinformatie is te vinden op <a href="http://www.vangorcumstudie.nl"><span style="font-weight:bold;">www.vangorcumstudie.nl</span></a>.</p>
            </body></html>
            """,
            encoding="utf-8",
        )
        anchor_strong_inline_result = service.convert(
            [InputDocument(path=anchor_strong_inline_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert '<p>Meer achtergrondinformatie is te vinden op <strong>www.vangorcumstudie.nl</strong>.</p>' in anchor_strong_inline_result.xml_text, "Anchors that contain styled content should drop the hyperlink but keep the formatted text inline."

        inline_spacing_html = temp_root / "inline-spacing.htm"
        inline_spacing_html.write_text(
            """
            <html><body>
              <p><span style="font-style:italic;">Italic</span><sup>1</sup></p>
              <p><span style="font-style:italic;">Italic</span> <sup>2</sup></p>
              <p><span style="font-weight:bold;">Bold</span><sub>3</sub></p>
              <p><span style="font-weight:bold;">Bold</span> <sub>4</sub></p>
            </body></html>
            """,
            encoding="utf-8",
        )
        inline_spacing_result = service.convert(
            [InputDocument(path=inline_spacing_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert "<em>Italic</em><sup>1</sup>" in inline_spacing_result.xml_text, "Italic text followed immediately by sup should stay adjacent."
        assert "<em>Italic</em> <sup>2</sup>" in inline_spacing_result.xml_text, "Existing spaces before sup should be preserved."
        assert "<strong>Bold</strong><sub>3</sub>" in inline_spacing_result.xml_text, "Bold text followed immediately by sub should stay adjacent."
        assert "<strong>Bold</strong> <sub>4</sub>" in inline_spacing_result.xml_text, "Existing spaces before sub should be preserved."

        inline_hyphen_spacing_html = temp_root / "inline-hyphen-spacing.htm"
        inline_hyphen_spacing_html.write_text(
            """
            <html><body>
              <p>het <span style="font-style:italic;">Incentive motivation</span>-model en het <span style="font-style:italic;">Dual control</span>-model.</p>
            </body></html>
            """,
            encoding="utf-8",
        )
        inline_hyphen_spacing_result = service.convert(
            [InputDocument(path=inline_hyphen_spacing_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert "<em>Incentive motivation</em>-model" in inline_hyphen_spacing_result.xml_text, "Italic text followed by a hyphen should stay attached."
        assert "<em>Dual control</em>-model" in inline_hyphen_spacing_result.xml_text, "Multiple italic-hyphen combinations should not gain an extra space."
        assert "<em>Incentive motivation</em> -model" not in inline_hyphen_spacing_result.xml_text, "No extra space should be injected before a hyphen after inline emphasis."

        heading_preserve_html = temp_root / "heading-preserve.htm"
        heading_preserve_html.write_text(
            """
            <html><body>
              <h1><span>&lt;h1&gt;</span>Chapter<sup>1</sup><span>&lt;/h1&gt;</span></h1>
            </body></html>
            """,
            encoding="utf-8",
        )
        heading_preserve_result = service.convert(
            [InputDocument(path=heading_preserve_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert re.search(r"<h1>Chapter<sup>1</sup>\s*</h1>", heading_preserve_result.xml_text), "Unknown inline tags inside headings should stay intact."

        split_heading_html = temp_root / "split-heading.htm"
        split_heading_html.write_text(
            """
            <html><body>
              <p><span class="font8">&lt;h1&gt;Hoofdstuk 1</span></p>
              <h1><a name="bookmark12"></a><span class="font10" style="font-weight:bold;">Hoe werkt seks&lt;/h1&gt;</span></h1>
            </body></html>
            """,
            encoding="utf-8",
        )
        split_heading_result = service.convert(
            [InputDocument(path=split_heading_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert "<h1>Hoofdstuk 1 Hoe werkt seks</h1>" in split_heading_result.xml_text, "Split heading wrappers should merge into a single real heading with preserved spacing."

        html_validator = HtmlSourceValidator()

        valid_html = temp_root / "html-validator-valid.htm"
        valid_html.write_text(
            """
            <html><body>
              <p>Water H<sup>2</sup>O.</p>
              <p><span class="font2">&lt;ft&gt;</span></p>
              <p>1 Example note.</p>
              <p><span class="font2">&lt;/ft&gt;</span></p>
            </body></html>
            """,
            encoding="utf-8",
        )
        valid_validation_result = html_validator.validate_documents(
            [InputDocument(path=valid_html, order=1, origin=str(temp_root))]
        )
        assert valid_validation_result.is_valid, "Well-nested HTML and escaped semantic tags should pass HTML validation."
        assert "Validation successful 100%." in valid_validation_result.report_text, "Successful HTML validation should report a 100% success status."
        assert valid_validation_result.report_path is not None and valid_validation_result.report_path.exists(), "HTML validation should always write a report beside the source files."

        split_semantic_html = temp_root / "html-validator-split-semantic.htm"
        split_semantic_html.write_text(
            """
            <html><body>
              <p><span class="font16" style="font-weight:bold;">&lt;</span><span class="font16">fig</span><span class="font16" style="font-weight:bold;">&gt;</span></p>
              <p>Caption line one.</p>
              <p><span class="font16" style="font-weight:bold;">&lt;/</span><span class="font16">fig</span><span class="font16" style="font-weight:bold;">&gt;</span></p>
              <p><span class="font16" style="font-weight:bold;">&lt;ft</span><span class="font16" style="font-weight:bold;">&gt;</span></p>
              <p>1 Split marker note.</p>
              <p><span class="font16" style="font-weight:bold;">&lt;/ft</span><span class="font16" style="font-weight:bold;">&gt;</span></p>
            </body></html>
            """,
            encoding="utf-8",
        )
        split_semantic_validation_result = html_validator.validate_documents(
            [InputDocument(path=split_semantic_html, order=1, origin=str(temp_root))]
        )
        assert split_semantic_validation_result.is_valid, "Split escaped semantic tags across spans should still validate successfully."

        invalid_html = temp_root / "html-validator-invalid.htm"
        invalid_html.write_text(
            """
            <html><body>
              <p><span class="font2">&lt;ft&gt;</span></p>
              <p>Wrong semantic closer <span class="font2">&lt;/fig&gt;</span></p>
              <p>Wrong inline closer <sup>10</sub></p>
            </body></html>
            """,
            encoding="utf-8",
        )
        invalid_validation_result = html_validator.validate_documents(
            [InputDocument(path=invalid_html, order=1, origin=str(temp_root))]
        )
        assert not invalid_validation_result.is_valid, "Mismatched HTML and escaped semantic tags should fail HTML validation."
        invalid_report = invalid_validation_result.report_text
        assert "Escaped semantic tag mismatch" in invalid_report, "Semantic tag mismatches should be logged in the HTML validation report."
        assert "HTML tag mismatch" in invalid_report, "Actual HTML tag mismatches should be logged in the HTML validation report."

        plain_real_heading_html = temp_root / "plain-real-heading.htm"
        plain_real_heading_html.write_text(
            """
            <html><body>
              <h2><em>Plain real heading</em></h2>
            </body></html>
            """,
            encoding="utf-8",
        )
        plain_real_heading_result = service.convert(
            [InputDocument(path=plain_real_heading_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert "<p><em>Plain real heading</em></p>" in plain_real_heading_result.xml_text, "Real headings without escaped heading wrappers should convert to paragraphs."
        assert "<h2><em>Plain real heading</em></h2>" not in plain_real_heading_result.xml_text, "Real headings should not stay as DTBook headings without escaped wrappers."

        block_preserve_html = temp_root / "block-preserve.htm"
        block_preserve_html.write_text(
            """
            <html><body>
              <article data-kind="science">
                <section>
                  <p>Alpha<sup>2</sup></p>
                </section>
                <pre>line 1
  line 2</pre>
              </article>
            </body></html>
            """,
            encoding="utf-8",
        )
        block_preserve_result = service.convert(
            [InputDocument(path=block_preserve_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert '<article data-kind="science">' in block_preserve_result.xml_text, "Unknown block tags should be preserved as-is."
        assert "<section>" in block_preserve_result.xml_text, "Nested unknown block tags should be preserved."
        assert re.search(r"<pre>line 1\s*\n  line 2</pre>", block_preserve_result.xml_text), "Preformatted blocks should retain their whitespace."
        preserved_block_tags = {issue.tag for issue in block_preserve_result.issues if issue.code == "preserved-html-tag"}
        assert {"article", "section", "pre"}.issubset(preserved_block_tags), "Preserved block tags should be reported in the issue log."
        assert "sup" not in preserved_block_tags, "Sup preservation report entries should be hidden even when the tag is preserved."

        heading_levels_html = temp_root / "heading-levels.htm"
        heading_levels_html.write_text(
            """
            <html><body>
              <h1><span>&lt;h1&gt;</span>Part One<span>&lt;/h1&gt;</span></h1>
              <p>Alpha</p>
              <h2><span>&lt;h2&gt;</span>Chapter One<span>&lt;/h2&gt;</span></h2>
              <p>Beta</p>
              <h3><span>&lt;h3&gt;</span>Section One<span>&lt;/h3&gt;</span></h3>
              <p>Gamma</p>
              <h2><span>&lt;h2&gt;</span>Chapter Two<span>&lt;/h2&gt;</span></h2>
              <p>Delta</p>
            </body></html>
            """,
            encoding="utf-8",
        )
        heading_levels_result = service.convert(
            [InputDocument(path=heading_levels_html, order=1, origin=str(temp_root))],
            metadata,
        )
        heading_root = etree.fromstring(heading_levels_result.xml_text.encode("utf-8"))
        assert heading_root.xpath("count(.//*[local-name()='bodymatter']/*[local-name()='level1'])") == 1.0, "A genuine h1 should open the first DTBook level."
        assert heading_root.xpath("count(.//*[local-name()='level1']/*[local-name()='level2'])") == 2.0, "Later h2 headings should stay nested under the current h1."
        assert heading_root.xpath("count(.//*[local-name()='level2']/*[local-name()='level3'])") == 1.0, "A genuine h3 should nest under the active h2 level."
        assert "Alpha" in ranged_blank_result.xml_text and "Beta" in ranged_blank_result.xml_text and "Gamma" in ranged_blank_result.xml_text, "Generated page numbering must not drop content around blank markers."

        mixed_heading_html = temp_root / "mixed-heading.htm"
        mixed_heading_html.write_text(
            """
            <html><body>
              <h2><span class="font2">&lt;page<a name="bookmark3"></a>&gt;</span><br><br><span class="font2"> &lt;h2&gt; </span><span class="font2" style="font-weight:bold;">2.1 Inleiding</span><span class="font2"> &lt;/h2&gt; </span></h2>
            </body></html>
            """,
            encoding="utf-8",
        )
        mixed_heading_result = service.convert(
            [InputDocument(path=mixed_heading_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert '<pagenum page="normal" id="page-1">1</pagenum>' in mixed_heading_result.xml_text, "Escaped page markers should still become pagenum output before the heading."
        assert "<h2>2.1 Inleiding</h2>" in mixed_heading_result.xml_text, "Escaped heading wrappers inside real headings should preserve the heading and strip only the wrappers."

        mixed_heading_in_div_html = temp_root / "mixed-heading-in-div.htm"
        mixed_heading_in_div_html.write_text(
            """
            <html><body>
              <div>
                <p><span class="font1">Zoek in de rubriek Zorg &amp;nbsp;Welzijn.</span></p>
              </div><br clear="all">
              <div>
                <h3><span class="font4">&lt;page<a name="bookmark23"></a>&gt;</span><br><br><span class="font2" style="font-weight:bold;">&lt;h2&gt;Literatuur&lt;/h2&gt;</span></h3>
                <p><span class="font1">1. Vanwesenbeeck, I. (2011). ‘Gender doen’ in seks en sekswetenschap.</span></p>
              </div>
            </body></html>
            """,
            encoding="utf-8",
        )
        mixed_heading_in_div_result = service.convert(
            [InputDocument(path=mixed_heading_in_div_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert '<pagenum page="normal" id="page-1">1</pagenum>' in mixed_heading_in_div_result.xml_text, "Leading escaped page markers inside heading wrappers should still emit a page number."
        assert re.search(r"<level2 id=\"l-\d+\">\s*<h2>Literatuur</h2>\s*<p>1\. Vanwesenbeeck, I\. \(2011\)\. ‘Gender doen’ in seks en sekswetenschap\.</p>\s*</level2>", mixed_heading_in_div_result.xml_text), "Paragraphs that follow a semantic heading inside a div should remain inside that heading level."

        sidebar_boundary_heading_html = temp_root / "sidebar-boundary-heading.htm"
        sidebar_boundary_heading_html.write_text(
            """
            <html><body>
              <h3><span class="font2" style="font-weight:bold;">&lt;sd&gt;</span><br><br><span class="font2" style="font-weight:bold;">Reflectie</span></h3>
              <p><span class="font1">&lt;ul&gt;</span></p>
              <p><span class="font1">• Vraag 1</span></p>
              <p><span class="font1">&lt;/ul&gt;</span></p>
              <p><span class="font1">Zoek in de rubriek Zorg &amp;nbsp;Welzijn.</span></p>
              <h3><span class="font4">&lt;page<a name="bookmark23"></a>&gt;</span><br><br><span class="font2" style="font-weight:bold;">&lt;h2&gt;Literatuur&lt;/h2&gt;</span></h3>
              <p><span class="font1">1. Vanwesenbeeck, I. (2011). ‘Gender doen’ in seks en sekswetenschap.</span></p>
            </body></html>
            """,
            encoding="utf-8",
        )
        sidebar_boundary_heading_result = service.convert(
            [InputDocument(path=sidebar_boundary_heading_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert re.search(r"<sidebar render=\"required\">.*?<p>Zoek in de rubriek Zorg Welzijn\.</p>\s*</sidebar>", sidebar_boundary_heading_result.xml_text, re.DOTALL), "Open sidebars should keep their own content before a later semantic heading starts."
        assert re.search(r"</sidebar>\s*<pagenum page=\"normal\" id=\"page-1\">1</pagenum>\s*<level2 id=\"l-\d+\">\s*<h2>Literatuur</h2>\s*<p>1\. Vanwesenbeeck, I\. \(2011\)\. ‘Gender doen’ in seks en sekswetenschap\.</p>\s*</level2>", sidebar_boundary_heading_result.xml_text), "A semantic heading should close an open sidebar boundary before starting the new DTBook level."

        close_img_heading_html = temp_root / "close-img-heading.htm"
        close_img_heading_html.write_text(
            """
            <html><body>
              <p><span class="font1">&lt;img&gt;</span></p>
              <h3><span class="font1">&lt;/img<a name="bookmark2"></a>&gt;</span><br><br><span class="font1" style="font-weight:bold;">Leerdoelen</span></h3>
              <p><span class="font1">Na het lezen van dit hoofdstuk:</span></p>
            </body></html>
            """,
            encoding="utf-8",
        )
        close_img_heading_result = service.convert(
            [InputDocument(path=close_img_heading_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert "<imggroup>" not in close_img_heading_result.xml_text, "A close-img marker without a real image should not leave behind an empty image group."
        assert "<p><strong>Leerdoelen</strong></p>" in close_img_heading_result.xml_text, "Content that follows a close-img marker in the same heading node should return to normal flow."
        assert "<p>Na het lezen van dit hoofdstuk:</p>" in close_img_heading_result.xml_text, "Paragraphs after a close-img marker should no longer be captured inside the previous image caption."

        close_img_semantic_heading_html = temp_root / "close-img-semantic-heading.htm"
        close_img_semantic_heading_html.write_text(
            """
            <html><body>
              <p><span class="font3">&lt;img&gt;</span></p>
              <h2><span class="font3">&lt;/img<a name="bookmark35"></a>&gt;</span><br><br><span class="font1">&lt;h3&gt;</span><span class="font2" style="font-weight:bold;">Reflectie</span><span class="font1">&lt;/h3&gt;</span></h2>
            </body></html>
            """,
            encoding="utf-8",
        )
        close_img_semantic_heading_result = service.convert(
            [InputDocument(path=close_img_semantic_heading_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert "<imggroup>" not in close_img_semantic_heading_result.xml_text, "A close-img marker should be consumed before semantic heading detection runs."
        assert "<h3>Reflectie</h3>" in close_img_semantic_heading_result.xml_text, "Escaped heading wrappers that follow a close-img marker should still create a real heading."

        nested_semantic_headings_html = temp_root / "nested-semantic-headings.htm"
        nested_semantic_headings_html.write_text(
            """
            <html><body>
              <h2><span class="font2">&lt;h2&gt;</span><span class="font2" style="font-weight:bold;">2.5 Derde levensfase (55-75 jaar)</span><span class="font2">&lt;/h2&gt;</span></h2>
              <h3><span class="font1">&lt;h3&gt;</span><span class="font1" style="font-weight:bold;">2.5.1 Biopsychosociale context</span><span class="font1">&lt;/h3&gt;</span></h3>
            </body></html>
            """,
            encoding="utf-8",
        )
        nested_semantic_headings_result = service.convert(
            [InputDocument(path=nested_semantic_headings_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert "<h2>2.5 Derde levensfase (55-75 jaar)</h2>" in nested_semantic_headings_result.xml_text, "Nested semantic h2 headings should not leave strong wrappers or break bracketed text."
        assert "<h3>2.5.1 Biopsychosociale context</h3>" in nested_semantic_headings_result.xml_text, "Nested semantic h3 headings should also unwrap strong formatting cleanly."

        inline_page_marker_html = temp_root / "inline-page-marker.htm"
        inline_page_marker_html.write_text(
            """
            <html><body>
              <p><span class="font3">Bij deze leeftijdsgroep &lt;page&gt;</span></p>
            </body></html>
            """,
            encoding="utf-8",
        )
        inline_page_marker_result = service.convert(
            [InputDocument(path=inline_page_marker_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert "<p>Bij deze leeftijdsgroep </p>" in inline_page_marker_result.xml_text, "Inline text should remain before a trailing page marker."
        assert '<pagenum page="normal" id="page-1">1</pagenum>' in inline_page_marker_result.xml_text, "Escaped page markers inside text should convert to pagenum output instead of being removed."
        assert "<p><pagenum" not in inline_page_marker_result.xml_text, "Page markers should not remain inside the opening paragraph tag."

        split_inline_page_marker_html = temp_root / "split-inline-page-marker.htm"
        split_inline_page_marker_html.write_text(
            """
            <html><body>
              <p><span class="font2">waar&lt;page&gt;</span></p>
              <p><span class="font2">schijnlijk slechts het topje van de ijsberg.</span></p>
            </body></html>
            """,
            encoding="utf-8",
        )
        split_inline_page_marker_result = service.convert(
            [InputDocument(path=split_inline_page_marker_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert "<p>waar</p>" in split_inline_page_marker_result.xml_text, "Text before an inline page marker should stay in its own paragraph."
        assert '<pagenum page="normal" id="page-1">1</pagenum>' in split_inline_page_marker_result.xml_text, "Split paragraphs should still emit the page marker."
        assert "<p>schijnlijk slechts het topje van de ijsberg.</p>" in split_inline_page_marker_result.xml_text, "Text after an inline page marker should continue in a fresh paragraph."

        split_standalone_page_marker_html = temp_root / "split-standalone-page-marker.htm"
        split_standalone_page_marker_html.write_text(
            """
            <html><body>
              <p><span class="font16" style="font-weight:bold;">&lt;</span><span class="font16">page</span><span class="font16" style="font-weight:bold;">&gt;</span></p>
            </body></html>
            """,
            encoding="utf-8",
        )
        split_standalone_page_marker_result = service.convert(
            [InputDocument(path=split_standalone_page_marker_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert '<pagenum page="normal" id="page-1">1</pagenum>' in split_standalone_page_marker_result.xml_text, "Standalone split page markers should still emit a pagenum."
        assert "<p>&lt;</p>" not in split_standalone_page_marker_result.xml_text, "Standalone split page markers should not leave a stray opening bracket paragraph."
        assert "<p>&gt;</p>" not in split_standalone_page_marker_result.xml_text, "Standalone split page markers should not leave a stray closing bracket paragraph."

        split_leading_page_marker_html = temp_root / "split-leading-page-marker.htm"
        split_leading_page_marker_html.write_text(
            """
            <html><body>
              <p><span class="font16" style="font-weight:bold;">&lt;</span><span class="font16">page</span><span class="font16" style="font-weight:bold;">&gt;</span><span class="font2">Leading text stays here.</span></p>
            </body></html>
            """,
            encoding="utf-8",
        )
        split_leading_page_marker_result = service.convert(
            [InputDocument(path=split_leading_page_marker_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert '<pagenum page="normal" id="page-1">1</pagenum>' in split_leading_page_marker_result.xml_text, "Leading split page markers should still emit a pagenum."
        assert "<p>Leading text stays here.</p>" in split_leading_page_marker_result.xml_text, "Text after a split page marker should remain in the paragraph."
        assert "<p>&lt;</p>" not in split_leading_page_marker_result.xml_text, "Leading split page markers should not leave a stray opening bracket paragraph."

        split_wrapped_heading_marker_html = temp_root / "split-wrapped-heading-marker.htm"
        split_wrapped_heading_marker_html.write_text(
            """
            <html><body>
              <h2><span class="font16" style="font-weight:bold;">&lt;</span><span class="font16">h2</span><span class="font16" style="font-weight:bold;">&gt;</span><span class="font2" style="font-style:italic;">Literatuur</span><span class="font16" style="font-weight:bold;">&lt;/</span><span class="font16">h2</span><span class="font16" style="font-weight:bold;">&gt;</span></h2>
            </body></html>
            """,
            encoding="utf-8",
        )
        split_wrapped_heading_marker_result = service.convert(
            [InputDocument(path=split_wrapped_heading_marker_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert re.search(r"<h2>\s*<em>Literatuur</em>\s*</h2>", split_wrapped_heading_marker_result.xml_text), "Split heading marker wrappers should preserve the heading content without leaking angle-bracket fragments."
        assert "&lt;" not in split_wrapped_heading_marker_result.xml_text and "&gt;" not in split_wrapped_heading_marker_result.xml_text, "Split heading wrappers should not leak escaped angle brackets into the XML output."

        discontinuous_documents_root = temp_root / "discontinuous"
        discontinuous_documents_root.mkdir(parents=True, exist_ok=True)
        discontinuous_first = discontinuous_documents_root / "381196_041-080.htm"
        discontinuous_first.write_text(
            """
            <html><body>
              <h1><span>&lt;h1&gt;</span>Hoofdstuk 4 Diversiteit<span>&lt;/h1&gt;</span></h1>
              <h2><span>&lt;h2&gt;</span>4.2 Feiten en cijfers<span>&lt;/h2&gt;</span></h2>
              <h3><span>&lt;h3&gt;</span>4.2.3 Seksuele oriëntatie<span>&lt;/h3&gt;</span></h3>
            </body></html>
            """,
            encoding="utf-8",
        )
        discontinuous_second = discontinuous_documents_root / "381196_371-410.htm"
        discontinuous_second.write_text(
            """
            <html><body>
              <h2><span class="font1">&lt;h3&gt;<a name="bookmark0"></a></span><span class="font1" style="font-weight:bold;">20.3.2 Wisselwerking tussen het relationele aspect en seksuele aspect</span><span class="font1">&lt;/h3&gt;</span></h2>
              <h2><span class="font1">&lt;h3&gt;<a name="bookmark1"></a></span><span class="font1" style="font-weight:bold;">20.3.3 Beschadigde intimiteit en ontrouw</span><span class="font1">&lt;/h3&gt;</span></h2>
              <h1><span class="font1">&lt;h2&gt;<a name="bookmark2"></a></span><span class="font2" style="font-weight:bold;">20.4 Praktische aanpak</span><span class="font1">&lt;/h2&gt;</span></h1>
            </body></html>
            """,
            encoding="utf-8",
        )
        discontinuous_result = service.convert(
            [
                InputDocument(path=discontinuous_first, order=1, origin=str(discontinuous_documents_root)),
                InputDocument(path=discontinuous_second, order=2, origin=str(discontinuous_documents_root)),
            ],
            metadata,
        )
        assert "<h3>20.3.2 Wisselwerking tussen het relationele aspect en seksuele aspect</h3>" in discontinuous_result.xml_text, "The first carried-over h3 should remain in its own chunk after a file gap."
        assert "<h3>20.3.3 Beschadigde intimiteit en ontrouw</h3>" in discontinuous_result.xml_text, "The second carried-over h3 should remain with the same discontinuous chunk."
        assert "<h2>20.4 Praktische aanpak</h2>" in discontinuous_result.xml_text, "Later h2 headings in a discontinuous file should no longer stay attached to an earlier chapter from another file."
        assert "<h1>Chapter 20</h1>" not in discontinuous_result.xml_text, "Synthetic chapter placeholders should no longer be generated for discontinuous file gaps."
        assert "<h2>Section 20.3</h2>" not in discontinuous_result.xml_text, "Synthetic section placeholders should no longer be generated for discontinuous file gaps."

        headingless_document_html = temp_root / "headingless-document.htm"
        headingless_document_html.write_text(
            """
            <html><body>
              <p>Alpha</p>
              <p>Beta</p>
            </body></html>
            """,
            encoding="utf-8",
        )
        headingless_document_result = service.convert(
            [InputDocument(path=headingless_document_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert re.search(r"<level1 id=\"l-\d+\">\s*<h1/>\s*<p>Alpha</p>\s*<p>Beta</p>\s*</level1>", headingless_document_result.xml_text), "Files with no headings anywhere should get an empty dummy h1 at the start of the body content."

        img_marker_folder = temp_root / "381196_(041-080)_files"
        img_marker_folder.mkdir(parents=True, exist_ok=True)
        img_marker_image = img_marker_folder / "381196_(041-080)-6.jpg"
        img_marker_image.write_bytes(b"\xff\xd8\xff\xd9")
        img_marker_html = temp_root / "img-marker.htm"
        img_marker_html.write_text(
            """
            <html><body>
              <p><span class="font3">&lt;img&gt;</span></p>
              <br clear="all">
              <div><img src="381196_(041-080)_files/381196_(041-080)-6.jpg" alt="" style="width:387pt;height:216pt;"/>
              <p><span class="font1" style="font-weight:bold;">Figuur 2.2 </span><span class="font1">Verschuiving in ervaring met penetratieseks in de afgelopen 12 maanden (%)<sup>24</sup></span></p>
              <p><span class="font3">&lt;/img&gt;</span></p></div>
            </body></html>
            """,
            encoding="utf-8",
        )
        img_marker_result = service.convert(
            [InputDocument(path=img_marker_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert re.search(r"<imggroup>\s*<img src=\"img/cover\.jpg\" alt=\"afbeelding\"/>\s*<caption>\s*<p><strong>Figuur 2\.2</strong> Verschuiving in ervaring met penetratieseks in de afgelopen 12 maanden \(%\)<sup>24</sup>\s*</p>\s*</caption>", img_marker_result.xml_text), "Escaped img wrapper blocks should convert into a single imggroup with image and caption content."

        marker_list_html = temp_root / "marker-lists.htm"
        marker_list_html.write_text(
            """
            <html><body>
              <p><span class="font7">&lt;ol&gt;</span></p>
              <p><span class="font4" style="font-weight:bold;">a </span><span class="font20">Text A </span><span class="font1" style="font-weight:bold;">R</span></p>
              <p><span class="font4" style="font-weight:bold;">b </span><span class="font20">Text B </span><span class="font1" style="font-weight:bold;">T1</span></p>
              <p><span class="font4" style="font-weight:bold;">c </span><span class="font20">Text C </span><span class="font1" style="font-weight:bold;">I</span></p>
              <p><span class="font7">&lt;/ol&gt;</span></p>
              <p><span class="font7">&lt;ul&gt;</span></p>
              <p><span class="font20">Item 1</span></p>
              <p><span class="font20">Item 2</span></p>
              <p><span class="font20">Item 3</span></p>
              <p><span class="font7">&lt;/ul&gt;</span></p>
            </body></html>
            """,
            encoding="utf-8",
        )
        marker_list_result = service.convert(
            [InputDocument(path=marker_list_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert '<list type="pl">' in marker_list_result.xml_text, "Ordered marker list should convert to DTBook list."
        assert marker_list_result.xml_text.count("<li>") >= 6, "Marker-based list items should stay separated."
        assert "<li><strong>a</strong> Text A (R)</li>" in marker_list_result.xml_text, "Ordered marker first item is wrong."
        assert "<li><strong>b</strong> Text B (T1)</li>" in marker_list_result.xml_text, "Ordered marker second item is wrong."
        assert "<li><strong>c</strong> Text C (I)</li>" in marker_list_result.xml_text, "Ordered marker third item is wrong."
        assert '<list type="pl" class="ul-nobullets">' in marker_list_result.xml_text, "Unordered marker list should use ul-nobullets."
        assert "<li>Item 1</li>" in marker_list_result.xml_text, "First unordered item is wrong."
        assert "<li>Item 2</li>" in marker_list_result.xml_text, "Second unordered item is wrong."
        assert "<li>Item 3</li>" in marker_list_result.xml_text, "Third unordered item is wrong."

        figure_marker_html = temp_root / "figure-marker.htm"
        figure_marker_html.write_text(
            """
            <html><body>
              <p><span class="font1">&lt;fig&gt;</span></p>
              <div><img src="sample.jpg" alt="" style="width:52pt;height:25pt;"/></div>
              <div>
                <p><span class="font13" style="font-style:italic;">Een luipaard of een lui paard? Sommige</span></p>
                <p><span class="font13" style="font-style:italic;">Nederlandse samenstellingen zijn eigenlijk best gek.</span></p>
                <p><span class="font1">&lt;/fig&gt;</span></p>
              </div>
            </body></html>
            """,
            encoding="utf-8",
        )
        figure_marker_result = service.convert(
            [InputDocument(path=figure_marker_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert (
            "<imggroup>\n<img src=\"img/cover.jpg\" alt=\"afbeelding\"/>\n<caption>\n<p><em>Een luipaard of een lui paard? Sommige</em></p>\n<p><em>Nederlandse samenstellingen zijn eigenlijk best gek.</em></p>\n</caption>\n</imggroup>"
            in figure_marker_result.xml_text
        ), "Marker-based figure captions should stay inside the imggroup caption block."

        figure_caption_first_html = temp_root / "figure-caption-first.htm"
        figure_caption_first_html.write_text(
            """
            <html><body>
              <p><span class="font1">&lt;fig&gt;</span></p>
              <div>
                <p><span class="font13" style="font-style:italic;">Caption line before image.</span></p>
                <p><span class="font13" style="font-style:italic;">Second caption line before image.</span></p>
                <div><img src="sample.jpg" alt="" style="width:52pt;height:25pt;"/></div>
                <p><span class="font1">&lt;/fig&gt;</span></p>
              </div>
            </body></html>
            """,
            encoding="utf-8",
        )
        figure_caption_first_result = service.convert(
            [InputDocument(path=figure_caption_first_html, order=1, origin=str(temp_root))],
            metadata,
        )
        figure_caption_first_root = etree.fromstring(figure_caption_first_result.xml_text.encode("utf-8"))
        figure_group = figure_caption_first_root.xpath(".//*[local-name()='imggroup']")[0]
        assert [child.tag.split('}', 1)[-1] for child in figure_group[:2]] == ["img", "caption"], "Figure output should always place the image before its captions."
        assert "Caption line before image." in figure_caption_first_result.xml_text and "Second caption line before image." in figure_caption_first_result.xml_text, "Caption text should be preserved when reordered."

        figure_container_html = temp_root / "figure-container.htm"
        figure_container_html.write_text(
            """
            <html><body>
              <div>
                <p><span style="font-style:italic;">Caption appears before the image.</span></p>
                <img src="sample.jpg" alt=""/>
                <p><span style="font-style:italic;">Caption stays after the image in XML.</span></p>
              </div>
            </body></html>
            """,
            encoding="utf-8",
        )
        figure_container_result = service.convert(
            [InputDocument(path=figure_container_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert (
            "<imggroup>\n<img src=\"img/cover.jpg\" alt=\"afbeelding\"/>\n<caption>\n<p><em>Caption appears before the image.</em></p>\n<p><em>Caption stays after the image in XML.</em></p>\n</caption>\n</imggroup>"
            in figure_container_result.xml_text
        ), "Figure-like containers should normalize the image before all caption paragraphs."

        figure_placeholder_html = temp_root / "figure-placeholder.htm"
        figure_placeholder_html.write_text(
            """
            <html><body>
              <img src="sample.jpg"/>
            </body></html>
            """,
            encoding="utf-8",
        )
        figure_placeholder_result = service.convert(
            [InputDocument(path=figure_placeholder_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert "<caption></caption>" in figure_placeholder_result.xml_text, "Empty captions should stay on a single line."
        assert re.search(
            r"<imggroup>\s*<img src=\"img/cover\.jpg\" alt=\"afbeelding\"/>\s*<caption>\s*</caption>\s*<prodnote render=\"required\">\s*<p>Tekst in afbeelding:</p>\s*</prodnote>\s*</imggroup>",
            figure_placeholder_result.xml_text,
        ), "Image-only groups should receive an empty caption plus required prodnote placeholder."
        figure_placeholder_report = service._build_text_report(figure_placeholder_result.issues)
        assert "No declaration for element prodnote" not in figure_placeholder_report, "Prodnote declaration errors should be hidden from the text report."
        assert "No declaration for attribute render of element prodnote" not in figure_placeholder_report, "Prodnote attribute declaration errors should be hidden from the text report."

        figure_existing_prodnote_html = temp_root / "figure-existing-prodnote.htm"
        figure_existing_prodnote_html.write_text(
            """
            <html><body>
              <div>
                <img src="sample.jpg"/>
                <prodnote render="required"><p>Existing note</p></prodnote>
              </div>
            </body></html>
            """,
            encoding="utf-8",
        )
        figure_existing_prodnote_result = service.convert(
            [InputDocument(path=figure_existing_prodnote_html, order=1, origin=str(temp_root))],
            metadata,
        )
        assert "<p>Existing note</p>" in figure_existing_prodnote_result.xml_text, "Existing prodnote content should be preserved."
        assert "Tekst in afbeelding:" not in figure_existing_prodnote_result.xml_text, "Placeholder prodnote should not overwrite existing figure text."

        id_finalizer_xml = service.finalize_xml_ids(
            """<?xml version="1.0" encoding="utf-8"?>
<?xml-model href="https://epubshowcase.dedicontest.nl/schematron/dtbook-ext.sch" type="application/xml" schematypens="http://purl.oclc.org/dsdl/schematron"?>
<!DOCTYPE dtbook PUBLIC "-//NISO//DTD dtbook 2005-3//EN" "http://www.daisy.org/z3986/2005/dtbook-2005-3.dtd">
<dtbook version="2005-3" xml:lang="en" xmlns="http://www.daisy.org/z3986/2005/dtbook/">
<head><meta name="dtb:uid" content="374388"/></head>
<book><frontmatter/><bodymatter>
<level1 id="broken"><h1>One</h1>
<level3 id="broken-two"><h3>Two</h3><pagenum id="broken-b" page="normal">1a</pagenum></level3>
</level1>
<level4 id="broken-three"><h4>Three</h4><pagenum id="broken-c" page="front">12</pagenum></level4>
<pagenum id="broken-a" page="normal">i</pagenum>
</bodymatter><rearmatter/></book>
</dtbook>
""",
            regenerate_page_ids=True,
            regenerate_level_ids=True,
        )
        assert 'id="l-1"' in id_finalizer_xml and 'id="l-2"' in id_finalizer_xml and 'id="l-3"' in id_finalizer_xml, "Level IDs should be sequential."
        assert '<level1 id="l-1">' in id_finalizer_xml, "Top-level opening level tag should normalize to level1."
        assert '<level2 id="l-2">' in id_finalizer_xml, "Nested opening level tag should normalize to level2."
        assert '</level2>' in id_finalizer_xml and '</level1>' in id_finalizer_xml, "Closing level tags should be normalized to the regenerated nesting depth."
        assert '<level1 id="l-3">' in id_finalizer_xml, "A new top-level section after closing should normalize back to level1."
        assert 'id="page-i" page="front">i</pagenum>' in id_finalizer_xml, "Roman page should be marked as front."
        assert 'id="page-1a" page="special">1a</pagenum>' in id_finalizer_xml, "Special page should be marked as special."
        assert 'id="page-12" page="normal">12</pagenum>' in id_finalizer_xml, "Numeric page should be marked as normal."
        assert service.extract_uid_from_xml(id_finalizer_xml) == "374388", "UID extraction should use dtb:uid."

        preservation_input = '<pagenum custom="keep" id="old" page="normal">ii</pagenum>\n<p>Text stays same</p>\n<level1 class="chapter" id="x">'
        preservation_output = service.finalize_xml_ids(
            preservation_input,
            regenerate_page_ids=True,
            regenerate_level_ids=True,
        )
        assert '<pagenum custom="keep" id="page-ii" page="front">ii</pagenum>' in preservation_output, "Only page attributes should change in pagenum tags."
        assert '<p>Text stays same</p>' in preservation_output, "Finalizer should not change content outside IDs."
        assert '<level1 class="chapter" id="l-1">' in preservation_output, "Only level id should change in level tags."
        print("[release-check] conversion smoke test passed")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def run_license_smoke_test() -> None:
    service = LicenseService()
    service.save_state = lambda _state: None  # type: ignore[assignment]

    now = datetime.now(UTC)
    active_state = LicenseState(
        installed_at=now.isoformat(),
        trial_expires_at=(now + timedelta(days=1)).isoformat(),
        terms_accepted=True,
        activated=False,
        activation_key="",
        machine_id="TC-ABCDEF123456",
    )
    expired_state = LicenseState(
        installed_at=(now - timedelta(days=5)).isoformat(),
        trial_expires_at=(now - timedelta(days=1)).isoformat(),
        terms_accepted=True,
        activated=False,
        activation_key="",
        machine_id="TC-ABCDEF123456",
    )

    valid_key = service.expected_activation_key(active_state.machine_id)
    ok, message = service.validate_activation_key(active_state, valid_key)
    assert ok and not message, "Valid activation key failed validation."

    ok, message = service.validate_activation_key(active_state, "BAD-KEY")
    assert not ok and "format" in message.lower(), "Malformed activation key should be rejected."

    ok, message = service.activate(active_state, valid_key)
    assert ok and active_state.activated, "Activation flow failed with a valid key."
    assert "successfully" in message.lower(), "Successful activation message missing."
    assert not service.can_launch(expired_state), "Expired unlicensed state should not be allowed to launch."
    assert service.remaining_time_label(active_state), "Remaining time label should be available for active trial states."
    print("[release-check] license smoke test passed")


def run_security_smoke_test() -> None:
    status = SecurityService().run_startup_checks()
    assert status.is_ok, f"Security startup checks failed: {status.errors}"
    print("[release-check] security smoke test passed")


def run_update_service_smoke_test() -> None:
    service = UpdateService("https://github.com/Technnocops/Dedicon-html-to-xml-converter")
    assert service.repository == "Technnocops/Dedicon-html-to-xml-converter", "GitHub repository normalization failed."
    assert service.is_configured, "Update service should be configured with the default repository."
    assert service._extract_version("Release-1.0.0") == "1.0.0", "Release-prefixed GitHub tags should still be parsed as numeric versions."
    print("[release-check] update service smoke test passed")


def run_distribution_check(dist_root: Path) -> None:
    assert dist_root.exists(), f"Portable bundle not found: {dist_root}"

    exe_path = dist_root / "Technocops_DDC_Converter_HTML_to_XML_Pro.exe"
    assert exe_path.exists(), f"Expected EXE missing: {exe_path}"

    candidate_asset_roots = [
        dist_root / "_internal" / "assets",
        dist_root / "assets",
    ]
    asset_root = next((path for path in candidate_asset_roots if path.exists()), None)
    assert asset_root is not None, "Bundled assets directory missing from portable build."
    assert (asset_root / "dtd" / "dtbook-basic.dtd").exists(), "Bundled DTBook DTD missing from portable build."
    assert (asset_root / "branding" / "technocops_app_icon.ico").exists(), "Bundled application icon missing from portable build."
    assert (asset_root / "branding" / "technocops_splash.png").exists(), "Bundled splash image missing from portable build."
    print("[release-check] distribution smoke test passed")


if __name__ == "__main__":
    raise SystemExit(main())
