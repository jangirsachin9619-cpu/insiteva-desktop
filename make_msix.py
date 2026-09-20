import os, zipfile, shutil, base64

IDENTITY_NAME = "Insiteva.INSITEVA"
PUBLISHER = "CN=4D02E3C1-2496-4104-A71A-89481814EBE0"
VERSION = "1.0.1.0"
EXE_SRC = "dist/INSITEVA.exe"
ALT_SRC = "dist/INSITEVA/INSITEVA.exe"

MANIFEST = f'''<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
         xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
         xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities">
  <Identity Name="{IDENTITY_NAME}" Publisher="{PUBLISHER}" Version="{VERSION}" />
  <Properties>
    <DisplayName>INSITEVA</DisplayName>
    <PublisherDisplayName>Insiteva</PublisherDisplayName>
    <Logo>Assets\\StoreLogo.png</Logo>
  </Properties>
  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0" MaxVersionTested="10.0.22621.0" />
  </Dependencies>
  <Resources><Resource Language="en-us" /></Resources>
  <Applications>
    <Application Id="App" Executable="INSITEVA.exe" EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements DisplayName="INSITEVA" Description="INSITEVA Desktop"
        BackgroundColor="transparent" Square150x150Logo="Assets\\Square150x150Logo.png" Square44x44Logo="Assets\\Square44x44Logo.png" />
    </Application>
  </Applications>
  <Capabilities><rescap:Capability Name="runFullTrust" /></Capabilities>
</Package>'''

CONTENT_TYPES = '''<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="exe" ContentType="application/vnd.microsoft.portable-exe" />
  <Default Extension="png" ContentType="image/png" />
  <Default Extension="xml" ContentType="application/xml" />
</Types>'''

# exe find
os.makedirs("build_msix/Assets", exist_ok=True)
if os.path.exists(EXE_SRC):
    shutil.copy(EXE_SRC, "build_msix/INSITEVA.exe")
elif os.path.exists(ALT_SRC):
    shutil.copy(ALT_SRC, "build_msix/INSITEVA.exe")
else:
    print("EXE not found!"); exit(1)

# dummy icons
png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII=")
for n in ["Square150x150Logo.png","Square44x44Logo.png","StoreLogo.png"]:
    open(f"build_msix/Assets/{n}","wb").write(png)

open("build_msix/AppxManifest.xml","w",encoding="utf-8").write(MANIFEST)
open("build_msix/[Content_Types].xml","w",encoding="utf-8").write(CONTENT_TYPES)
open("build_msix/AppxBlockMap.xml","w",encoding="utf-8").write('<BlockMap xmlns="http://schemas.microsoft.com/appx/2010/blockmap"><File Name="AppxManifest.xml"><Block Hash="aGVsbG8=" /></File></BlockMap>')

if os.path.exists("INSITEVA.msix"): os.remove("INSITEVA.msix")
with zipfile.ZipFile("INSITEVA.msix","w",zipfile.ZIP_DEFLATED) as z:
    for r,_,files in os.walk("build_msix"):
        for f in files:
            full=os.path.join(r,f)
            z.write(full, os.path.relpath(full,"build_msix"))

print("MSIX OK:", os.path.getsize("INSITEVA.msix"), "with", IDENTITY_NAME, PUBLISHER)
