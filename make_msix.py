import os, shutil, subprocess, glob

# clean old
for f in glob.glob("*.msix"):
    os.remove(f)
if os.path.exists("msix_build"):
    shutil.rmtree("msix_build")

os.makedirs("msix_build", exist_ok=True)

# copy exe from dist
exe_path = glob.glob("dist/*.exe")
if not exe_path:
    exe_path = glob.glob("**/INSITEVA.exe", recursive=True)
if not exe_path:
    raise Exception("EXE not found in dist/")

shutil.copy(exe_path[0], "msix_build/INSITEVA.exe")

# copy assets if exists
if os.path.exists("assets"):
    shutil.copytree("assets", "msix_build/assets", dirs_exist_ok=True)

# create AppxManifest.xml
manifest = """<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
         xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
         xmlns:uap10="http://schemas.microsoft.com/appx/manifest/uap/windows10/10">
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

# create dummy images if missing
from PIL import Image
os.makedirs("msix_build/assets", exist_ok=True)
for name, size in [("StoreLogo.png",(50,50)), ("Square150x150Logo.png",(150,150)), ("SmallLogo.png",(44,44)), ("Square44x44Logo.png",(44,44))]:
    p = f"msix_build/assets/{name}"
    if not os.path.exists(p):
        Image.new('RGBA', size, (0,120,255,255)).save(p)

# make msix
# find makeappx
makeappx = r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\makeappx.exe"
if not os.path.exists(makeappx):
    # try find any version
    import pathlib
    kits = list(pathlib.Path(r"C:\Program Files (x86)\Windows Kits\10\bin").rglob("makeappx.exe"))
    if kits:
        makeappx = str(kits[0])

print(f"Using {makeappx}")
subprocess.check_call([makeappx, "pack", "/d", "msix_build", "/p", "INSITEVA_1.0.12.0_x64.msix", "/o"])
print("MSIX created!")
