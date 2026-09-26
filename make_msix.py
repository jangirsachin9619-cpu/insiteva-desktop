import os, shutil, subprocess, glob, pathlib
from PIL import Image

print("Cleaning...")
for f in glob.glob("*.msix"): os.remove(f)
if os.path.exists("msix_build"): shutil.rmtree("msix_build")
os.makedirs("msix_build/assets", exist_ok=True)

exe_list = glob.glob("dist/*.exe")
if not exe_list: exe_list = glob.glob("**/INSITEVA.exe", recursive=True)
if not exe_list: raise Exception("EXE not found")
print(f"Found {exe_list[0]}")
shutil.copy(exe_list[0], "msix_build/INSITEVA.exe")

if os.path.exists("assets"):
    for item in os.listdir("assets"):
        s=os.path.join("assets",item); d=os.path.join("msix_build/assets",item)
        if os.path.isfile(s): shutil.copy(s,d)

# --- FIXED MANIFEST - 100% Valid ---
manifest = """<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
         xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
         xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
         IgnorableNamespaces="uap rescap">
  <Identity Name="INSITEVA.App" Publisher="CN=INSITEVA" Version="1.0.12.0" />
  <Properties>
    <DisplayName>INSITEVA</DisplayName>
    <PublisherDisplayName>INSITEVA</PublisherDisplayName>
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
    <rescap:Capability Name="runFullTrust" />
  </Capabilities>
</Package>
"""
with open("msix_build/AppxManifest.xml", "w", encoding="utf-8") as f:
    f.write(manifest)

# create icons if missing
for name, size in [("StoreLogo.png",(50,50)), ("Square150x150Logo.png",(150,150)), ("SmallLogo.png",(44,44))]:
    p=f"msix_build/assets/{name}"
    if not os.path.exists(p):
        Image.new('RGBA', size, (0,120,255,255)).save(p)

# find x64 makeappx ONLY
kits = sorted(pathlib.Path(r"C:\Program Files (x86)\Windows Kits\10\bin").rglob("x64/makeappx.exe"), reverse=True)
makeappx = str(kits[0])
print(f"Using {makeappx}")
subprocess.check_call([makeappx, "pack", "/d", "msix_build", "/p", "INSITEVA_1.0.12.0_x64.msix", "/o"])
print("MSIX CREATED!")
