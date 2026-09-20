import os, zipfile, shutil, base64, hashlib
from pathlib import Path

IDENTITY_NAME = "Insiteva.INSITEVA"
PUBLISHER = "CN=4D02E3C1-2496-4104-A71A-89481814EBE0"
VERSION = "1.0.2.0"
EXE_SRC = "dist/INSITEVA.exe"
ALT_SRC = "dist/INSITEVA/INSITEVA.exe"

def sha256_b64(data):
    return base64.b64encode(hashlib.sha256(data).digest()).decode()

def make_blockmap(files_root, files_list):
    # files_list = list of relative paths inside package (excluding BlockMap itself)
    xml = ['<?xml version="1.0" encoding="utf-8"?>','<BlockMap xmlns="http://schemas.microsoft.com/appx/2010/blockmap" HashMethod="http://www.w3.org/2001/04/xmlenc#sha256">']
    for rel in files_list:
        full = os.path.join(files_root, rel)
        size = os.path.getsize(full)
        xml.append(f'  <File Name="{rel}" Size="{size}" LfhSize="{size}">')
        with open(full, 'rb') as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                xml.append(f'    <Block Hash="{sha256_b64(chunk)}" />')
        xml.append('  </File>')
    xml.append('</BlockMap>')
    return "\n".join(xml)

MANIFEST = f'''<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
         xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
         xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities">
  <Identity Name="{IDENTITY_NAME}" Publisher="{PUBLISHER}" Version="{VERSION}" ProcessorArchitecture="x64"/>
  <Properties><DisplayName>INSITEVA</DisplayName><PublisherDisplayName>Insiteva</PublisherDisplayName><Logo>Assets\\StoreLogo.png</Logo></Properties>
  <Dependencies><TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.17763.0" MaxVersionTested="10.0.22621.0" /></Dependencies>
  <Resources><Resource Language="en-us" /></Resources>
  <Applications><Application Id="App" Executable="INSITEVA.exe" EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements DisplayName="INSITEVA" Description="INSITEVA" BackgroundColor="transparent" Square150x150Logo="Assets\\Square150x150Logo.png" Square44x44Logo="Assets\\Square44x44Logo.png" />
    </Application></Applications>
  <Capabilities><rescap:Capability Name="runFullTrust" /></Capabilities>
</Package>'''

CONTENT_TYPES = '''<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="exe" ContentType="application/vnd.microsoft.portable-exe" />
  <Default Extension="dll" ContentType="application/x-msdownload" />
  <Default Extension="png" ContentType="image/png" />
  <Default Extension="xml" ContentType="application/xml" />
</Types>'''

# Clean
if os.path.exists("build_msix"): shutil.rmtree("build_msix")
os.makedirs("build_msix/Assets", exist_ok=True)

src = EXE_SRC if os.path.exists(EXE_SRC) else ALT_SRC
shutil.copy(src, "build_msix/INSITEVA.exe")

# icons
png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII=")
for n in ["Square150x150Logo.png","Square44x44Logo.png","StoreLogo.png"]:
    open(f"build_msix/Assets/{n}","wb").write(png)

Path("build_msix/AppxManifest.xml").write_text(MANIFEST, encoding="utf-8")
Path("build_msix/[Content_Types].xml").write_text(CONTENT_TYPES, encoding="utf-8")

# list files to include (except BlockMap)
files = []
for root,_,fnames in os.walk("build_msix"):
    for fn in fnames:
        full = os.path.join(root, fn)
        rel = os.path.relpath(full, "build_msix").replace("\\","/")
        files.append(rel)

blockmap_xml = make_blockmap("build_msix", files)
Path("build_msix/AppxBlockMap.xml").write_text(blockmap_xml, encoding="utf-8")

# create msix
if os.path.exists("INSITEVA.msix"): os.remove("INSITEVA.msix")
with zipfile.ZipFile("INSITEVA.msix","w",zipfile.ZIP_DEFLATED) as z:
    for root,_,fnames in os.walk("build_msix"):
        for fn in fnames:
            full=os.path.join(root,fn)
            rel=os.path.relpath(full,"build_msix")
            z.write(full, rel)

print(f"VALID MSIX DONE: {os.path.getsize('INSITEVA.msix')} bytes")
