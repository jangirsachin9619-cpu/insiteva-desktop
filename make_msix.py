import os, zipfile, shutil

# Partner Center se match karne wala identity
# Ye wahi hoga jo Partner Center > Product Identity me hai
DIST = "dist"
EXE_NAME = "INSITEVA.exe"
MANIFEST = '''<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
         xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
         xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities">
  <Identity Name="com.insiteva.app" Publisher="CN=StorePublisher" Version="1.0.1.0" />
  <Properties>
    <DisplayName>INSITEVA</DisplayName>
    <PublisherDisplayName>INSITEVA</PublisherDisplayName>
    <Logo>assets\\icon.png</Logo>
  </Properties>
  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0" MaxVersionTested="10.0.22621.0" />
  </Dependencies>
  <Resources>
    <Resource Language="en-us" />
  </Resources>
  <Applications>
    <Application Id="App" Executable="INSITEVA.exe" EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements DisplayName="INSITEVA" Description="INSITEVA Desktop App"
        BackgroundColor="transparent" Square150x150Logo="assets\\icon.png" Square44x44Logo="assets\\icon.png" />
    </Application>
  </Applications>
  <Capabilities>
    <rescap:Capability Name="runFullTrust" />
  </Capabilities>
</Package>'''

# Check exe
exe_path = os.path.join(DIST, EXE_NAME)
if not os.path.exists(exe_path):
    # onefile me dist ke andar direct exe hota hai
    print(f"{exe_path} nahi mila, dist folder check kar raha hu...")
    # agar dist/INSITEVA folder me hai to use copy kar lo
    alt = "dist/INSITEVA/INSITEVA.exe"
    if os.path.exists(alt):
        shutil.copy(alt, exe_path)
    else:
        print("EXE nahi mila - pehle pyinstaller chalao")
        exit(1)

os.makedirs(os.path.join(DIST, "assets"), exist_ok=True)
# icon hai to copy, nahi to blank bana dega
if os.path.exists("background.svg"):
    # simple fallback, store ko png chahiye, svg ko rename karke de rahe hai
    try:
        shutil.copy("background.svg", os.path.join(DIST, "assets", "icon.png"))
    except:
        pass
else:
    # agar icon nahi hai to bhi chale
    if not os.path.exists(os.path.join(DIST, "assets", "icon.png")):
        open(os.path.join(DIST, "assets", "icon.png"), "wb").close()

with open(os.path.join(DIST, "AppxManifest.xml"), "w", encoding="utf-8") as f:
    f.write(MANIFEST)

if os.path.exists("INSITEVA.msix"):
    os.remove("INSITEVA.msix")

with zipfile.ZipFile("INSITEVA.msix", "w", zipfile.ZIP_DEFLATED) as z:
    for r, _, files in os.walk(DIST):
        for file in files:
            fp = os.path.join(r, file)
            z.write(fp, os.path.relpath(fp, DIST))

print("INSITEVA.msix ban gaya! Fixed wala")
