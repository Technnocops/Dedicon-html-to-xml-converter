# Release Build Instructions

## Application
- Product Name: Technocops DDC Converter (HTML to XML) Pro
- Version: 1.0.0
- Company: Technocops Technology & Innovation

## Prerequisites
- Windows 10/11
- Python virtual environment available in `.venv`
- PyInstaller installed in the virtual environment
- Inno Setup 6 installed if you want to build the installer EXE

## Release Build Steps
1. Open PowerShell in the project root.
2. Run the production build script:

```powershell
.\build_release.ps1
```

3. The script will:
- regenerate branding assets
- run pre-build smoke checks
- build the portable EXE bundle with PyInstaller
- run post-build distribution checks
- build the installer if `ISCC.exe` is available

## Output Paths
- Portable EXE bundle:

```text
release/portable/Technocops_DDC_Converter_HTML_to_XML_Pro/
```

- Installer EXE:

```text
release/installer/
```

## Optional Flags
- Skip smoke checks:

```powershell
.\build_release.ps1 -SkipSmokeChecks
```

- Skip installer compilation:

```powershell
.\build_release.ps1 -SkipInstaller
```

## Installer Compiler
The installer script is:

```text
installer/Technocops_DDC_Converter_HTML_to_XML_Pro.iss
```

If Inno Setup is installed, the build script compiles it automatically.

## Activation Key
Generate an activation key for a target machine ID using:

```powershell
.\.venv\Scripts\python.exe generate_activation_key.py --machine-id TC-XXXXXXXXXXXX
```

## Validation Notes
- The smoke tests validate UI startup, conversion behavior, XML output generation, report generation, image bundling, and license validation logic.
- Full clean-machine installation validation should be performed on a separate Windows test machine before external distribution.
