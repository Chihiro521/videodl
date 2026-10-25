"""Tie worker descendants to their GUI-owned Windows job handle."""

import ctypes
import os
from ctypes import wintypes


class ProcessTree:
    def __init__(self, pid):
        self.handle = None
        if os.name != "nt":
            return

        class Limits(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                ("flags", wintypes.DWORD), ("min_working_set", ctypes.c_size_t), ("max_working_set", ctypes.c_size_t),
                ("active_processes", wintypes.DWORD), ("affinity", ctypes.c_size_t),
                ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]

        class Counters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]

        class Extended(ctypes.Structure):
            _fields_ = [("limits", Limits), ("io", Counters), ("process_memory", ctypes.c_size_t),
                ("job_memory", ctypes.c_size_t), ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t)]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.CreateJobObjectW(None, None)
        limits = Extended()
        limits.limits.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        self.kernel = kernel
        configured = handle and kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits))
        if configured:
            # A venv redirector owns a separate job for its interpreter. Nest the
            # actual interpreter first; binding its wrapper first creates sibling
            # jobs that Windows cannot merge afterwards.
            for candidate in [*self.descendants(pid), int(pid)]:
                process = kernel.OpenProcess(0x0101, False, candidate)
                if process:
                    if kernel.AssignProcessToJobObject(handle, process):
                        self.handle = handle
                    kernel.CloseHandle(process)
        if handle and not self.handle:
            kernel.CloseHandle(handle)

    def descendants(self, pid):
        class Entry(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("usage", wintypes.DWORD), ("pid", wintypes.DWORD),
                ("heap", ctypes.c_size_t), ("module", wintypes.DWORD), ("threads", wintypes.DWORD),
                ("parent", wintypes.DWORD), ("priority", wintypes.LONG), ("flags", wintypes.DWORD), ("exe", wintypes.WCHAR * 260)]
        kernel = self.kernel
        kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
        kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
        snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            return []
        entry = Entry()
        entry.size = ctypes.sizeof(entry)
        parents = {}
        try:
            valid = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
            while valid:
                parents[entry.pid] = entry.parent
                valid = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            kernel.CloseHandle(snapshot)
        found, pending = [], [int(pid)]
        while pending:
            parent = pending.pop()
            for child, owner in parents.items():
                if owner == parent and child not in found:
                    found.append(child)
                    pending.append(child)
        return found

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
