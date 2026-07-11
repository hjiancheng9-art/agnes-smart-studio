"""Agnes 一键构建脚本

用法:
  python build.py          # → dist/AgnesSetup.exe
  python build.py --quick  # 仅打包 exe，跳过安装包制作
  python build.py --clean  # 清理构建缓存
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
DIST = ROOT / "dist"
BUILD = ROOT / "build"
SPEC_FILE = ROOT / "Agnes.spec"
ISS_FILE = ROOT / "setup.iss"
VERSION = "1.0.0"

# ── 确保依赖 ─────────────────────────────
REQUIRED_PKGS = ["pyinstaller", "Pillow", "requests"]


def check_deps():
    missing = []
    for pkg in REQUIRED_PKGS:
        try:
            __import__(pkg.replace("-", "_"))
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"[*] 安装缺失依赖: {', '.join(missing)}")
        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])


# ── 清理 ─────────────────────────────────
def clean():
    for d in [DIST, BUILD]:
        if d.exists():
            shutil.rmtree(d)
    for spec in ROOT.glob("*.spec"):
        spec.unlink()
    print("[✓] 清理完成")


# ── 构建 EXE ─────────────────────────────
def build_exe():
    print("[*] 构建可执行文件...")

    # 生成 .spec 文件内容
    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['launcher.pyw', 'query_tool.pyw', 'kids_launcher.pyw'],
    pathex=[r'{ROOT}'],
    binaries=[],
    datas=[
        (r'{ROOT / "agnes"}\\__init__.py', 'agnes'),
        (r'{ROOT / "agnes"}\\__main__.py', 'agnes'),
        (r'{ROOT / "agnes"}\\client.py', 'agnes'),
        (r'{ROOT / "agnes"}\\cli.py', 'agnes'),
        (r'{ROOT / "agnes"}\\config.py', 'agnes'),
        (r'{ROOT / "agnes"}\\config.py', '.'),
    ],
    hiddenimports=[
        'agnes', 'agnes.client', 'agnes.cli', 'agnes.config',
        'tkinter', 'tkinter.ttk', 'tkinter.messagebox', 'tkinter.scrolledtext',
        'tkinter.filedialog', 'PIL', 'PIL.Image', 'PIL.ImageTk',
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'pandas', 'notebook',
              'jupyter', 'ipykernel', 'setuptools', 'pip', 'pkg_resources'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe_launcher = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AgnesLauncher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=r'{ROOT / "agnes.ico"}',
)

exe_query = EXE(
    pyz,
    a.scripts,
    [
        ('query_tool.pyw', r'{ROOT / "query_tool.pyw"}', 'DATA')
    ],
    name='AgnesQuery',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=r'{ROOT / "agnes.ico"}',
)

exe_kids = EXE(
    pyz,
    a.scripts,
    [
        ('kids_launcher.pyw', r'{ROOT / "kids_launcher.pyw"}', 'DATA')
    ],
    name='AgnesKids',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=r'{ROOT / "agnes.ico"}',
)
'''

    spec_path = ROOT / "Agnes.spec"
    spec_path.write_text(spec_content, encoding="utf-8")

    # 执行 PyInstaller
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", str(spec_path), "--distpath", str(DIST), "--workpath", str(BUILD)],
        cwd=ROOT,
    )
    if result.returncode != 0:
        print("[✗] PyInstaller 构建失败")
        sys.exit(1)

    print(f"[✓] EXE 构建完成: {DIST}")


# ── 构建安装包 ───────────────────────────
def build_setup():
    """用 Inno Setup 制作安装包"""
    iss = ISS_FILE
    if not iss.exists():
        print(f"[!] 未找到 {iss.name}，跳过安装包制作")
        print("   请安装 Inno Setup 后运行: iscc setup.iss")
        return

    iscc = shutil.which("iscc") or r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if not os.path.exists(iscc):
        print("[!] 未找到 Inno Setup 编译器 (iscc)")
        print("   请安装 Inno Setup 后运行: iscc setup.iss")
        return

    print("[*] 制作安装包...")
    result = subprocess.run([iscc, str(iss)], cwd=ROOT)
    if result.returncode == 0:
        print(f"[✓] 安装包制作完成: {DIST}")
    else:
        print("[✗] 安装包制作失败")


# ── 主入口 ───────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Agnes 构建脚本")
    parser.add_argument("--quick", action="store_true", help="仅打包 EXE，跳过安装包")
    parser.add_argument("--clean", action="store_true", help="清理构建缓存")
    parser.add_argument("--setup-only", action="store_true", help="仅制作安装包（跳过 EXE 构建）")
    args = parser.parse_args()

    if args.clean:
        clean()
        return

    if not args.setup_only:
        check_deps()
        build_exe()

    if not args.quick:
        build_setup()

    print("\n" + "=" * 50)
    print("  🎉 构建完成！")
    print(f"  版本: {VERSION}")
    print(f"  输出: {DIST}")
    print("=" * 50)


if __name__ == "__main__":
    main()
