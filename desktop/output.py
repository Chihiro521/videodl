"""Owned workspaces and collision-free publication of finished downloads."""

import errno
import os
import shutil
import tempfile
from pathlib import Path


def temporary_root():
    from .storage import data_dir
    root = data_dir() / "temp"
    root.mkdir(parents=True, exist_ok=True)
    return root


def unique_path(path):
    candidate, number = path, 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} ({number}){path.suffix}")
        number += 1
    return candidate


def reserve_folder(root, title):
    number = 0
    while True:
        path = root / (title if not number else f"{title} ({number})")
        try:
            path.mkdir()
            return path
        except FileExistsError:
            number += 1


def publish_file(source, target, staging_root=None, report=lambda *a, **k: None):
    """Finish on the destination disk before exposing the final file name."""
    target.parent.mkdir(parents=True, exist_ok=True)
    while True:
        candidate = unique_path(target)
        try:
            if os.name == "nt":
                os.rename(source, candidate)
            else:
                os.link(source, candidate)
                source.unlink()
            return candidate
        except FileExistsError:
            continue
        except OSError as exc:
            if exc.errno != errno.EXDEV and getattr(exc, "winerror", None) != 17:
                raise
            # Keep the cross-disk copy outside the user's result directory.
            parent = Path(staging_root) if staging_root is not None else target.parent.parent
            with tempfile.TemporaryDirectory(prefix=".videodl-publish-", dir=parent) as scratch:
                report("scratch", path=scratch)
                temporary = Path(scratch) / target.name
                shutil.copyfile(source, temporary)
                finished = publish_file(temporary, target)
            source.unlink()
            return finished
