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

from technocops_ddc.models import AuthorEntry, DTBookMetadata, InputDocument, PageRangeSelection
from technocops_ddc.services.conversion_service import ConversionService
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
    assert metadata_form.producer_input.text() == "", "Producer should no longer be pre-populated."
    assert metadata_form.producer_input.placeholderText() == "Continuum Content Solutions", "Producer placeholder should guide the user."
    assert metadata_form.completion_date_input.calendarPopup(), "Completion date should use a calendar popup."
    assert metadata_form.produced_date_input.calendarPopup(), "Produced date should use a calendar popup."
    metadata_form.uid_input.setText("374388")
    metadata_form.identifier_input.setText("374388")
    metadata_form.generate_ids()
    assert metadata_form.uid_input.text() == "374388", "Generate IDs should not replace an existing UID with a random value."
    assert metadata_form.identifier_input.text() == "374388", "Generate IDs should not replace an existing Identifier with a random value."
    assert window.stop_on_critical_checkbox.text(), "Main window checkbox should be present."
    assert not window.id_regeneration_widget.page_ids_checkbox.isEnabled(), "ID regeneration should be disabled before XML is available."
    assert not window.id_regeneration_widget.apply_button.isEnabled(), "Apply ID finalizer should be disabled before XML is available."
    window.metadata_form.uid_input.setText("374388")
    window.metadata_form.title_input.setText("Temp title")
    window.clear_documents()
    assert window.metadata_form.uid_input.text() == "", "Clearing imported files should also clear metadata."
    assert window.metadata_form.title_input.text() == "", "Metadata reset should clear the previous document title."
    assert window.metadata_form.publisher_input.text() == "Dedicon", "Publisher should remain fixed after metadata reset."
    assert window.metadata_dialog.clean_button.text() == "Clean Metadata", "Metadata dialog should expose a clean button."
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
        output_path = temp_root / "output.xml"

        image_path.write_bytes(b"\xff\xd8\xff\xd9")
        html_path.write_text(
            """
            <html>
              <body>
                <p><page>1</page></p>
                <h1><strong>Chapter One</strong></h1>
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

        service = ConversionService()
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
        assert "<linegroup>" in xml_text, "PM block conversion missing."
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
        assert saved_output.json_report_path.exists(), "JSON report was not written."
        assert saved_output.text_report_path.exists(), "Text report was not written."
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
        assert "Alpha" in ranged_blank_result.xml_text and "Beta" in ranged_blank_result.xml_text and "Gamma" in ranged_blank_result.xml_text, "Generated page numbering must not drop content around blank markers."

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
