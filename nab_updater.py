"""nab_updater.exe - NAB update helper (one-folder install).
Called by NAB:  nab_updater.exe <app_dir> <new_dir> <nab_pid>
  app_dir  the install folder (NAB.exe, NAB_Launcher.exe, _internal, ...)
  new_dir  the unpacked new version (same layout)
Waits for NAB to exit, swaps the files with a rollback copy, reopens NAB.
Legacy single-file mode (<current_exe> <new_exe> <pid>) is still understood.
Build: pyinstaller --onefile --noconsole --name nab_updater nab_updater.py
"""
import sys, os, time, subprocess, shutil, ctypes, datetime

LOGDIR = [None]

def log(msg):
    try:
        with open(os.path.join(LOGDIR[0] or os.path.dirname(sys.executable), "nab_update.log"), "a", encoding="utf-8") as f:
            f.write(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " " + msg + "\n")
    except Exception:
        pass

def pid_alive(pid):
    try:
        h = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)
        if not h:
            return False
        r = ctypes.windll.kernel32.WaitForSingleObject(h, 0)
        ctypes.windll.kernel32.CloseHandle(h)
        return r != 0
    except Exception:
        return False

def wait_pid(pid, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        if not pid_alive(pid):
            return True
        time.sleep(0.25)
    return False

def retry(fn, tries=40, delay=0.5):
    """Files can stay locked for a moment after NAB closes (antivirus, child processes)."""
    last = None
    for _ in range(tries):
        try:
            return fn()
        except Exception as e:
            last = e
            time.sleep(delay)
    raise last

def rm(path):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path, ignore_errors=True)
    elif os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass

def swap_folder(app_dir, new_dir):
    """Move every top-level item of the new version into app_dir; the old copy of each goes to
    app_dir\\_old first. Anything not in the new version (the user's own files) stays untouched.
    If a step fails everything is put back."""
    old = os.path.join(app_dir, "_old")
    rm(old)
    os.makedirs(old, exist_ok=True)
    done = []          # (name, had_old)
    try:
        for name in os.listdir(new_dir):
            dst = os.path.join(app_dir, name)
            had = os.path.exists(dst)
            if had:
                retry(lambda: os.replace(dst, os.path.join(old, name)))
            done.append((name, had))
            retry(lambda: shutil.move(os.path.join(new_dir, name), dst))
        return True
    except Exception as e:
        log("ERROR during swap: %r - rolling back" % (e,))
        for name, had in reversed(done):
            dst = os.path.join(app_dir, name)
            try:
                rm(dst)
                if had:
                    os.replace(os.path.join(old, name), dst)
            except Exception as e2:
                log("ROLLBACK problem for %s: %r" % (name, e2))
        return False

def start_app(app_dir):
    for exe in ("NAB_Launcher.exe", "NAB.exe"):
        p = os.path.join(app_dir, exe)
        if os.path.exists(p):
            try:
                subprocess.Popen([p], cwd=app_dir)
                log("started " + exe)
                return True
            except Exception as e:
                log("ERROR start %s: %r" % (exe, e))
    return False

def main_folder(app_dir, new_dir, pid):
    LOGDIR[0] = app_dir
    log("Updater started (folder mode) pid=%s" % pid)
    if not os.path.exists(os.path.join(new_dir, "NAB.exe")):
        log("ERROR: new version incomplete: " + new_dir)
        start_app(app_dir)
        return 1
    if pid:
        if not wait_pid(pid, 40):
            log("WARNING: NAB did not exit in time, trying anyway")
    time.sleep(0.8)
    flag = os.path.join(app_dir, "update_ok.flag")
    rm(flag)
    ok = swap_folder(app_dir, new_dir)
    log("swap " + ("complete" if ok else "FAILED (old version kept)"))
    start_app(app_dir)
    if ok:
        # the new version must report that it started. If it never does, go back to the old files
        # (this is only a safety net for a broken build; the update is still required).
        end = time.time() + 75
        while time.time() < end and not os.path.exists(flag):
            time.sleep(1)
        if os.path.exists(flag):
            log("new version started fine")
            rm(os.path.join(app_dir, "_old"))
        else:
            log("ERROR: new version did not start - restoring the old version")
            old = os.path.join(app_dir, "_old")
            try:
                for _ in range(10):
                    subprocess.call(["taskkill", "/F", "/IM", "NAB.exe"], creationflags=0x08000000)
                    time.sleep(0.5)
                for name in os.listdir(old):
                    dst = os.path.join(app_dir, name)
                    rm(dst)
                    retry(lambda: os.replace(os.path.join(old, name), dst))
                start_app(app_dir)
                log("old version restored")
            except Exception as e:
                log("RESTORE FAILED: %r" % (e,))
            return 1
    rm(os.path.join(app_dir, "_update"))
    return 0 if ok else 1

def main_single(current, new, pid):
    d = os.path.dirname(current)
    LOGDIR[0] = d
    log("Updater started (single-file mode) pid=%s" % pid)
    if not os.path.exists(new):
        log("ERROR: new file missing: " + new)
        return 1
    if pid:
        wait_pid(pid, 30)
    else:
        time.sleep(2)
    time.sleep(0.5)
    old = current + ".old"
    try:
        rm(old)
        os.rename(current, old)
        os.rename(new, current)
        log("Swap complete")
    except Exception as e:
        log("ERROR swap: " + str(e))
        try:
            if not os.path.exists(current) and os.path.exists(old):
                os.rename(old, current)
        except Exception:
            pass
        return 1
    time.sleep(0.3)
    try:
        subprocess.Popen([current])
    except Exception as e:
        log("ERROR launch: " + str(e))
        return 1
    return 0

def main():
    if len(sys.argv) < 3:
        sys.exit(1)
    a, b = sys.argv[1], sys.argv[2]
    pid = int(sys.argv[3]) if len(sys.argv) >= 4 and sys.argv[3].isdigit() else 0
    if os.path.isdir(a) and os.path.isdir(b):
        sys.exit(main_folder(a, b, pid))
    sys.exit(main_single(a, b, pid))

if __name__ == "__main__":
    main()
