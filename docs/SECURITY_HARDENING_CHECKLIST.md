# Security Hardening Checklist

## Implemented In-App Controls
- DPAPI-protected license state at rest
- Machine-bound activation keys
- Registry-backed license state recovery
- Trial expiry enforcement at startup
- Immediate activation prompt on launch for non-activated systems
- Asset integrity verification at startup
- Basic debugger detection

## Recommended Build-Time Hardening
- Use PyArmor or Nuitka-based obfuscation for client-facing protected builds
- Strip debug symbols from packaged artifacts where safe
- Keep update URLs and licensing configuration externalized per environment
- Sign every distributed artifact

## Recommended Operational Controls
- Issue activation keys per machine ID
- Track delivered machine IDs in an admin register
- Avoid sharing one universal activation key across clients
- Store signed release hashes with each delivery batch

## Limits To Acknowledge
- No desktop executable can be made fully uncrackable
- Anti-debug and integrity checks are deterrents, not absolute protection
- Real protection comes from layered controls:
  - licensing
  - machine binding
  - code signing
  - obfuscation
  - operational key management

## Recommended Tools
- PyInstaller for standard bundling
- PyArmor for Python bytecode obfuscation
- Nuitka for stronger compiled distribution builds
- WiX Toolset for MSI packaging
- SignTool or AzureSignTool for code signing
