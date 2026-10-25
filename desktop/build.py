"""Build an allowlisted Windows portable distribution from locked dependencies.

Run: python -m desktop.build. Only build/ and dist/ are written.
"""

import ast
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
import types
import zipfile
from pathlib import Path

import requests

from . import __version__
from .storage import save_json

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "build" / "desktop-package"
DIST = ROOT / "dist" / "desktop"
FORBIDDEN_KEY = re.compile(r"cookie|authorization|api.?key|password|secret|^token$|^API_TOKEN$", re.I)


class PublicDefaults(ast.NodeTransformer):
    """Remove embedded account/service defaults in the build copy only."""
    def __init__(self):
        self.removed = []
        self.removed_values = set()

    def visit_Dict(self, node):
        self.generic_visit(node)
        for index, (key, value) in enumerate(zip(node.keys, node.values)):
            if isinstance(key, ast.Constant) and isinstance(key.value, str) and FORBIDDEN_KEY.search(key.value):
                if isinstance(value, ast.Constant) and isinstance(value.value, str) and len(value.value) > 8:
                    self.removed.append({"line": value.lineno, "field": key.value})
                    self.removed_values.add(value.value)
                    node.values[index] = ast.copy_location(ast.Constant(""), value)
        return node

    def visit_Assign(self, node):
        self.generic_visit(node)
        name = ast.unparse(node.targets[0])
        if FORBIDDEN_KEY.search(name) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str) and len(node.value.value) > 15:
            self.removed.append({"line": node.lineno, "field": name})
            self.removed_values.add(node.value.value)
            node.value = ast.copy_location(ast.Constant(""), node.value)
        return node


def stage_sources():
    stage = WORK / "source"
    audit = []
    for source in (ROOT / "videodl").rglob("*"):
        if not source.is_file() or source.suffix not in {".py", ".js", ".wasm"} or "__pycache__" in source.parts:
            continue
        destination = stage / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix == ".py":
            tree = ast.parse(source.read_text(encoding="utf-8-sig"))
            public = PublicDefaults()
            tree = public.visit(tree)
            destination.write_text(ast.unparse(ast.fix_missing_locations(tree)) + "\n", encoding="utf-8")
            if public.removed:
                audit.append({"file": str(source.relative_to(ROOT)).replace("\\", "/"), "removed_defaults": public.removed})
        else:
            shutil.copy2(source, destination)
    save_json(WORK / "public-build-audit.json", audit)
    for source in (ROOT / "desktop").glob("*.py"):
        destination = stage / "desktop" / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return stage


def assert_public_archive():
    from PyInstaller.archive.readers import ZlibArchiveReader
    originals = set()
    for path in (ROOT / "videodl").rglob("*.py"):
        public = PublicDefaults()
        public.visit(ast.parse(path.read_text(encoding="utf-8-sig")))
        originals.update(public.removed_values)
    archive = ZlibArchiveReader(str(WORK / "pyinstaller/desktop/PYZ-00.pyz"))
    checked = 0
    for name in archive.toc:
        if name != "videodl" and not name.startswith("videodl."):
            continue
        code = archive.extract(name)
        pending = [code]
        while pending:
            value = pending.pop()
            if isinstance(value, types.CodeType):
                pending.extend(value.co_consts)
            elif isinstance(value, (tuple, frozenset)):
                pending.extend(value)
            elif isinstance(value, str) and value in originals:
                raise RuntimeError("Embedded account/service default in bundled module: " + name)
        checked += 1
    if checked < 10:
        raise RuntimeError("Upstream modules are missing from the compiled archive")
    return checked


def media_tools():
    config = json.loads((ROOT / "desktop/media-tools.json").read_text(encoding="utf-8"))
    cache = ROOT / "build/media-cache"
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / config["url"].rsplit("/", 1)[1]
    if not archive.exists():
        with requests.get(config["url"], stream=True, timeout=(30, 120)) as response:
            response.raise_for_status()
            with archive.open("wb") as output:
                for chunk in response.iter_content(1024 * 1024):
                    output.write(chunk)
    if hashlib.file_digest(archive.open("rb"), "sha256").hexdigest() != config["sha256"]:
        raise RuntimeError("Media tool archive checksum mismatch")
    extracted = WORK / "media-tools"
    extracted.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as compressed:
        for entry in compressed.infolist():
            path = extracted / entry.filename
            if not path.resolve().is_relative_to(extracted.resolve()):
                raise RuntimeError("Unexpected archive path")
            compressed.extract(entry, extracted)
    return next(extracted.glob("*/bin")), config


def main():
    if sys.platform != "win32":
        raise SystemExit("Build the Windows package on Windows.")
    if DIST.exists():
        raise SystemExit("dist/desktop already exists. Use a fresh build checkout or rename this output before rebuilding.")
    WORK.mkdir(parents=True, exist_ok=True)
    stage = stage_sources()
    tools, config = media_tools()
    upstream_info = json.loads((ROOT / "desktop/upstream.json").read_text(encoding="utf-8"))
    save_json(WORK / "build-info.json", {"desktop_version": __version__, **upstream_info,
        "desktop_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "media_tools": config["version"]})
    # The spec takes explicit paths rather than the developer's global PATH.
    environment = os.environ.copy()
    environment["VIDEODL_BUILD_TOOLS"] = str(tools)
    environment["PYTHONPATH"] = str(stage)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--distpath", str(DIST),
                    "--workpath", str(WORK / "pyinstaller"), str(ROOT / "desktop/desktop.spec")], cwd=stage, env=environment, check=True)
    checked = assert_public_archive()
    print("Verified public compiled modules:", checked)
    package = DIST / "VideoDL Desktop"
    shutil.copy2(ROOT / "LICENSE", package / "LICENSE.txt")
    shutil.copy2(ROOT / "desktop/README.md", package / "使用说明.md")
    shutil.copy2(WORK / "public-build-audit.json", package / "public-build-audit.json")
    shutil.copy2(WORK / "build-info.json", package / "build-info.json")
    notice = ("VideoDL Desktop " + __version__ + "\nOriginal project: https://github.com/CharlesPikachu/videodl\nDesktop project: https://github.com/Chihiro521/videodl\n\n"
              + config["version"] + "\nBinary: " + config["url"] + "\nFFmpeg source: " + config["source_url"] + "\nBuild scripts and dependency source recipes: " + config["build_source_url"]
              + "\nFFmpeg uses shared libraries; they can be replaced in _internal/tools.\n"
              + "Qt source: https://code.qt.io/cgit/qt/qtbase.git/tag/?h=v6.12.0\n"
              + "PySide source: https://code.qt.io/cgit/pyside/pyside-setup.git/tag/?h=v6.12.0\n\nPython dependency notices:\n")
    for distribution in sorted(importlib.metadata.distributions(), key=lambda d: d.metadata["Name"].lower()):
        name = distribution.metadata["Name"]
        if name.lower() in {"pytest", "pyinstaller", "pyinstaller-hooks-contrib", "pip"}:
            continue
        notice += f"\n{name} {distribution.version}\n"
        for file in distribution.files or []:
            if ("license" in str(file).lower() or "copying" in str(file).lower()) and ".dist-info" in str(file):
                actual = distribution.locate_file(file)
                if actual.is_file() and actual.stat().st_size < 1024 * 1024:
                    notice += actual.read_text(encoding="utf-8", errors="replace") + "\n"
    (package / "THIRD-PARTY-NOTICES.txt").write_text(notice, encoding="utf-8")
    ffmpeg_root = tools.parent
    for file in ffmpeg_root.iterdir():
        if file.is_file() and re.search("license|copying|readme", file.name, re.I):
            shutil.copy2(file, package / ("FFmpeg-" + file.name))
    if any(p.suffix.lower() in {".wvd", ".pkl", ".cookie"} for p in package.rglob("*")):
        raise RuntimeError("Unexpected identity/configuration file in package")
    name = f"VideoDL-Desktop-{__version__}-windows-x64"
    archive = shutil.make_archive(str(DIST / name), "zip", root_dir=DIST, base_dir="VideoDL Desktop")
    sha = hashlib.file_digest(open(archive, "rb"), "sha256").hexdigest()
    (DIST / "SHA256SUMS.txt").write_text(f"{sha}  {Path(archive).name}\n", encoding="ascii")
    print("Portable distribution:", archive)


if __name__ == "__main__":
    main()
