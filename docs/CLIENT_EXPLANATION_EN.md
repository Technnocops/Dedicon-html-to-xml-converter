# Technocops DDC Converter Pro

## Non-Technical Conversion Summary

### What this software does
Technocops DDC Converter Pro is an offline desktop application that converts OCR-generated HTML files, especially ABBYY FineReader output, into a single structured DTBook XML file.

The software is designed for rule-based publishing conversion. It does not guess the structure with AI. Instead, it follows predefined conversion rules so the output remains consistent and predictable.

### Technologies used
- Python
- PyQt6 for the desktop interface
- lxml for HTML parsing, XML generation, and DTD validation
- requests for GitHub update checking
- PyInstaller for Windows EXE packaging

### How the conversion works
The converter reads the HTML files, parses the content, and applies fixed transformation rules.

The conversion is mainly based on:
- HTML tag mapping
- ABBYY marker recognition such as page, pm, hsd, ol, ul
- Inline style detection for bold and italic text
- Structural post-processing for frontmatter, bodymatter, rearmatter, TOC, and level IDs

### Is the conversion font-based?
Not fully.

The converter is not dependent on visual font appearance like a word processor. It works mainly on HTML tags and text markers.

Only a small part is style-based:
- bold span styles are converted to `strong`
- italic span styles are converted to `em`
- special bold markers such as T1, T2, I, and R are converted into bracketed markers like `(T1)`

### Is the conversion DTD-based?
No.

The DTD does not perform the conversion.

The conversion is done first by the application's rule engine. After that, the generated XML is checked against DTBook structural requirements and the bundled DTD validation rules.

So the DTD is used for validation, not for transformation.

### Main conversion logic used
- `<html>` structure is converted into `dtbook`, `head`, `book`, `frontmatter`, `bodymatter`, and `rearmatter`
- metadata tags are generated from the metadata form and detected document values
- headings are converted into nested `level1` to `level6` sections
- `<ol>` and `<ul>` are converted into DTBook `list` structures
- images are collected and referenced inside `imggroup`
- tables are cleaned and preserved in DTBook-friendly structure
- `<pm>` blocks are converted into `linegroup` and `line`
- `<hsd>` blocks are converted into `sidebar`
- page markers are converted into `pagenum`
- unsupported or forbidden HTML tags are flattened or removed according to rule definitions

### Validation and quality control
After conversion, the software checks:
- required DTBook sections
- required metadata
- forbidden leftover HTML tags
- XML well-formedness
- DTD validation issues

It also produces logs and error reports so the operator can review warnings or structural problems.

### One-line explanation for clients
This software uses a rule-based Python conversion engine built on `lxml` to transform ABBYY OCR HTML into structured DTBook XML, with DTD-based validation applied after conversion for quality control.
