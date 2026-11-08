"""
Svit Editor Installer — вікно інсталятора (pywebview).
Запускається з launcher-а: python3 installer_ui.py <папка Resources>
"""
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

RES = Path(sys.argv[1]).resolve()
HOME = Path.home() / ".svit-editor"
PF = HOME / "install-progress.txt"
LOG = HOME / "install.log"


def installed_version():
    v = HOME / "VERSION"
    return v.read_text().strip() if v.exists() and (HOME / "app" / "ui.py").exists() else None


def log_tail(n=14):
    try:
        return "\n".join(LOG.read_text(encoding="utf-8", errors="ignore").splitlines()[-n:])
    except Exception:
        return ""


class Api:
    def __init__(self):
        self.window = None
        self.proc = None

    def ready(self):
        return {"version": (RES / "payload" / "VERSION").read_text().strip(), "installed": installed_version()}

    def action(self, a):
        if a in ("install", "python"):
            if self.proc and self.proc.poll() is None:
                return
            threading.Thread(target=self._run, args=(a,), daemon=True).start()
        elif a == "davinci":
            for name in ("DaVinci Resolve", "DaVinci Resolve Studio"):
                if subprocess.run(["open", "-a", name]).returncode == 0:
                    break
            threading.Timer(0.3, self._close).start()
        elif a == "log":
            subprocess.run(["open", str(LOG)])
        elif a == "quit":
            threading.Timer(0.1, self._close).start()

    def _close(self):
        try:
            self.window.destroy()
        except Exception:
            pass
        import os
        os._exit(0)

    def _js(self, fn, *args):
        try:
            self.window.evaluate_js(f"S.{fn}(" + ",".join(json.dumps(x, ensure_ascii=False) for x in args) + ")")
        except Exception:
            pass

    def _run(self, mode):
        HOME.mkdir(parents=True, exist_ok=True)
        if PF.exists():
            PF.unlink()
        self._js("started", mode)
        self.proc = subprocess.Popen(["/bin/bash", str(RES / "worker.sh"), mode, str(RES), str(PF)],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        seen, result = 0, None
        while True:
            lines = PF.read_text(encoding="utf-8").splitlines() if PF.exists() else []
            last_p = None
            for ln in lines[seen:]:
                f = ln.split("|")
                if f[0] == "P":
                    last_p = f
                elif f[0] in ("D", "E"):
                    result = f
            seen = len(lines)
            if last_p:
                self._js("progress", int(last_p[1]), last_p[2], "|".join(last_p[3:]))
            if result:
                break
            if self.proc.poll() is not None:
                time.sleep(0.4)
                if PF.exists() and len(PF.read_text(encoding="utf-8").splitlines()) > seen:
                    continue
                break
            time.sleep(0.25)
        if not result:
            self._js("error", "Встановлення зупинилось неочікувано.", log_tail())
        elif result[0] == "D":
            self._js("done", result[1], result[2])
        elif result[1] == "nopython":
            self._js("needPython")
        else:
            self._js("error", "|".join(result[2:]), log_tail())


def polish():
    try:
        from AppKit import NSApplication, NSImage, NSAppearance
        from PyObjCTools import AppHelper

        def apply():
            app = NSApplication.sharedApplication()
            icon = RES / "icon.png"
            if icon.exists():
                app.setApplicationIconImage_(NSImage.alloc().initWithContentsOfFile_(str(icon)))
            app.setAppearance_(NSAppearance.appearanceNamed_("NSAppearanceNameDarkAqua"))
            app.activateIgnoringOtherApps_(True)
        AppHelper.callAfter(apply)
    except Exception:
        pass


def main():
    try:
        from Foundation import NSBundle
        info = NSBundle.mainBundle().localizedInfoDictionary() or NSBundle.mainBundle().infoDictionary()
        info["CFBundleName"] = "Svit Editor"
    except Exception:
        pass
    import webview
    api = Api()
    win = webview.create_window("Svit Editor", url=str(RES / "installer.html"), js_api=api,
                                width=640, height=600, resizable=True, min_size=(600, 560), background_color="#111114")
    api.window = win
    webview.start(polish)


if __name__ == "__main__":
    main()
