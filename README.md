# Technocops DDC Converter (HTML to XML) Pro

Technocops DDC Converter (HTML to XML) Pro is a Windows desktop application built with Python and PyQt for converting OCR-generated HTML files into a single structured DTBook XML document, validating the generated output, and packaging the result for production workflows.

## Highlights

- Multiple HTML file upload with manual sequencing
- ZIP import with automatic extraction and ordering
- Folder import and drag-and-drop support
- Optional page-range filtering with start/end validation
- Rule-based ABBYY FineReader HTML to DTBook XML conversion
- DTBook metadata form with production fields
- XML preview, input preview, progress tracking, and validation logs
- Error report export in both `.txt` and `.json`
- Offline desktop workflow
- Optional GitHub release update check
- Machine-bound activation, encrypted local trial state, and 3-day evaluation workflow
- Release-ready portable EXE and installer packaging flow

## Technology

- Python
- PyQt6
- lxml
- Requests
- PyInstaller

## Project Structure

```text
src/technocops_ddc/
  app.py
  config.py
  models.py
  services/
  ui/
run_app.py
assets/
  logo.svg
  dtd/dtbook-basic.dtd
technocops_ddc.spec
build_exe.ps1
```

## Running Locally

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
py -3 -m pip install -r requirements.txt
python run_app.py
```

If you prefer to launch from the source tree without installing the package, set the module search path:

```powershell
$env:PYTHONPATH = "src"
py -3 -m technocops_ddc
```

## Building the Production Release

```powershell
.\build_release.ps1
```

Portable output is generated in:

```text
release/portable/Technocops_DDC_Converter_HTML_to_XML_Pro/
```

If Inno Setup is installed, the installer output is generated in:

```text
release/installer/
```

## GitHub Auto Update

The updater is enabled when the environment variable below is present before launching the application:

```powershell
$env:TECHNOCOPS_DDC_GITHUB_REPO = "owner/repository"
```

The app checks the latest GitHub release and can download and launch a packaged update asset.

## Validation Notes

- The application performs XML well-formedness checks.
- It validates required DTBook structural elements and metadata.
- It uses the bundled `assets/dtd/dtbook-basic.dtd` file for basic DTD validation.
- Validation issues are shown in the logs panel and written to `.report.txt`.

## Packaging Note

For the cleanest Windows distribution, publish a `.exe`, `.msi`, or `.zip` asset in GitHub Releases so the updater can pick it up automatically.
