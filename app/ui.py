"""
Svit Editor — вікно програми.

Запускається з DaVinci (Workspace → Scripts → Svit Editor) з параметром --session <папка>.
Через цю папку вікно обмінюється командами з DaVinci: оновити список кліпів, зібрати таймлайн.
"""
import argparse
import base64
import io
import json
import os
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import svlog  # noqa: E402
svlog.setup((HERE / "VERSION").read_text().strip() if (HERE / "VERSION").exists() else "dev")
svlog.ssl_fix()
import engine  # noqa: E402
import music  # noqa: E402

HOME = engine.HOME
SHOTS = HOME / "shots"
VERSION = (HERE / "VERSION").read_text().strip() if (HERE / "VERSION").exists() else "dev"
UPDATE_REPO = "SadSwetty/svit-editor"   # GitHub: власник/репозиторій, звідки брати оновлення
RESTART_CODE = 75
BRIDGE_REV = 26        # має збігатися з BRIDGE_REV у resolve/Svit Editor.py
URLS = {"keys": "https://platform.claude.com/settings/keys",
        "billing": "https://platform.claude.com/settings/billing",
        "usage": "https://platform.claude.com/usage"}
FORMAT_LABELS = {"9:16": "9:16 — вертикальне (TikTok, Reels, Shorts)", "4:5": "4:5 — пост Instagram",
                 "1:1": "1:1 — квадрат", "4:3": "4:3 — класичне", "16:9": "16:9 — горизонтальне (YouTube)",
                 "src": "як у джерела"}
LAYOUT_LABELS = {"one": "усе на одному таймлайні, ролики підряд",
                 "separate": "кожне відео на окремому таймлайні"}
LENGTHS = ["на твій розсуд, з урахуванням запиту", "до 15 секунд", "15–30 секунд",
           "30–60 секунд", "1–3 хвилини", "3–10 хвилин"]


# ======================================================================= міст з DaVinci

class Bridge:
    def __init__(self, session):
        self.dir = Path(session) if session else None
        self.n = 0

    @property
    def ok(self):
        return bool(self.dir and (self.dir / "sources.json").exists())

    def stale(self):
        """DaVinci-частина стара (запущена до оновлення) — у ній немає нових ефектів."""
        if not self.dir:
            return False
        try:
            info = json.loads((self.dir / "bridge.json").read_text(encoding="utf-8"))
            return int(info.get("rev", 0)) < BRIDGE_REV
        except Exception:
            return True

    def sources(self):
        try:
            return json.loads((self.dir / "sources.json").read_text(encoding="utf-8"))
        except Exception:
            return {}

    def send(self, cmd, payload=None, timeout=30, on_status=None, cancel=None):
        if not self.dir:
            raise RuntimeError("Svit Editor відкритий не з DaVinci.")
        self.n += 1
        cid = f"{int(time.time() * 1000)}_{self.n}"
        (self.dir / "cmd").mkdir(exist_ok=True)
        (self.dir / "resp").mkdir(exist_ok=True)
        tmp = self.dir / "cmd" / f".{cid}.tmp"
        tmp.write_text(json.dumps({"id": cid, "cmd": cmd, "data": payload}, ensure_ascii=False),
                       encoding="utf-8")
        tmp.rename(self.dir / "cmd" / f"{cid}.json")
        if timeout == 0:
            return None
        resp = self.dir / "resp" / f"{cid}.json"
        status = self.dir / "status.json"
        t0, last = time.time(), None
        while time.time() - t0 < timeout:
            if resp.exists():
                time.sleep(0.05)
                return json.loads(resp.read_text(encoding="utf-8"))
            if on_status and status.exists():
                try:
                    st = status.read_text(encoding="utf-8")
                    if st != last:
                        last = st
                        on_status(json.loads(st))
                except Exception:
                    pass
            time.sleep(0.2)
        raise RuntimeError("DaVinci не відповідає. Перевір, що DaVinci відкритий, і спробуй ще раз.")


# ======================================================================= API для сторінки

def thumb_of(path):
    from PIL import Image
    img = Image.open(path)
    img.thumbnail((140, 140))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def vtuple(v):
    """'2.4-alpha' < '2.4' < '2.4.1': тестові версії йдуть перед релізом з тим самим номером."""
    v = str(v).lower().lstrip("v")
    pre = any(t in v for t in ("alpha", "beta", "rc"))
    core = v.split("-")[0].split(" ")[0]
    out = []
    for part in core.split("."):
        num = "".join(ch for ch in part if ch.isdigit())
        out.append(int(num) if num else 0)
    while len(out) < 3:
        out.append(0)
    return tuple(out) + ((0,) if pre else (1,))


def friendly_error(e):
    svlog.log(f"помилка: {e!r}")
    name, text = type(e).__name__, str(e)
    if "Authentication" in name or "401" in text:
        return "Ключ Claude не підходить. Зміни його в налаштуваннях (шестерня вгорі)."
    if "credit balance" in text.lower() or "billing" in text.lower():
        return "На балансі Claude закінчились кошти. Поповни баланс і спробуй ще раз."
    if "RateLimit" in name or "429" in text:
        return "Забагато запитів до Claude. Зачекай хвилину і спробуй ще раз."
    if "Overloaded" in name or "529" in text:
        return "Claude зараз перевантажений. Спробуй за кілька хвилин."
    if "Connection" in name or "timed out" in text.lower():
        return "Немає з'єднання з інтернетом."
    return text or name


class Api:
    def __init__(self, bridge):
        self.bridge = bridge
        self.window = None
        self.cancel_event = threading.Event()
        self._style_lock = threading.Lock()
        self._style_gen = 0
        self._style_pending = None
        self._style_need = {}
        self._style_thread = None
        self.worker = None
        self._last_push = 0.0
        self.restart_requested = False
        self.last = None   # (папка роботи, кліпи, налаштування) — для правок

    # ---- стан
    def init(self):
        cfg = engine.load_cfg()
        key = cfg.get("api_key", "")
        shots = []
        for p in cfg.get("shots", []):
            try:
                if Path(p).exists():
                    shots.append({"path": p, "thumb": thumb_of(p)})
            except Exception:
                pass
        return {"settings": cfg.get("settings", {}), "has_key": bool(key), "key_tail": key[-4:] if key else "",
                "spend": cfg.get("spend", {}).get(time.strftime("%Y-%m"), 0.0), "version": VERSION,
                "bridge": self.bridge.ok, "sources": self.bridge.sources() if self.bridge.ok else {},
                "shots": shots, "on_top": cfg.get("on_top", True), "rate": engine.TOKENS_PER_USD,
                "refs": self.list_refs()}

    def save_settings(self, st):
        cfg = engine.load_cfg()
        cfg["settings"] = st
        engine.save_cfg(cfg)
        return True

    def estimate(self, st, total_sec, n_sources, n_shots, n_refs=0):
        s = dict(st)
        s["num_videos_n"] = int(st.get("num") or 0) or None
        return engine.estimate(float(total_sec or 0), int(n_sources or 0), s, int(n_shots or 0), int(n_refs or 0))

    def refresh_sources(self, mode):
        try:
            r = self.bridge.send("refresh", {"mode": mode}, timeout=20)
            return r.get("sources", []) if r else []
        except Exception:
            return None

    # ---- скріни
    def _store_shot(self, data, name):
        SHOTS.mkdir(parents=True, exist_ok=True)
        dst = SHOTS / f"{int(time.time() * 1000)}_{Path(name).stem[:40]}.jpg"
        dst.write_bytes(engine.image_bytes(data))
        cfg = engine.load_cfg()
        cfg["shots"] = cfg.get("shots", []) + [str(dst)]
        engine.save_cfg(cfg)
        return {"path": str(dst), "thumb": thumb_of(dst)}

    def pick_screenshots(self):
        import webview
        files = self.window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=True,
            file_types=("Зображення (*.png;*.jpg;*.jpeg;*.webp)", "Усі файли (*.*)"))
        out = []
        for f in files or []:
            try:
                out.append(self._store_shot(Path(f).read_bytes(), Path(f).name))
            except Exception:
                pass
        return out

    def add_dropped(self, name, data_url):
        try:
            data = base64.b64decode(data_url.split(",", 1)[1])
            return self._store_shot(data, name)
        except Exception:
            return None

    def set_shots(self, paths):
        cfg = engine.load_cfg()
        cfg["shots"] = list(paths)
        engine.save_cfg(cfg)
        return True

    # ---- ключ
    def check_key(self, key):
        try:
            import anthropic
            anthropic.Anthropic(api_key=key).models.list(limit=1)
        except Exception as e:
            return {"ok": False, "msg": friendly_error(e)}
        cfg = engine.load_cfg()
        cfg["api_key"] = key
        engine.save_cfg(cfg)
        return {"ok": True}

    # ---- перетягування кліпів
    VIDEO_EXT = {".mov", ".mp4", ".m4v", ".mxf", ".avi", ".mkv", ".mts", ".m2ts", ".webm", ".3gp"}

    def on_drop(self, e):
        """Подія drop від pywebview: тут є повні шляхи файлів (з DaVinci або Finder)."""
        try:
            files = (e.get("dataTransfer") or {}).get("files") or []
            try:
                target = self.window.evaluate_js("SV.takeDropTarget()") or "material"
            except Exception:
                target = "material"
            paths = []
            for f in files:
                p = f.get("pywebviewFullPath")
                if not p:
                    continue
                pp = Path(p)
                if target == "refs" and pp.suffix.lower() in self.VIDEO_EXT:
                    self._js("refAdded", self.add_ref_path(str(pp)))
                    continue
                if pp.suffix.lower() in music.AUDIO_EXT:
                    self._js("musicLoading", pp.name)
                    self._js("musicSet", self.set_music(str(pp)))
                    continue
                if pp.is_dir():
                    paths += [str(x) for x in sorted(pp.rglob("*"))
                              if x.suffix.lower() in self.VIDEO_EXT and not x.name.startswith(".")]
                elif pp.suffix.lower() in self.VIDEO_EXT:
                    paths.append(str(pp))
            if not paths:
                return
            self._js("droppedStart", len(paths))
            r = self.bridge.send("add_paths", {"paths": paths}, timeout=120)
            self._js("dropped", (r or {}).get("sources", []))
        except Exception as ex:
            self._js("droppedFail", friendly_error(ex))

    # ---- референси
    def _refs(self):
        return engine.load_cfg().get("refs", [])

    def _save_refs(self, lst):
        cfg = engine.load_cfg()
        cfg["refs"] = lst
        engine.save_cfg(cfg)

    def ref_card(self, r):
        out = dict(r)
        if r.get("path"):
            try:
                fr = engine.grab_frames(r["path"], [1.0], lambda f: None, lambda: None)
                if fr:
                    out["thumb"] = "data:image/jpeg;base64," + base64.b64encode(fr[0][1]).decode()
            except Exception:
                pass
        return out

    def list_refs(self):
        return [self.ref_card(r) for r in self._refs()]

    def add_ref_link(self, text):
        import refs as _r
        urls = _r.URL_RE.findall(text or "")
        if not urls:
            return {"error": "Встав посилання на TikTok, Reels, Shorts або YouTube."}
        lst, added = self._refs(), []
        for u in urls:
            u = u.rstrip(").,;»\"'")
            if any(x.get("url") == u for x in lst):
                continue
            item = {"url": u, "label": _r.platform(u)}
            lst.append(item)
            added.append(item)
        self._save_refs(lst)
        return {"added": added}

    def add_ref_path(self, path):
        lst = self._refs()
        if not any(x.get("path") == path for x in lst):
            item = {"path": path, "label": Path(path).name}
            lst.append(item)
            self._save_refs(lst)
            return self.ref_card(item)
        return None

    def pick_ref_videos(self):
        import webview
        files = self.window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=True,
                                               file_types=("Відео (*.mp4;*.mov;*.m4v;*.webm;*.mkv)", "Усі файли (*.*)"))
        return [c for c in (self.add_ref_path(f) for f in (files or [])) if c]

    def remove_ref(self, i):
        lst = self._refs()
        if 0 <= int(i) < len(lst):
            lst.pop(int(i))
            self._save_refs(lst)
        return True

    # ---- музика
    def pick_music(self):
        import webview
        files = self.window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=False,
            file_types=("Аудіо (" + ";".join("*" + e for e in sorted(music.AUDIO_EXT)) + ")", "Усі файли (*.*)"))
        if not files:
            return None
        self._js("musicLoading", Path(files[0]).name)
        return self.set_music(files[0])

    def set_music(self, path):
        try:
            ov = music.overview(path)
        except Exception as e:
            return {"error": friendly_error(e)}
        return {"path": str(path), "name": Path(path).name, "duration": ov["duration"], "peaks": ov["peaks"]}

    def music_preview(self, path, start, end):
        try:
            return music.preview_wav(path, float(start), float(end))
        except Exception:
            return None

    def estimate_edit(self, span, full):
        if not self.last:
            return {"cost": 0}
        return engine.estimate_edit(self.last[0], float(span or 0), bool(full))

    def clear_dropped(self):
        try:
            self.bridge.send("clear_dropped", timeout=20)
        except Exception:
            pass
        return True

    def set_on_top(self, on):
        try:
            self.window.on_top = bool(on)
        except Exception:
            pass
        cfg = engine.load_cfg()
        cfg["on_top"] = bool(on)
        engine.save_cfg(cfg)
        return bool(on)

    # ---- різне
    def open_url(self, which):
        url = URLS.get(which, which)
        if isinstance(url, str) and url.startswith("https://"):
            webbrowser.open(url)

    def open_path(self, p):
        """Відкриває лише папки/файли самої програми і готові ролики — не довільні шляхи."""
        import subprocess
        if not p:
            return
        try:
            target = Path(p).expanduser().resolve()
            allowed = [HOME.resolve(), (Path.home() / "Movies" / "Svit Editor").resolve()]
            if not any(target == a or a in target.parents for a in allowed):
                svlog.log(f"open_path: відмовлено {target}")
                return
            if target.is_file() and target.suffix.lower() in (".app", ".command", ".sh", ".py", ".pkg", ".tool"):
                target = target.parent          # виконувані файли не запускаємо — показуємо папку
            subprocess.run(["open", str(target)])
        except Exception as e:
            svlog.log(f"open_path: {e!r}")

    # ---- оновлення
    def check_update(self):
        import urllib.request
        repo = engine.load_cfg().get("update_repo") or UPDATE_REPO
        try:
            req = urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/latest",
                                         headers={"User-Agent": "SvitEditor", "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=10) as r:
                rel = json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if getattr(e, "code", None) == 404:
                return {"available": False, "current": VERSION}
            return {"available": False, "error": "Не вдалося перевірити оновлення. Перевір інтернет."}
        latest = str(rel.get("tag_name", "")).lstrip("vV")
        asset = next((a for a in rel.get("assets", []) if a.get("name", "").endswith(".zip")), None)
        if not latest or not asset:
            return {"available": False, "current": VERSION}
        url = asset.get("browser_download_url", "")
        if not url.startswith(f"https://github.com/{repo}/releases/download/"):
            svlog.log(f"Оновлення: підозріле посилання на файл, ігнорую: {url}")
            return {"available": False, "current": VERSION}
        self._upd_offer = {"url": url, "version": latest}
        return {"available": vtuple(latest) > vtuple(VERSION), "version": latest, "current": VERSION,
                "notes": (rel.get("body") or "").strip()[:1500], "url": asset["browser_download_url"],
                "size": asset.get("size", 0)}

    def install_update(self, url=None, version=None):
        """Встановлюємо лише те, що сама програма щойно знайшла на GitHub (посилання від сторінки ігнорується)."""
        offer = getattr(self, "_upd_offer", None)
        if not offer:
            return False
        threading.Thread(target=self._update, args=(offer["url"], offer["version"]), daemon=True).start()
        return True

    def _update(self, url, version):
        import subprocess
        import urllib.request
        import zipfile
        try:
            upd = HOME / "updates"
            if upd.exists():
                import shutil
                shutil.rmtree(upd, ignore_errors=True)
            upd.mkdir(parents=True)
            zpath = upd / "update.zip"
            req = urllib.request.Request(url, headers={"User-Agent": "SvitEditor"})
            with urllib.request.urlopen(req, timeout=30) as r, open(zpath, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                got = 0
                while True:
                    chunk = r.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    if total:
                        self._js("updProgress", 0.6 * got / total,
                                 f"Завантажую оновлення · {got // 1048576} з {max(1, total // 1048576)} МБ")
            self._js("updProgress", 0.62, "Розпаковую")
            with zipfile.ZipFile(zpath) as z:
                z.extractall(upd)
            res = next(upd.glob("*.app/Contents/Resources"), None)
            if not res or not (res / "worker.sh").exists():
                raise RuntimeError("Файл оновлення пошкоджений.")
            # цифровий підпис автора: без нього нічого не запускаємо
            self._js("updProgress", 0.63, "Перевіряю підпис")
            import sigcheck
            ok, why = sigcheck.check_app(res.parent.parent, version)
            svlog.log(f"Підпис оновлення {version}: {'OK' if ok else why}")
            if not ok:
                raise RuntimeError(f"Оновлення відхилено з міркувань безпеки: {why}. "
                                   f"Завантаж інсталятор вручну зі сторінки релізів на GitHub.")
            pf = upd / "progress.txt"
            proc = subprocess.Popen(["/bin/bash", str(res / "worker.sh"), "install", str(res), str(pf)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            seen, result = 0, None
            while True:
                lines = pf.read_text(encoding="utf-8").splitlines() if pf.exists() else []
                for ln in lines[seen:]:
                    f = ln.split("|")
                    if f[0] == "P":
                        self._js("updProgress", 0.62 + 0.38 * int(f[1]) / 100, "|".join(f[3:]))
                    elif f[0] in ("D", "E"):
                        result = f
                seen = len(lines)
                if proc.poll() is not None and result is None:
                    time.sleep(0.3)
                    if seen == len(pf.read_text(encoding="utf-8").splitlines()):
                        break
                if result:
                    break
                time.sleep(0.3)
            if not result or result[0] == "E":
                raise RuntimeError(result[2] if result and len(result) > 2 else "Оновлення не встановилось.")
            self._js("updDone", version)
        except Exception as e:
            self._js("updFail", friendly_error(e))

    def restart(self):
        self.restart_requested = True
        hard_exit(1.5, RESTART_CODE)
        try:
            self.window.destroy()
        except Exception:
            pass

    def quit(self):
        """Кнопка «Закрити»: повідомляємо DaVinci і гарантовано завершуємо процес
        (destroy() з потоку сторінки на macOS іноді підвисає, а фонові потоки тримають процес)."""
        svlog.log("Закриття вікна (кнопка)")
        self.cancel_event.set()
        try:
            self.bridge.send("quit", timeout=0)
        except Exception:
            pass
        hard_exit(0.6)
        try:
            self.window.destroy()
        except Exception:
            pass

    # ---- монтаж
    def start(self, st):
        if self.worker and self.worker.is_alive():
            return {"ok": False}
        self.cancel_event.clear()
        self.worker = threading.Thread(target=self._run, args=(dict(st),), daemon=True)
        self.worker.start()
        return {"ok": True}

    def cancel(self):
        self.cancel_event.set()

    def _js(self, fn, *args):
        try:
            self.window.evaluate_js(f"SV.{fn}(" + ",".join(json.dumps(a, ensure_ascii=False) for a in args) + ")")
        except Exception:
            pass

    def _progress(self, stage, pct, msg, extra):
        now = time.time()
        if now - self._last_push < 0.15 and stage == getattr(self, "_last_stage", None):
            return
        self._last_push, self._last_stage = now, stage
        self._js("progress", stage, pct, msg, extra or {})

    def _build(self, result, report):
        out, sources, st, stamp = self.last
        report("build", 0.05, "Збираю таймлайн у DaVinci")

        def on_status(s):
            report("build", s.get("pct", 0.5), s.get("msg", "Збираю таймлайн у DaVinci"))
        resp = self.bridge.send("build", {"plan": result, "sources": sources, "format": st.get("format", "9:16"),
                                          "layout": st.get("layout", "one"),
                                          "auto_render": bool(st.get("auto_render")),
                                          "fps": st.get("fps", "src"), "stamp": stamp,
                                          "gap": engine.VIDEO_GAP,
                                          "fx_strength": float(st.get("fx_strength", 50)) / 100.0,
                                          "look_strength": float(st.get("look_strength", 60)) / 100.0,
                                          "tr_speed": float(st.get("tr_speed", 60)) / 100.0,
                                          "tone_strength": (float(st.get("auto_tone_strength", 70)) / 100.0)
                                          if st.get("auto_tone", True) else 0,
                                          "overlay": {
                                              "blur": (float(st.get("ov_blur_strength", 30)) / 100.0) if st.get("ov_blur") else 0,
                                              "halation": (float(st.get("ov_hal_strength", 40)) / 100.0) if st.get("ov_hal") else 0},
                                          "ghost": float(st.get("style_ghost", 100)) / 100.0,
                                          "grain": (float(st["style_grain"]) / 100.0)
                                          if st.get("style_grain") is not None else None,
                                          "version": result.get("version", 1)},
                                timeout=900, on_status=on_status)
        if not resp or not resp.get("ok"):
            if resp and resp.get("details"):
                svlog.log("DaVinci повернув помилку:\n" + resp["details"])
            raise RuntimeError((resp or {}).get("error", "DaVinci не зміг зібрати таймлайн."))
        result["folder"] = resp.get("folder", "")
        result["timelines"] = resp.get("timelines") or []
        self._last_build = {"plan": result, "layout": st.get("layout", "one"), "timelines": result["timelines"],
                            "orig_looks": [v.get("look") for v in result.get("videos", [])]}
        result["style"] = self._style_from_settings(st, result)
        fu = resp.get("fusion") or {}
        n_fx = sum(1 for v in result.get("videos", []) for sg in v.get("segments", [])
                   if sg.get("fx") or sg.get("tr") or sg.get("zoom_end") or v.get("look"))
        result["fusion_line"] = (f"У DaVinci: шматків {fu.get('total', '?')}, з Fusion {fu.get('comps', fu.get('ok', 0))} "
                                 f"(за планом мало бути {n_fx}).")
        svlog.log(f"Збірка в DaVinci: Fusion успішно {fu.get('ok', 0)}, з помилками {fu.get('fail', 0)} "
                  f"{fu.get('errors') or ''}")
        if fu.get("fail"):
            note = (f"Увага: на {fu['fail']} шматках зуми/ефекти Fusion не вдалося зробити повністю "
                    f"(«{(fu.get('errors') or ['?'])[0][:90]}»). Натисни «Журнал» і надішли його Claude.")
            result["notes"] = (note + " " + (result.get("notes") or "")).strip()
            result["has_issue"] = True

    # ---- «Вигляд» після монтажу: повзунки ефектів без нового монтажу
    @staticmethod
    def _style_from_settings(st, result):
        looks = sorted({v.get("look") for v in result.get("videos", []) if v.get("look")})
        look = int(st.get("look_strength", 60))
        grain = st.get("style_grain")
        if grain is None:            # як задумано фактурою — показуємо, скільки зерна вийшло
            m = 0.4 + 0.9 * look / 100.0
            grain = round(100 * min(1.0, 0.35 + 0.5 * m)) if any(engine.LOOKS.get(l, {}).get("grain") or
                                                               l in ("vhs", "camcorder", "film8", "film16",
                                                                     "bwfilm", "lostwave") for l in looks) else 0
        return {"look": look, "fx": int(st.get("fx_strength", 50)),
                "speed": int(st.get("tr_speed", 60)),
                "tone": int(st.get("auto_tone_strength", 70)) if st.get("auto_tone", True) else 0,
                "halation": int(st.get("ov_hal_strength", 40)) if st.get("ov_hal") else 0,
                "dreamy": int(st.get("ov_blur_strength", 30)) if st.get("ov_blur") else 0,
                "ghost": int(st.get("style_ghost", 100)), "grain": int(grain),
                "grain_auto": st.get("style_grain") is None, "looks": looks, "look_type": ""}

    # Живе налаштування: кожна зміна повзунка ставиться в чергу; якщо DaVinci ще оновлює попередню —
    # її перериваємо (style_gen) і одразу беремо найсвіжішу. «Перебудова» не губиться, поки не завершиться.
    def restyle(self, p):
        p = dict(p or {})
        if self.worker and self.worker.is_alive():
            return {"ok": False}
        if not p.get("manual") and not getattr(self, "_last_build", None):
            return {"ok": False}
        with self._style_lock:
            self._style_gen += 1
            p["gen"] = "%d_%d" % (os.getpid(), self._style_gen)
            if p.get("mode") != "tune":
                self._style_need[bool(p.get("manual"))] = p.get("mode") or "rebuild"
            self._style_pending = p
            try:
                if self.bridge.dir:
                    (self.bridge.dir / "style_gen").write_text(p["gen"])
            except Exception:
                pass
            if not (self._style_thread and self._style_thread.is_alive()):
                self._style_thread = threading.Thread(target=self._style_loop, daemon=True)
                self._style_thread.start()
        return {"ok": True}

    def _style_loop(self):
        while True:
            with self._style_lock:
                p = self._style_pending
                self._style_pending = None
                if p is None:
                    return
                need = self._style_need.get(bool(p.get("manual")))
                if need:
                    p["mode"] = need
            resp = self._restyle(p)
            if resp and not resp.get("aborted"):
                with self._style_lock:
                    if self._style_need.get(bool(p.get("manual"))) == p["mode"]:
                        self._style_need.pop(bool(p.get("manual")), None)
                with self._style_lock:
                    last = self._style_pending is None
                if last:
                    self._js("restyleDone", resp)

    def _restyle(self, p):
        try:
            g = lambda k, d: max(0.0, float(p.get(k, d) if p.get(k) is not None else d)) / 100.0
            data = {"look_strength": max(0.1, g("look", 60)), "fx_strength": g("fx", 50),
                    "tr_speed": g("speed", 60), "tone_strength": g("tone", 0 if p.get("manual") else 70),
                    "overlay": {"blur": g("dreamy", 0), "halation": g("halation", 0)},
                    "ghost": g("ghost", 100), "grain": None if p.get("grain_auto") else g("grain", 0),
                    "mode": p.get("mode", "rebuild"), "gen": p.get("gen", "")}
            lt = p.get("look_type", "")
            if p.get("manual"):
                data["manual"] = True
                data["look_override"] = lt if lt in engine.LOOKS and float(p.get("look", 60)) > 0 else ""
            else:
                lb = self._last_build
                data.update({"plan": lb["plan"], "layout": lb["layout"], "timelines": lb["timelines"]})
                if lt == "none" or float(p.get("look", 60)) <= 0:
                    data["look_override"] = ""
                elif lt in engine.LOOKS:
                    data["look_override"] = lt
                else:                       # «як у монтажі» — повертаємо фактури, які обрав Claude
                    for v, ol in zip(lb["plan"].get("videos", []), lb.get("orig_looks", [])):
                        v["look"] = ol
            svlog.log("Вигляд: " + json.dumps({k: v for k, v in data.items() if k != "plan"}, ensure_ascii=False))

            def on_status(s):
                self._js("restyleProgress", s.get("pct", 0.5), s.get("msg", ""))
            resp = self.bridge.send("restyle", data, timeout=900, on_status=on_status)
            if not resp or not resp.get("ok"):
                raise RuntimeError((resp or {}).get("error", "DaVinci не зміг оновити вигляд."))
            resp["manual"] = bool(p.get("manual"))
            if resp.get("aborted"):
                return resp
            # наступні правки словами збиратимуться вже з цим виглядом
            if self.last and not p.get("manual"):
                st = self.last[2]
                st.update({"look_strength": p.get("look"), "fx_strength": p.get("fx"), "tr_speed": p.get("speed"),
                           "auto_tone": float(p.get("tone", 0)) > 0, "auto_tone_strength": p.get("tone") or 70,
                           "ov_hal": float(p.get("halation", 0)) > 0, "ov_hal_strength": p.get("halation") or 40,
                           "ov_blur": float(p.get("dreamy", 0)) > 0, "ov_blur_strength": p.get("dreamy") or 30,
                           "style_ghost": p.get("ghost"),
                           "style_grain": None if p.get("grain_auto") else p.get("grain")})
            return resp
        except Exception as e:
            svlog.log("Вигляд: помилка " + traceback.format_exc())
            with self._style_lock:
                self._style_pending = None
                self._style_need.pop(bool(p.get("manual")), None)
            self._js("restyleFail", friendly_error(e))
            return None

    def timeline_info(self):
        try:
            return self.bridge.send("timeline_info", {}, timeout=15)
        except Exception as e:
            return {"ok": False, "error": friendly_error(e)}

    def revise(self, text, rng=None):
        if not self.last or (self.worker and self.worker.is_alive()):
            return {"ok": False}
        self.cancel_event.clear()
        self.worker = threading.Thread(target=self._revise, args=(text, rng), daemon=True)
        self.worker.start()
        return {"ok": True}

    def _revise(self, text, rng=None):
        try:
            out = self.last[0]

            def report(stage, frac, msg, **extra):
                base = {"plan": 0.0, "build": 0.85}.get(stage, 0)
                span = {"plan": 0.85, "build": 0.15}.get(stage, 0.1)
                self._progress(stage, min(0.99, base + span * frac), msg, extra)
            result = engine.revise(out, text, lambda st, f, m, ex: report(st, f, m, **(ex or {})),
                                   self.cancel_event, rng)
            self._build(result, report)
            self._js("done", result)
        except engine.Cancelled:
            self._js("fail", "cancelled", "")
        except Exception as e:
            self._fail(e, "Правка монтажу", {"правка": text, "ділянка": rng})

    def _fail(self, e, what, extra=None):
        details = traceback.format_exc()
        svlog.log(f"ПОМИЛКА ({what}):\n{details}")
        ctx = {"дія": what}
        ctx.update(extra or {})
        rp = svlog.report(f"{what}: {friendly_error(e)}", str(e), details, ctx)
        self.last_report = str(rp) if rp else None
        self._js("fail", friendly_error(e), details)

    def open_log(self):
        """Кнопка «Журнал»: свіжий звіт з усіма журналами у TextEdit."""
        rp = svlog.report("Журнал на прохання користувача", "", "", None)
        return str(rp) if rp else None

    def open_logs_folder(self):
        svlog.open_folder()

    def _run(self, st):
        try:
            svlog.log("Старт монтажу: " + json.dumps({k: v for k, v in st.items() if k != "prompt"},
                                                      ensure_ascii=False)[:2000])
            svlog.log("Запит: " + str(st.get("prompt", ""))[:1000])
            if self.bridge.stale():
                raise RuntimeError("Частина Svit Editor усередині DaVinci ще стара (була запущена до оновлення), "
                                   "тому зуми, ефекти й переходи не спрацюють. Закрий це вікно і запусти Svit Editor "
                                   "знову: Workspace → Scripts → Svit Editor.")
            mode = st.get("source_mode", "selected")
            r = self.bridge.send("refresh", {"mode": mode}, timeout=20)
            items = (r or {}).get("sources", [])
            if not items:
                raise RuntimeError("Не знайшов відео. Виділи кліпи в Media Pool і натисни «Оновити».")
            sources = []
            for i, it in enumerate(items, 1):
                sources.append({"id": i, "uid": it["uid"], "name": it["name"], "path": it["path"],
                                "duration": float(it["duration"]), "fps": it.get("fps", 25),
                                "resolution": it.get("resolution", "")})
            cfg = engine.load_cfg()
            stamp = time.strftime("%Y%m%d_%H%M%S")
            out = HOME / "jobs" / stamp
            fmt = st.get("format", "9:16")
            layout = st.get("layout", "one")
            job = {
                "prompt": st.get("prompt", ""),
                "screenshots": [p for p in cfg.get("shots", []) if Path(p).exists()],
                "refs": [r for r in cfg.get("refs", []) if r.get("url") or Path(r.get("path", "")).exists()],
                "sources": sources,
                "settings": {
                    "num_videos": st.get("num") or "скільки вважаєш за потрібне за запитом",
                    "video_length": LENGTHS[int(st.get("len") or 0)],
                    "format_label": FORMAT_LABELS.get(fmt, fmt),
                    "layout": layout, "layout_label": LAYOUT_LABELS[layout],
                    "subtitles": bool(st.get("subtitles")), "transcribe": bool(st.get("transcribe")),
                    "frames": bool(st.get("frames")), "language": st.get("language") or None,
                    "whisper_model": st.get("whisper_model", "medium"),
                    "model": st.get("model", "claude-sonnet-5-5"),
                    "pace": st.get("pace", "normal"),
                    "zoom_crop": bool(st.get("zoom_crop", True)),
                    "zoom_dynamic": bool(st.get("zoom_dynamic", True)),
                    "zoom_strength": st.get("zoom_strength", 35),
                    "fx_on": bool(st.get("fx_on", True)),
                    "fx_allowed": [f for f in (st.get("fx_allowed") or []) if f in engine.FX_INFO],
                    "tr_on": bool(st.get("tr_on", True)),
                    "tr_allowed": [f for f in (st.get("tr_allowed") or []) if f in engine.TRANS_INFO],
                    "abstract": int(st.get("abstract", 25)),
                    "cinematic": bool(st.get("cinematic", False)),
                    "cinematic_level": int(st.get("cinematic_level", 60)),
                    "take_sync": bool(st.get("take_sync", True)),
                    "ui_lang": "en" if st.get("ui_lang") == "en" else "uk",
                    "auto_tone": bool(st.get("auto_tone", True)),
                    "look": st.get("look") if (st.get("look") in engine.LOOKS or st.get("look") == "auto") else "none",
                },
            }
            mu = st.get("music") or {}
            if st.get("music_on") and mu.get("path") and Path(mu["path"]).exists():
                job["music"] = {"path": mu["path"], "start": float(mu.get("start", 0)),
                                "end": float(mu.get("end", 30))}
                job["settings"]["video_length"] = f"рівно довжина фрагмента пісні ({float(mu.get('end', 30)) - float(mu.get('start', 0)):.0f} с)"
            out.mkdir(parents=True, exist_ok=True)
            (out / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")

            j = engine.Job(job, out, self._progress, self.cancel_event)
            result = j.run()
            self.last = (out, sources, st, stamp)
            self._build(result, j.report)
            self._js("done", result)
        except engine.Cancelled:
            self._js("fail", "cancelled", "")
        except Exception as e:
            safe = {k: v for k, v in st.items() if k not in ("api_key",)}
            self._fail(e, "Монтаж", {"налаштування": json.dumps(safe, ensure_ascii=False)[:3000]})


# ======================================================================= запуск

def hard_exit(delay=0.6, code=0):
    """Завершити процес через delay секунд, навіть якщо щось тримає його."""
    import os
    t = threading.Timer(delay, lambda: os._exit(code))
    t.daemon = True
    t.start()


def bind_drop(window, api):
    try:
        from webview.dom import DOMEventHandler
        window.dom.document.events.dragover += DOMEventHandler(lambda e: None, True, False)
        window.dom.document.events.drop += DOMEventHandler(api.on_drop, True, False)
    except Exception as e:
        print("Перетягування недоступне:", e)


def macos_polish(window, api=None):
    """Назва й іконка в Dock, темне оформлення, вікно поверх DaVinci."""
    if api is not None:
        bind_drop(window, api)
    try:
        from AppKit import NSApplication, NSImage, NSAppearance
        from PyObjCTools import AppHelper

        def apply():
            app = NSApplication.sharedApplication()
            icon = HERE / "web" / "icon.png"
            if icon.exists():
                app.setApplicationIconImage_(NSImage.alloc().initWithContentsOfFile_(str(icon)))
            app.setAppearance_(NSAppearance.appearanceNamed_("NSAppearanceNameDarkAqua"))
            app.activateIgnoringOtherApps_(True)
        AppHelper.callAfter(apply)
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", default=None)
    args = ap.parse_args()

    try:
        from Foundation import NSBundle
        info = NSBundle.mainBundle().localizedInfoDictionary() or NSBundle.mainBundle().infoDictionary()
        info["CFBundleName"] = "Svit Editor"
    except Exception:
        pass

    import webview
    api = Api(Bridge(args.session))
    win = webview.create_window("Svit Editor", url=str(HERE / "web" / "index.html"), js_api=api,
                                width=780, height=920, min_size=(640, 640),
                                background_color="#111114", text_select=True,
                                on_top=bool(engine.load_cfg().get("on_top", True)))
    api.window = win

    def on_closed():
        if api.restart_requested:
            return
        svlog.log("Вікно закрито")
        try:
            api.cancel_event.set()
            api.bridge.send("quit", timeout=0)
        except Exception:
            pass
        hard_exit(1.0)
    win.events.closed += on_closed
    webview.start(macos_polish, (win, api), private_mode=False)
    if api.restart_requested:
        sys.exit(RESTART_CODE)
    import os
    os._exit(0)


if __name__ == "__main__":
    main()
