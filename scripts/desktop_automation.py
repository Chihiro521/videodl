"""Trusted stdlib-only helpers. Upstream modules are never imported here."""

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPOSITORY = "Chihiro521/videodl"
UPSTREAM = "https://github.com/CharlesPikachu/videodl.git"
OWNED = (".github", "desktop", "scripts/desktop_automation.py", "scripts/desktop_release.py", "scripts/tests", "scripts/sync-desktop.ps1", "requirements-desktop.txt", "启动桌面版.vbs")
GENERATED = ("daily_test_results",)
SHA = re.compile(r"[0-9a-f]{40}")
VERSION = re.compile(r"\d+\.\d+\.\d+")


def run(root, *args, check=True):
    result = subprocess.run(args, cwd=root, text=True, encoding="utf-8", capture_output=True)
    if check and result.returncode:
        # Never echo subprocess stderr: HTTP failures can contain signed URLs.
        raise RuntimeError(f"{args[0]} 操作失败（退出码 {result.returncode}）。请查看对应步骤。")
    return result


def git(root, *args, check=True):
    return run(root, "git", *args, check=check)


def read_version(text):
    for statement in ast.parse(text).body:
        if isinstance(statement, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__version__" for t in statement.targets):
            value = ast.literal_eval(statement.value)
            if isinstance(value, str) and VERSION.fullmatch(value):
                return value
    raise ValueError("版本号必须是静态的 X.Y.Z 字符串。")


def owned(path):
    return any(path == prefix or path.startswith(prefix + "/") for prefix in OWNED)


def generated(path):
    return any(path == prefix or path.startswith(prefix + "/") for prefix in GENERATED)


def changed_files(root, base, head="HEAD"):
    return [p for p in git(root, "diff", "--name-only", "-z", base, head).stdout.split("\0") if p]


def commit(root, message):
    git(root, "-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com", "commit", "-m", message)


def pending(root, revision, conflicts):
    git(root, "merge", "--abort")
    path = root / "desktop/upstream-pending.json"
    path.write_text(json.dumps({"upstream_revision": revision, "conflicts": conflicts}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    git(root, "add", "--", "desktop/upstream-pending.json")
    commit(root, "desktop: record upstream update requiring adaptation")
    return {"blocked": True, "conflicts": conflicts, "preserved": []}


def merge_upstream(root, revision):
    if not SHA.fullmatch(revision):
        raise ValueError("上游提交号无效。")
    base = git(root, "rev-parse", "HEAD").stdout.strip()
    merge_base = git(root, "merge-base", base, revision).stdout.strip()
    incoming = changed_files(root, merge_base, revision)
    preserved = [p for p in incoming if owned(p) or generated(p)]
    git(root, "merge", "--no-commit", "--no-ff", revision, check=False)
    if git(root, "rev-parse", "--verify", "MERGE_HEAD", check=False).returncode:
        raise ValueError("无法建立上游合并，请检查 Git 历史。")
    # Keep the desktop automation, dependency lock and entrypoint exactly as
    # reviewed on the target branch, even when upstream modifies them.
    existing = set(git(root, "ls-tree", "-r", "-z", "--name-only", base).stdout.split("\0"))
    present = existing | set(git(root, "ls-files", "-z").stdout.split("\0"))
    restore = [p for p in OWNED + GENERATED if any(f == p or f.startswith(p + "/") for f in present)]
    git(root, "restore", "--source=" + base, "--staged", "--worktree", "--", *restore)
    conflicts = [p for p in git(root, "diff", "-z", "--name-only", "--diff-filter=U").stdout.split("\0") if p]
    if conflicts:
        return pending(root, revision, conflicts)
    try:
        version = read_version(git(root, "show", f"{revision}:videodl/__init__.py").stdout)
    except (SyntaxError, ValueError):
        return pending(root, revision, ["videodl/__init__.py：需要人工确认版本元数据"])
    path = root / "desktop/upstream.json"
    path.write_text(json.dumps({"core_version": version, "upstream_revision": revision,
                               "repository": "CharlesPikachu/videodl"}, indent=2) + "\n", encoding="utf-8")
    git(root, "add", "--", "desktop/upstream.json")
    commit(root, "desktop: sync reviewed-boundary upstream snapshot " + revision[:12])
    return {"blocked": False, "conflicts": [], "preserved": preserved}


def guard(root, base, branch):
    if (root / "desktop/upstream-pending.json").exists():
        raise ValueError("上游合并仍有待处理项，请先修复 upstream-pending.json 中的冲突并移除此记录。")
    info = json.loads((root / "desktop/upstream.json").read_text(encoding="utf-8-sig"))
    revision = info.get("upstream_revision", "")
    if not SHA.fullmatch(revision) or git(root, "merge-base", "--is-ancestor", revision, "HEAD", check=False).returncode:
        raise ValueError("上游记录必须对应已包含在当前历史中的完整提交。")
    if branch.startswith("codex/sync-upstream-"):
        forbidden = [p for p in changed_files(root, base) if (owned(p) and p != "desktop/upstream.json") or generated(p)]
        if forbidden:
            raise ValueError("同步 PR 修改了桌面维护文件，请改用单独的适配 PR：" + ", ".join(forbidden))
    print("自动化边界与上游版本记录检查通过。")


def summarize(text):
    destination = os.environ.get("GITHUB_STEP_SUMMARY")
    if destination:
        with open(destination, "a", encoding="utf-8") as stream:
            stream.write(text + "\n")
    print(text)


def sync(root, publish=False):
    if git(root, "status", "--porcelain", "--untracked-files=no").stdout.strip():
        raise ValueError("请先保存已跟踪文件的改动。")
    git(root, "fetch", "origin", "desktop")
    git(root, "fetch", UPSTREAM, "master:refs/remotes/trusted-upstream/master")
    revision = git(root, "rev-parse", "refs/remotes/trusted-upstream/master").stdout.strip()
    if git(root, "merge-base", "--is-ancestor", revision, "origin/desktop", check=False).returncode == 0:
        summarize("已包含上游最新提交；本次没有创建 PR。")
        return
    shared = git(root, "merge-base", "origin/desktop", revision).stdout.strip()
    if not any(not generated(p) for p in changed_files(root, shared, revision)):
        summarize("上游仅更新测试报告或示例视频；本次没有创建源码同步 PR。")
        return
    prs = json.loads(run(root, "gh", "pr", "list", "--repo", REPOSITORY, "--base", "desktop", "--state", "open", "--json", "number,headRefName,url").stdout) if publish else []
    existing = next((p for p in prs if p["headRefName"].startswith("codex/sync-upstream-")), None)
    if existing:
        summarize("已有待处理的同步 PR，保留其中的人工修改：" + existing["url"])
        return
    branch = "codex/sync-upstream-" + revision[:12]
    previous = json.loads(run(root, "gh", "pr", "list", "--repo", REPOSITORY, "--head", branch, "--state", "all", "--json", "url").stdout) if publish else []
    if previous:
        summarize("此上游版本已有处理记录；等待上游新提交：" + previous[0]["url"])
        return
    git(root, "switch", "-c", branch, "origin/desktop")
    base = git(root, "rev-parse", "HEAD").stdout.strip()
    result = merge_upstream(root, revision)
    if not publish:
        summarize("已准备同步分支：" + branch + "。请先审查变更，再运行测试。")
        return
    body = ["自动同步原作者 master 到桌面版，等待检查与维护者确认。", "",
            f"上游提交：https://github.com/CharlesPikachu/videodl/commit/{revision}", "",
            "此任务仅进行 Git 合并与静态元数据读取，未导入或运行新增上游模块。",
            "桌面代码、工作流、固定依赖和启动入口继续采用 desktop 分支版本。", ""]
    if result["blocked"]:
        body += ["合并需要人工适配，本 PR 仅记录待处理提交；运行测试前请先解决下列冲突：", *[f"- `{json.dumps(p, ensure_ascii=True)}`" for p in result["conflicts"]], ""]
    body += ["保留桌面版本、未引入的上游维护文件：", *[f"- `{json.dumps(p, ensure_ascii=True)}`" for p in result["preserved"]], "",
             "本 PR 变更文件：", *[f"- `{json.dumps(p, ensure_ascii=True)}`" for p in changed_files(root, base)], "",
             "检查通过后将草稿标记为可审查，再确认合入。代码扫描通过仍需核对本次变更。"]
    report = Path(os.environ.get("RUNNER_TEMP", root / "build")) / "desktop-upstream-pr.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(body) + "\n", encoding="utf-8")
    run(root, "gh", "auth", "setup-git")
    git(root, "push", "--set-upstream", "origin", branch)
    url = run(root, "gh", "pr", "create", "--repo", REPOSITORY, "--base", "desktop", "--head", branch,
              "--draft", "--title", "同步上游：" + revision[:12], "--body-file", str(report)).stdout.strip()
    # GITHUB_TOKEN-created PRs may await workflow approval. Explicit dispatch
    # runs the preserved workflow on this exact branch without a personal token.
    for workflow in ("desktop-analysis.yml", "desktop-ci.yml"):
        run(root, "gh", "workflow", "run", workflow, "--repo", REPOSITORY, "--ref", branch)
    summarize("已创建同步草稿 PR 并启动检查：" + url)


def release_target(root, requested, ref):
    if ref != "refs/heads/desktop" and not re.fullmatch(r"refs/tags/desktop-v\d+\.\d+\.\d+", ref):
        raise ValueError("发行构建请选择 desktop 分支或 desktop-vX.Y.Z 标签。")
    git(root, "fetch", "origin", "desktop")
    revision = git(root, "rev-parse", "HEAD").stdout.strip()
    if git(root, "merge-base", "--is-ancestor", revision, "origin/desktop", check=False).returncode:
        raise ValueError("发行提交尚未合入 desktop。")
    version = read_version((root / "desktop/__init__.py").read_text(encoding="utf-8-sig"))
    if requested and requested != version:
        raise ValueError("输入版本须与 desktop/__init__.py 一致；请先通过 PR 更新版本。")
    tag = "desktop-v" + version
    if ref.startswith("refs/tags/") and ref != "refs/tags/" + tag:
        raise ValueError("标签与源码版本不一致。")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(f"tag={tag}\nrevision={revision}\nversion={version}\n")
    return tag, revision


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("sync", "guard", "release-target"))
    parser.add_argument("--base", default="origin/desktop")
    parser.add_argument("--branch", default=os.environ.get("BRANCH_NAME", ""))
    parser.add_argument("--publish-pr", action="store_true")
    args = parser.parse_args()
    root = Path.cwd()
    if args.action == "sync":
        sync(root, args.publish_pr)
    elif args.action == "guard":
        guard(root, args.base, args.branch)
    else:
        print(release_target(root, os.environ.get("REQUESTED_VERSION", ""), os.environ["GITHUB_REF"])[0])


if __name__ == "__main__":
    main()
