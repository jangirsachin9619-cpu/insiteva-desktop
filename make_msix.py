import os
import shutil
import subprocess
import glob
import pathlib
from PIL import Image

print("Cleaning old files...")
for f in glob.glob("*.msix"):
    os.remove(f)
if os.path.exists("msix_build"):
    shutil.rmtree("msix_build")
os.makedirs("msix_build/assets", exist_ok=True)

# Find EXE
exe_list = glob.glob("dist/*.exe")
if not exe_list:
    exe_list = glob.glob("**/INSITEVA.exe", recursive=True)
if not exe_list:
    raise Exception("EXE not found in dist/ folder")
print(f"Found {exe_list[0]}")
shutil.copy(exe_list[0], "msix_build/INSITEVA.exe")

# Copy assets if exists
if os.path.exists("assets"):
    for item in os.listdir("assets"):
        s = os.path.join("assets", item)
        d = os.path.join("msix_build/assets", item)
        if os.path.isfile(s):
            shutil.copy(s, d)

# --- FINAL MANIFEST - Partner Center Valid ---
manifest = """<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
         xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
         IgnorableNamespaces="uap">
  <Identity Name="Insiteva.INSITEVA" Publisher="CN=4D02E3C1-2496-4104-A71A-89481814EBE0" Version="1.0.13.0" />
  <Properties>
    <DisplayName>INSITEVA</DisplayName>
    <PublisherDisplayName>Insiteva</PublisherDisplayName>
    <Logo>assets\\StoreLogo.png</Logo>
  </Properties>
  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0" MaxVersionTested="10.0.26100.0" />
  </Dependencies>
  <Resources>
    <Resource Language="en-us" />
  </Resources>
  <Applications>
    <Application Id="App" Executable="INSITEVA.exe" EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements DisplayName="INSITEVA"
        Description="INSITEVA Desktop App"
        BackgroundColor="transparent"
        Square150x150Logo="assets\\Square150x150Logo.png"
        Square44x44Logo="assets\\SmallLogo.png" />
    </Application>
  </Applications>
  <Capabilities>
    <Capability Name="runFullTrust" />
    <Capability Name="internetClient" />
  </Capabilities>
</Package>
"""

with open("msix_build/AppxManifest.xml", "w", encoding="utf-8") as f:
    f.write(manifest)

# Create dummy icons if missing
for name, size in [("StoreLogo.png",(50,50)), ("Square150x150Logo.png",(150,150)), ("SmallLogo.png",(44,44)), ("Square44x44Logo.png",(44,44))]:
    p = f"msix_build/assets/{name}"
    if not os.path.exists(p):
        Image.new('RGBA', size, (0,120,255,255)).save(p)

# Find makeappx.exe (x64 only)
kits = sorted(pathlib.Path(r"C:\Program Files (x86)\Windows Kits\10\bin").rglob("x64/makeappx.exe"), reverse=True)
if not kits:
    raise Exception("makeappx.exe not found")
makeappx = str(kits[0])
print(f"Using {makeappx}")

subprocess.check_call([makeappx, "pack", "/d", "msix_build", "/p", "INSITEVA_1.0.13.0_x64.msix", "/o"])
print("MSIX CREATED SUCCESSFULLY - INSITEVA_1.0.13.0_x64.msix")
