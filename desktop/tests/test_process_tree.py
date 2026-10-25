import os
import subprocess
import sys

import pytest

from desktop.jobobject import ProcessTree


@pytest.mark.skipif(os.name != "nt", reason="Windows process tree contract")
def test_closing_engine_job_stops_its_descendants():
    import ctypes
    from ctypes import wintypes
    code = "import subprocess,sys,time;print('ready',flush=True);sys.stdin.readline();p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(90)']);print(p.pid,flush=True);time.sleep(90)"
    process = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    tree = None
    try:
        assert process.stdout.readline().strip() == "ready"
        tree = ProcessTree(process.pid)
        assert tree.handle, "the GUI must own the worker's descendants"
        process.stdin.write("continue\n")
        process.stdin.flush()
        child_pid = int(process.stdout.readline().strip())
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        child = kernel.OpenProcess(0x100001, False, child_pid)
        assert child
        try:
            tree.close()
            process.wait(timeout=5)
            assert kernel.WaitForSingleObject(child, 5000) == 0
        finally:
            if kernel.WaitForSingleObject(child, 0) == 258:
                kernel.TerminateProcess(child, 1)
            kernel.CloseHandle(child)
    finally:
        if tree:
            tree.close()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
