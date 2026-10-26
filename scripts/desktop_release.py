"""Publish a verified build artifact without importing or executing the SDK."""

import hashlib
import json
import os
import re
from pathlib import Path

from desktop_automation import REPOSITORY, run, read_version, git


def verify(root, artifact, tag, revision):
    if not re.fullmatch(r"desktop-v\d+\.\d+\.\d+", tag) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("发行参数无效。")
    version = tag.removeprefix("desktop-v")
    if read_version((root / "desktop/__init__.py").read_text(encoding="utf-8-sig")) != version:
        raise ValueError("发行版本与源码不一致。")
    if git(root, "rev-parse", "HEAD").stdout.strip() != revision:
        raise ValueError("发行任务没有检出预期提交。")
    if git(root, "merge-base", "--is-ancestor", revision, "origin/desktop", check=False).returncode:
        raise ValueError("发行任务的提交尚未合入 desktop。")
    metadata = json.loads((artifact / "VideoDL Desktop/build-info.json").read_text(encoding="utf-8"))
    if metadata.get("desktop_revision") != revision or metadata.get("desktop_version") != version:
        raise ValueError("构建信息与发行提交不一致。")
    filename = f"VideoDL-Desktop-{version}-windows-x64.zip"
    archive = artifact / filename
    lines = (artifact / "SHA256SUMS.txt").read_text(encoding="ascii").splitlines()
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if len(lines) != 1 or lines[0].split() != [digest, filename]:
        raise ValueError("发行包校验值不匹配。")
    return archive


def publish(root, artifact, tag, revision):
    archive = verify(root, artifact, tag, revision)
    previous = run(root, "gh", "release", "view", tag, "--repo", REPOSITORY, check=False)
    if previous.returncode == 0:
        raise ValueError("该版本已有发行记录，请使用新的版本号；已有附件保留。")
    ref = run(root, "gh", "api", f"repos/{REPOSITORY}/git/ref/tags/{tag}", check=False)
    if ref.returncode == 0:
        # Dereference annotated tags through Git, rather than accepting another target.
        git(root, "fetch", "origin", f"refs/tags/{tag}:refs/tags/{tag}")
        if git(root, "rev-parse", tag + "^{commit}").stdout.strip() != revision:
            raise ValueError("已有标签指向其他提交。")
    else:
        run(root, "gh", "api", "--method", "POST", f"repos/{REPOSITORY}/git/refs", "-f", "ref=refs/tags/" + tag, "-f", "sha=" + revision)
    # A bot-created tag does not need a recursive push-triggered workflow: the
    # current workflow has already built and tested this exact commit.
    result = run(root, "gh", "release", "create", tag, str(archive), str(artifact / "SHA256SUMS.txt"),
                 str(artifact / "VideoDL Desktop/build-info.json"), "--repo", REPOSITORY, "--verify-tag", "--target", revision,
                 "--draft", "--title", "VideoDL Desktop v" + tag.removeprefix("desktop-v"),
                 "--notes-file", str(root / "desktop/RELEASE_NOTES.md"))
    print(result.stdout.strip())


if __name__ == "__main__":
    publish(Path.cwd(), Path(os.environ["ARTIFACT_DIR"]), os.environ["RELEASE_TAG"], os.environ["RELEASE_REVISION"])
