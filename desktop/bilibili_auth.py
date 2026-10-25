"""Official QR login and Windows current-user encrypted session storage."""

import ctypes
import json
import os
import tempfile
from ctypes import wintypes

import requests

from .storage import data_dir

HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com/"}


def vault_path():
    return data_dir() / "bilibili-session.bin"


def protect(value, decrypt=False):
    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]
    raw = ctypes.create_string_buffer(value)
    source = Blob(len(value), ctypes.cast(raw, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    method = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    method.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                       ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    method.restype = wintypes.BOOL
    if not method(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise OSError("B站登录状态无法读取，请重新登录。")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


def load_cookies():
    try:
        value = json.loads(protect(vault_path().read_bytes(), decrypt=True))
        return {"SESSDATA": value["SESSDATA"]} if isinstance(value.get("SESSDATA"), str) else {}
    except (OSError, ValueError, AttributeError, KeyError):
        return {}


def save_cookies(cookies):
    value = cookies.get("SESSDATA")
    if not value:
        raise ValueError("未取得B站登录状态，请重新扫码。")
    encrypted = protect(json.dumps({"SESSDATA": value}).encode())
    path = vault_path()
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".bin")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encrypted)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def revision():
    try:
        return vault_path().stat().st_mtime_ns
    except OSError:
        return 0


class QRLogin:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.key = ""

    def get(self, endpoint, **kwargs):
        response = self.session.get(endpoint, timeout=(5, 8), allow_redirects=False, **kwargs)
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise ValueError("B站登录服务暂时不可用，请稍后重试。")
        return payload.get("data") or {}

    def generate(self):
        data = self.get("https://passport.bilibili.com/x/passport-login/web/qrcode/generate")
        self.key = data["qrcode_key"]
        return data["url"]

    def poll(self):
        data = self.get("https://passport.bilibili.com/x/passport-login/web/qrcode/poll", params={"qrcode_key": self.key})
        code = data.get("code")
        if code == 0:
            # Cookies arrive on the official poll response; never follow the SSO URL.
            if not self.get("https://api.bilibili.com/x/web-interface/nav").get("isLogin"):
                raise ValueError("B站登录未完成，请重新扫码。")
            cookies = {c.name: c.value for c in self.session.cookies
                       if c.name == "SESSDATA" and c.domain.lstrip(".") in ("bilibili.com", "passport.bilibili.com")}
            if not cookies:
                raise ValueError("未取得B站登录状态，请重新扫码。")
            return code, cookies
        if code not in (86101, 86090, 86038):
            raise ValueError("B站登录未完成，请重新扫码。")
        return code, None
