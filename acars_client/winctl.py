"""Window control through the Windows API, used by the PAC ACARS engine.

The engine never reaches into the window's own code: it finds the window by its
process and title, asks Windows whether it has hung (the same check that makes
Windows show "Not responding"), and shows, hides, resizes or pins it on top.
Everything here is a no-op on other systems.
"""
from __future__ import annotations

import sys

WIN = sys.platform == "win32"
if WIN:
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.IsHungAppWindow.argtypes = [wintypes.HWND]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]

HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x1, 0x2, 0x4, 0x10, 0x40
SW_HIDE, SW_SHOW, SW_RESTORE = 0, 5, 9


def _title(h):
    n = user32.GetWindowTextLengthW(h)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(h, buf, n + 1)
    return buf.value


def _pid_of(h):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    return pid.value


def find_window(pids, title="PAC ACARS"):
    """The top-level window belonging to one of these processes whose title starts with 'PAC ACARS'."""
    if not WIN or not pids:
        return None
    pids = set(pids)
    found = []

    def cb(h, _l):
        try:
            if _pid_of(h) in pids and user32.GetParent(h) == 0 and _title(h).startswith(title):
                found.append(h)
        except Exception:
            pass
        return True
    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return found[0] if found else None


def child_pids(pid):
    """A process and all its descendants (Edge and Chrome run several processes per window)."""
    if not WIN:
        return [pid]

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]
    parents = {}
    snap = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if snap in (0, -1):
        return [pid]
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            parents.setdefault(e.th32ParentProcessID, []).append(e.th32ProcessID)
            ok = kernel32.Process32NextW(snap, ctypes.byref(e))
    finally:
        kernel32.CloseHandle(snap)
    out, todo = [], [pid]
    while todo:
        p = todo.pop()
        if p not in out:
            out.append(p)
            todo += parents.get(p, [])
    return out


def is_hung(h):
    return bool(WIN and h and user32.IsHungAppWindow(h))


def exists(h):
    return bool(WIN and h and user32.IsWindow(h))


def is_minimized(h):
    return bool(WIN and h and user32.IsIconic(h))


def is_visible(h):
    return bool(WIN and h and user32.IsWindowVisible(h))


def show(h, pulse_top=True, keep_top=False):
    """Restore, show and bring to the front (a brief on-top pulse gets past the simulator and browser)."""
    if not WIN or not h:
        return
    user32.ShowWindow(h, SW_SHOW)
    user32.ShowWindow(h, SW_RESTORE)
    if pulse_top:
        user32.SetWindowPos(h, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
        if not keep_top:
            import threading
            threading.Timer(0.6, lambda: user32.SetWindowPos(h, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)).start()
    user32.SetForegroundWindow(h)


def hide(h):
    if WIN and h:
        user32.ShowWindow(h, SW_HIDE)


def set_topmost(h, on):
    if WIN and h:
        user32.SetWindowPos(h, HWND_TOPMOST if on else HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)


def size_of(h):
    if not WIN or not h:
        return None
    r = wintypes.RECT()
    user32.GetWindowRect(h, ctypes.byref(r))
    return (r.right - r.left, r.bottom - r.top)


def resize(h, w, hgt):
    if WIN and h:
        user32.SetWindowPos(h, 0, 0, 0, int(w), int(hgt), SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE)


def kill_tree(pid):
    """Ends a process and everything it started (Edge and Chrome run several processes per window)."""
    import subprocess
    try:
        if WIN:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True, timeout=10,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            import os
            import signal
            try:
                os.killpg(pid, signal.SIGKILL)  # the window was started in its own process group
            except Exception:
                os.kill(pid, signal.SIGKILL)
    except Exception:
        pass


def find_browser():
    """Microsoft Edge (on every Windows 10/11 PC), else Google Chrome. Their app mode gives a clean, sturdy window."""
    import os
    import shutil
    if os.environ.get("PAC_ACARS_BROWSER"):
        return os.environ["PAC_ACARS_BROWSER"]
    if not WIN:
        return None
    candidates = []
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        if base:
            candidates += [os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                           os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")]
    for c in candidates:
        if os.path.exists(c):
            return c
    return shutil.which("msedge") or shutil.which("chrome")


def pids_named(names):
    """Every running process whose program file is one of these names (e.g. {"msedge.exe"})."""
    if not WIN:
        return []

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]
    names = {n.lower() for n in names}
    out = []
    snap = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if snap in (0, -1):
        return out
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            if e.szExeFile.lower() in names:
                out.append(e.th32ProcessID)
            ok = kernel32.Process32NextW(snap, ctypes.byref(e))
    finally:
        kernel32.CloseHandle(snap)
    return out


def find_app_window(browser_path, title="PAC ACARS"):
    """The PAC ACARS app window in whichever Edge or Chrome process holds it. Edge often hands a new app window to a
    copy of itself that is already running, so the window may not belong to the process PAC ACARS started.
    App windows carry just the page title; ordinary browser windows add ' - Microsoft Edge' or ' - Google Chrome'."""
    import os
    if not WIN or not browser_path:
        return None
    pids = set(pids_named({os.path.basename(browser_path)}))
    if not pids:
        return None
    found = []

    def cb(h, _l):
        try:
            if _pid_of(h) in pids and user32.GetParent(h) == 0:
                t = _title(h)
                if t.startswith(title) and " - " not in t[len(title):]:
                    found.append(h)
        except Exception:
            pass
        return True
    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return found[0] if found else None


def pid_of(h):
    return _pid_of(h) if WIN and h else None


def close(h):
    """Asks a window to close, as clicking its X would (WM_CLOSE)."""
    if WIN and h:
        user32.PostMessageW(h, 0x0010, 0, 0)


def pids_with_arg(text, exe_name=None):
    """Processes whose command line contains this text (e.g. PAC ACARS's own window profile folder).
    Only PAC ACARS uses that folder, so a process found here is a window of ours left behind, never the pilot's browser."""
    import os
    import subprocess
    text_l = text.lower()
    out = []
    if WIN:
        flt = f"-Filter \"Name='{exe_name}'\" " if exe_name else ""
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                                f"Get-CimInstance Win32_Process {flt}| ForEach-Object {{ \"$($_.ProcessId)`t$($_.CommandLine)\" }}"],
                               capture_output=True, text=True, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            for line in r.stdout.splitlines():
                pid, _, cmd = line.partition("\t")
                if pid.strip().isdigit() and text_l in cmd.lower():
                    out.append(int(pid))
        except Exception:
            pass
        return out
    mine, p = set(), os.getpid()  # never ourselves or whatever started us
    while p > 1 and p not in mine:
        mine.add(p)
        try:
            p = int(open(f"/proc/{p}/stat").read().rsplit(")", 1)[1].split()[1])
        except Exception:
            break
    for d in os.listdir("/proc") if os.path.isdir("/proc") else []:
        if d.isdigit() and int(d) not in mine:
            try:
                cmd = open(f"/proc/{d}/cmdline", "rb").read().replace(b"\0", b" ").decode(errors="replace")
            except OSError:
                continue
            if text_l in cmd.lower() and (not exe_name or os.path.basename(cmd.split(" ")[0]).lower() == exe_name.lower()):
                out.append(int(d))
    return out
