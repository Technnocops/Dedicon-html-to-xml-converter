from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = PROJECT_ROOT / "docs"


def main() -> int:
    documents = [
        (
            DOCS_DIR / "CLIENT_EXPLANATION_EN.md",
            DOCS_DIR / "CLIENT_EXPLANATION_EN.docx",
            "Technocops DDC Converter Pro - Client Explanation (English)",
            "en-US",
        ),
        (
            DOCS_DIR / "CLIENT_EXPLANATION_HI.md",
            DOCS_DIR / "CLIENT_EXPLANATION_HI.docx",
            "Technocops DDC Converter Pro - Client Explanation (Hindi)",
            "hi-IN",
        ),
    ]

    for source_path, output_path, title, language in documents:
        markdown_text = source_path.read_text(encoding="utf-8")
        paragraphs = parse_markdown(markdown_text)
        write_docx(output_path, paragraphs, title=title, language=language)
        print(output_path)

    return 0


def parse_markdown(markdown_text: str) -> list[tuple[str, str]]:
    paragraphs: list[tuple[str, str]] = []
    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("## "):
            paragraphs.append(("heading2", clean_inline_markdown(line[3:])))
            continue
        if line.startswith("# "):
            paragraphs.append(("heading1", clean_inline_markdown(line[2:])))
            continue
        if line.startswith("- "):
            paragraphs.append(("bullet", clean_inline_markdown(line[2:])))
            continue
        paragraphs.append(("normal", clean_inline_markdown(line)))
    return paragraphs


def clean_inline_markdown(text: str) -> str:
    cleaned = text.replace("`", "")
    cleaned = cleaned.replace("**", "")
    cleaned = cleaned.replace("__", "")
    return cleaned.strip()


def write_docx(
    output_path: Path,
    paragraphs: list[tuple[str, str]],
    *,
    title: str,
    language: str,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", content_types_xml())
        docx.writestr("_rels/.rels", root_relationships_xml())
        docx.writestr("docProps/core.xml", core_properties_xml(title, timestamp))
        docx.writestr("docProps/app.xml", app_properties_xml())
        docx.writestr("word/document.xml", document_xml(paragraphs, language))
        docx.writestr("word/styles.xml", styles_xml(language))
        docx.writestr("word/_rels/document.xml.rels", document_relationships_xml())


def content_types_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>
"""


def root_relationships_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""


def document_relationships_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>
"""


def core_properties_xml(title: str, timestamp: str) -> str:
    escaped_title = escape(title)
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:dcterms="http://purl.org/dc/terms/"
    xmlns:dcmitype="http://purl.org/dc/dcmitype/"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{escaped_title}</dc:title>
  <dc:creator>Technocops Technology &amp; Innovation</dc:creator>
  <cp:lastModifiedBy>Technocops Technology &amp; Innovation</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{timestamp}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{timestamp}</dcterms:modified>
</cp:coreProperties>
"""


def app_properties_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
    xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Technocops DDC Converter Pro</Application>
</Properties>
"""


def document_xml(paragraphs: list[tuple[str, str]], language: str) -> str:
    paragraph_xml = "\n".join(build_paragraph_xml(style, text) for style, text in paragraphs)
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas"
    xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
    xmlns:o="urn:schemas-microsoft-com:office:office"
    xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"
    xmlns:v="urn:schemas-microsoft-com:vml"
    xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing"
    xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
    xmlns:w10="urn:schemas-microsoft-com:office:word"
    xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"
    xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup"
    xmlns:wpi="http://schemas.microsoft.com/office/word/2010/wordprocessingInk"
    xmlns:wne="http://schemas.microsoft.com/office/word/2006/wordml"
    xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
    mc:Ignorable="w14 wp14">
  <w:body>
{paragraph_xml}
    <w:sectPr>
      <w:pgSz w:w="12240" w:h="15840"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>
      <w:lang w:val="{escape(language)}"/>
    </w:sectPr>
  </w:body>
</w:document>
"""


def build_paragraph_xml(style: str, text: str) -> str:
    escaped_text = escape(text)
    style_name = {
        "heading1": "Heading1",
        "heading2": "Heading2",
        "bullet": "ListParagraph",
        "normal": "Normal",
    }[style]
    run_text = f"\u2022 {escaped_text}" if style == "bullet" else escaped_text
    return f"""    <w:p>
      <w:pPr>
        <w:pStyle w:val="{style_name}"/>
      </w:pPr>
      <w:r>
        <w:t xml:space="preserve">{run_text}</w:t>
      </w:r>
    </w:p>"""


def styles_xml(language: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault>
      <w:rPr>
        <w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Nirmala UI" w:cs="Nirmala UI"/>
        <w:lang w:val="{escape(language)}" w:eastAsia="{escape(language)}" w:bidi="{escape(language)}"/>
        <w:sz w:val="22"/>
        <w:szCs w:val="22"/>
      </w:rPr>
    </w:rPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:qFormat/>
    <w:pPr>
      <w:spacing w:after="140" w:line="300" w:lineRule="auto"/>
    </w:pPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/>
    <w:basedOn w:val="Normal"/>
    <w:next w:val="Normal"/>
    <w:qFormat/>
    <w:rPr>
      <w:b/>
      <w:sz w:val="32"/>
      <w:szCs w:val="32"/>
      <w:color w:val="17396D"/>
    </w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/>
    <w:basedOn w:val="Normal"/>
    <w:next w:val="Normal"/>
    <w:qFormat/>
    <w:rPr>
      <w:b/>
      <w:sz w:val="26"/>
      <w:szCs w:val="26"/>
      <w:color w:val="2384FF"/>
    </w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="ListParagraph">
    <w:name w:val="List Paragraph"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:pPr>
      <w:ind w:left="360" w:hanging="0"/>
      <w:spacing w:after="100" w:line="280" w:lineRule="auto"/>
    </w:pPr>
  </w:style>
</w:styles>
"""


if __name__ == "__main__":
    raise SystemExit(main())
