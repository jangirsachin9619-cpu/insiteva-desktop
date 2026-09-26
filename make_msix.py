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
    raise Exception("EXE not found! dist/ folder empty")

print(f"Found EXE: {exe_list[0]}")
shutil.copy(exe_list[0], "msix_build/INSITEVA.exe")

# Copy assets if exists
if os.path.exists("assets"):
    for item in os.listdir("assets"):
        s = os.path.join("assets", item)
        d = os.path.join("msix_build/assets", item)
        if os.path.isfile(s):
            shutil.copy(s, d)

# Create Manifest
manifest = """<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
         xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10">
  <Identity Name="INSITEVA.App" Publisher="CN=INSITEVA" Version="1.0.12.0" />
  <Properties>
    <DisplayName>INSITEVA</DisplayName>
    <PublisherDisplayName>INSITEVA</PublisherDisplayName>
    <Logo>assets\\StoreLogo.png</Logo>
  </Properties>
  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0" MaxVersionTested="10.0.26100.0" />
  </Dependencies>
  <Resources><Resource Language="en-us" /></Resources>
  <Applications>
    <Application Id="INSITEVA" Executable="INSITEVA.exe" EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements DisplayName="INSITEVA" Description="INSITEVA Desktop"
        BackgroundColor="transparent" Square150x150Logo="assets\\Square150x150Logo.png"
        Square44x44Logo="assets\\SmallLogo.png" />
    </Application>
  </Applications>
  <Capabilities><Capability Name="runFullTrust" /></Capabilities>
</Package>
"""
with open("msix_build/AppxManifest.xml", "w", encoding="utf-8") as f:
    f.write(manifest)

# Create dummy icons if missing
for name, size in [("StoreLogo.png",(50,50)), ("Square150x150Logo.png",(150,150)), ("SmallLogo.png",(44,44)), ("Square44x44Logo.png",(44,44))]:
    p = f"msix_build/assets/{name}"
    if not os.path.exists(p):
        Image.new('RGBA', size, (0,120,255,255)).save(p)
        print(f"Created {p}")

# Find CORRECT makeappx.exe - MUST be x64, not arm64
kits_root = pathlib.Path(r"C:\Program Files (x86)\Windows Kits\10\bin")
x64_kits = sorted(kits_root.rglob("x64/makeappx.exe"), reverse=True)

if not x64_kits:
    raise Exception("makeappx.exe x64 not found!")

makeappx = str(x64_kits[0])
print(f"Using: {makeappx}")

subprocess.check_call([makeappx, "pack", "/d", "msix_build", "/p", "INSITEVA_1.0.12.0_x64.msix", "/o"])
print("MSIX created SUCCESSFULLY!")
