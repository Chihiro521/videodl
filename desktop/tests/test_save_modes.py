"""Final-file placement and temporary workspaces are independent choices."""

import copy
import errno
from pathlib import Path

import pytest

from desktop.adapter import Adapter, DesktopError, media_key
from desktop.output import publish_file
from desktop.tests.test_adapter import parse_fixture


@pytest.mark.parametrize("mode", ["flat", "by_work", "by_type"])
def test_all_outputs_follow_save_mode_without_exposing_scratch(tmp_path, media_server, mode):
    output = tmp_path / "成品"
    server, _ = media_server
    scratch = []
    def report(event, **values):
        if event == "scratch":
            path = Path(values["path"])
            assert not path.is_relative_to(output)
            scratch.append(path)
    adapter = Adapter(output, report, common=False)
    infos = parse_fixture(adapter, server)
    assert not output.exists(), "parsing must not create source folders in the destination"
    result = adapter.download(infos, {"video": True, "audio": True, "cover": True}, save_mode=mode)
    assert result["status"] == "done", result["errors"]
    files = {f["kind"]: Path(f["path"]) for f in result["files"]}
    if mode == "flat":
        assert all(path.parent == output for path in files.values())
    elif mode == "by_work":
        assert {path.parent.name for path in files.values()} == {infos[0].title}
        assert len(list(output.iterdir())) == 1
    else:
        assert {kind: path.parent.name for kind, path in files.items()} == {"video": "视频", "audio": "音频", "cover": "封面"}
    assert scratch and not any(path.exists() for path in scratch)
    assert not list(output.rglob("*VideoClient*"))
    adapter.close()


def test_same_title_works_get_separate_folders_and_retry_reuses_its_folder(tmp_path, media_server):
    adapter = Adapter(tmp_path / "output", common=False)
    first = parse_fixture(adapter, media_server[0])[0]
    second = copy.deepcopy(first)
    first.identifier, second.identifier = "first-work", "second-work"
    folders = {}
    result = adapter.download([first, second], {"video": True, "audio": True}, save_mode="by_work", folders=folders)
    assert result["status"] == "done", result["errors"]
    by_work = {}
    for f in result["files"]:
        by_work.setdefault(f["item_key"], set()).add(Path(f["path"]).parent)
    assert len(by_work) == 2 and all(len(paths) == 1 for paths in by_work.values())
    assert len({next(iter(paths)) for paths in by_work.values()}) == 2
    key = media_key(first)
    retry = adapter.download([first], {"cover": True}, save_mode="by_work", folders=folders)
    assert retry["status"] == "done"
    assert Path(retry["files"][0]["path"]).parent == next(iter(by_work[key]))
    assert len(list(adapter.output.iterdir())) == 2
    adapter.close()


@pytest.mark.parametrize("mode", ["by_work", "by_type"])
def test_failed_download_removes_only_its_new_empty_folders(tmp_path, media_server, monkeypatch, mode):
    output = tmp_path / "output"
    output.mkdir()
    existing = output / "音频"
    existing.mkdir()
    adapter = Adapter(output, common=False)
    infos = parse_fixture(adapter, media_server[0])
    def fail(*args, **kwargs):
        raise DesktopError("测试下载失败")
    monkeypatch.setattr(adapter, "fetch_media", fail)
    result = adapter.download(infos, {"video": True}, save_mode=mode)
    assert result["status"] == "failed" and not result["files"]
    assert list(output.iterdir()) == [existing]
    adapter.close()


@pytest.mark.parametrize("fail_copy", [False, True])
def test_cross_disk_publication_keeps_staging_outside_results(tmp_path, monkeypatch, fail_copy):
    import desktop.output as output_module
    source = tmp_path / "cache" / "download.mp4"
    source.parent.mkdir()
    source.write_bytes(b"finished-media")
    output = tmp_path / "results"
    output.mkdir()
    target = output / "成品.mp4"
    original_move = output_module.os.rename if output_module.os.name == "nt" else output_module.os.link
    def move(start, end):
        if Path(start) == source:
            raise OSError(errno.EXDEV, "another volume")
        return original_move(start, end)
    monkeypatch.setattr(output_module.os, "rename" if output_module.os.name == "nt" else "link", move)
    original_copy = output_module.shutil.copyfile
    def copy_file(start, end):
        assert not target.exists()
        assert not Path(end).is_relative_to(output)
        if fail_copy:
            Path(end).write_bytes(b"partial")
            raise OSError("copy interrupted")
        return original_copy(start, end)
    monkeypatch.setattr(output_module.shutil, "copyfile", copy_file)
    if fail_copy:
        with pytest.raises(OSError, match="interrupted"):
            publish_file(source, target)
        assert not list(output.iterdir()) and source.is_file()
    else:
        assert publish_file(source, target) == target
        assert target.read_bytes() == b"finished-media" and not source.exists()
    assert not list(tmp_path.glob(".videodl-publish-*"))


def test_real_download_across_local_volumes(tmp_path, media_server):
    import tempfile
    root = Path.cwd() / "build"
    if not root.is_dir() or root.drive.casefold() == tmp_path.drive.casefold():
        pytest.skip("requires two local volumes")
    with tempfile.TemporaryDirectory(prefix="cross-volume-", dir=root) as directory:
        output = Path(directory) / "成品"
        adapter = Adapter(output, common=False, workspace=tmp_path / "cache")
        infos = parse_fixture(adapter, media_server[0])
        result = adapter.download(infos, {"video": True, "audio": True})
        assert result["status"] == "done", result["errors"]
        assert len(result["files"]) == 2
        assert all(Path(f["path"]).parent == output for f in result["files"])
        assert len(list(output.iterdir())) == 2
        assert not list(Path(directory).glob(".videodl-publish-*"))
