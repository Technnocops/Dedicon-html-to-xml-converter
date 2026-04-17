# Code Signing Checklist

## Goal
- Reduce Windows SmartScreen warnings
- Provide publisher identity in the installer and EXE
- Protect distribution integrity

## Certificate Options
- OV code-signing certificate for standard business release signing
- EV code-signing certificate for stronger SmartScreen reputation and hardware-backed key storage

## Required Tools
- `signtool.exe` from the Windows SDK
- RFC3161 timestamp URL from the certificate provider
- Secure access to the private key or HSM/token

## Signing Checklist
1. Build the final release bundle and installer first.
2. Sign the main application EXE:
   - `release/portable/Technocops_DDC_Converter_HTML_to_XML_Pro/Technocops_DDC_Converter_HTML_to_XML_Pro.exe`
3. Sign the installer EXE:
   - `release/installer/Technocops_DDC_Converter_HTML_to_XML_Pro_Setup_v1.0.0.exe`
4. Use SHA-256 digest and SHA-256 timestamping.
5. Verify the resulting signatures using:
   - `signtool verify /pa /v <file>`
6. Archive:
   - certificate details
   - timestamp service used
   - signing date
   - signed artifact hashes

## Recommended Command Pattern
```powershell
signtool sign /fd SHA256 /td SHA256 /tr <timestamp-url> /n "<publisher-name>" "<path-to-exe>"
```

## Release Gate
- Do not distribute unsigned client builds.
- Re-sign after every rebuild.
- Keep the certificate private key outside the development workstation when possible.
