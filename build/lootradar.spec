# PyInstaller recipe for the installed app (LootRadar.exe plus its _internal folder).
# Don't run this by hand: build/build.ps1 runs it, then wraps the result in LootRadarSetup.exe.
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
WORK = os.environ.get("LR_WORK") or os.path.join(SPECPATH, "work")  # set by build.ps1
APP = os.path.join(ROOT, "app")
# Every Loot Radar module, so nothing that's only imported inside a function gets left out.
MODULES = sorted(f[:-3] for f in os.listdir(APP) if f.endswith(".py"))

a = Analysis(
    [os.path.join(APP, "launcher.py")],
    pathex=[APP],
    datas=[
        (os.path.join(APP, "web"), "web"),
        (os.path.join(ROOT, "VERSION"), "."),
        (os.path.join(ROOT, "LICENSE"), "."),
    ],
    hiddenimports=MODULES + [
        "pystray._win32",
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
        "clr",
    ],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LootRadar",
    console=False,  # no black window; everything goes to data\lootradar.log
    icon=os.path.join(ROOT, "art", "loot-radar.ico"),
    version=os.path.join(WORK, "version_info.txt"),  # written by build.ps1
    upx=False,  # packed files upset antivirus programs
)
coll = COLLECT(exe, a.binaries, a.datas, name="LootRadar", upx=False)
