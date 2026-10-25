import ast

from desktop.build import PublicDefaults
from desktop import build
import os


def test_public_build_removes_defaults_without_changing_api_structure():
    original = '''
API_TOKEN = "example-private-service-token"
headers = {"Cookie": "account=example-value", "User-Agent": "Example public user agent"}
def f(url, cookies=None):
    return url, cookies
'''
    transform = PublicDefaults()
    tree = transform.visit(ast.parse(original))
    result = ast.unparse(ast.fix_missing_locations(tree))
    assert "example-private-service-token" not in result
    assert "account=example-value" not in result
    assert "Example public user agent" in result
    assert "def f(url, cookies=None)" in result
    assert len(transform.removed) == 2


def test_staged_sources_clear_reused_values_and_preserve_originals(tmp_path, monkeypatch):
    upstream = tmp_path / "videodl"
    upstream.mkdir()
    desktop = tmp_path / "desktop"
    desktop.mkdir()
    original = 'API_TOKEN = "example-service-default"\nreused = ["example-service-default"]\n'
    (upstream / "example.py").write_text(original, encoding="utf-8")
    monkeypatch.setattr(build, "ROOT", tmp_path)
    monkeypatch.setattr(build, "WORK", tmp_path / "work")
    stage = build.stage_sources()
    assert "example-service-default" not in (stage / "videodl/example.py").read_text(encoding="utf-8")
    assert (upstream / "example.py").read_text(encoding="utf-8") == original


def test_build_dll_search_does_not_inherit_other_apps(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "C:/other-application/poppler/bin")
    monkeypatch.setenv("QT_PLUGIN_PATH", "C:/other-application/qt/plugins")
    environment = build.isolated_environment(tmp_path / "stage", tmp_path / "tools")
    assert "other-application" not in environment["PATH"]
    assert "QT_PLUGIN_PATH" not in environment
    assert environment["PYTHONPATH"] == str(tmp_path / "stage")
