import os, shutil
from pathlib import Path
from PIL import Image

if os.path.exists("build_msix"):
    shutil.rmtree("build_msix")
os.makedirs("build_msix/Assets", exist_ok=True)

# copy exe
shutil.copy("dist/INSITEVA.exe", "build_msix/INSITEVA.exe")

# create 3 logos
Image.new('RGBA', (150,150), (0,120,212,255)).save("build_msix/Assets/Square150x150Logo.png")
Image.new('RGBA', (44,44), (0,120,212,255)).save("build_msix/Assets/Square44x44Logo.png")
Image.new('RGBA', (50,50), (0,120,212,255)).save("build_msix/Assets/StoreLogo.png")

# manifest
Path("build_msix/AppxManifest.xml").write_text('''<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10" xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10" xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities">
  <Identity Name="Insiteva.INSITEVA" Publisher="CN=4D02E3C1-2496-4104-A71A-89481814EBE0" Version="1.0.9.0" ProcessorArchitecture="x64"/>
  <Properties><DisplayName>INSITEVA</DisplayName><PublisherDisplayName>Insiteva</PublisherDisplayName><Logo>Assets\\StoreLogo.png</Logo></Properties>
  <Dependencies><TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0" MaxVersionTested="10.0.22621.0" /></Dependencies>
  <Resources><Resource Language="en-us" /></Resources>
  <Applications><Application Id="App" Executable="INSITEVA.exe" EntryPoint="Windows.FullTrustApplication"><uap:VisualElements DisplayName="INSITEVA" Description="INSITEVA" BackgroundColor="transparent" Square150x150Logo="Assets\\Square150x150Logo.png" Square44x44Logo="Assets\\Square44x44Logo.png" /></Application></Applications>
  <Capabilities><rescap:Capability Name="runFullTrust" /></Capabilities>
</Package>''', encoding='utf-8')

Path("build_msix/[Content_Types].xml").write_text('<?xml version="1.0" encoding="utf-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="exe" ContentType="application/vnd.microsoft.portable-exe" /><Default Extension="png" ContentType="image/png" /><Default Extension="xml" ContentType="application/xml" /></Types>', encoding='utf-8')
print("folder ready")
