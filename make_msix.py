import os, zipfile, shutil
DIST="dist/INSITEVA"
MANIFEST=f'''<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
         xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
         xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities">
  <Identity Name="com.insiteva.app" Publisher="CN=INSITEVA" Version="1.0.0.0" />
  <Properties><DisplayName>INSITEVA</DisplayName><PublisherDisplayName>INSITEVA</PublisherDisplayName><Logo>assets\\icon.png</Logo></Properties>
  <Resources><Resource Language="en-us"/></Resources>
  <Dependencies><TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0" MaxVersionTested="10.0.22621.0"/></Dependencies>
  <Applications><Application Id="App" Executable="INSITEVA.exe" EntryPoint="Windows.FullTrustApplication"><uap:VisualElements DisplayName="INSITEVA" Description="INSITEVA" BackgroundColor="transparent" Square150x150Logo="assets\\icon.png" Square44x44Logo="assets\\icon.png"/></Application></Applications>
  <Capabilities><rescap:Capability Name="runFullTrust"/></Capabilities>
</Package>'''
if not os.path.exists(DIST):
    print(f"{DIST} nahi mila - pehle pyinstaller chalao")
    exit(1)
with open(f"{DIST}/AppxManifest.xml","w",encoding="utf-8") as f: f.write(MANIFEST)
if os.path.exists("INSITEVA.msix"): os.remove("INSITEVA.msix")
with zipfile.ZipFile("INSITEVA.msix","w",zipfile.ZIP_DEFLATED) as z:
    for r,_,files in os.walk(DIST):
        for file in files:
            fp=os.path.join(r,file)
            z.write(fp, os.path.relpath(fp,DIST))
print("✅ INSITEVA.msix ban gaya!")
