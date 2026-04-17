# MSI Packaging Checklist

## Recommended Tooling
- WiX Toolset 4 for MSI authoring
- Windows SDK for validation tools
- Optional: Advanced Installer if a GUI-driven MSI workflow is preferred

## Pre-Conditions
- Portable bundle built successfully:
  - `release/portable/Technocops_DDC_Converter_HTML_to_XML_Pro/`
- Final icon available:
  - `assets/branding/technocops_app_icon.ico`
- Terms and Conditions finalized
- Final version number locked

## MSI Requirements
- Per-machine install by default
- Add/Remove Programs entry
- Desktop shortcut option
- Start Menu shortcut
- Uninstall support
- Major upgrade handling for future versions
- Optional launch-after-install checkbox

## MSI Authoring Checklist
1. Harvest the portable bundle into MSI components.
2. Install to:
   - `Program Files\Technocops DDC Converter (HTML to XML) Pro`
3. Register:
   - product name
   - version
   - publisher
   - uninstall icon
4. Add shortcuts for:
   - Start Menu
   - Desktop
5. Include the Terms & Conditions text in the bootstrapper or companion setup flow if needed.
6. Test:
   - install
   - repair
   - upgrade
   - uninstall

## Validation Checklist
- Install without missing DLLs
- App launches on first run
- Activation dialog appears for non-activated installations
- Page range UI is visible and functional
- Conversion, save, and report generation work
- Uninstall removes the application files but preserves user license state if desired

## Final Release Note
- Sign the MSI after building it.
- If both installer EXE and MSI are distributed, sign both artifacts separately.
