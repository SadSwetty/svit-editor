#!/usr/bin/env python3
"""Збирає macOS-інсталятор Svit Film (.pkg) без Мака.

Результат — звичайний пакет для Installer.app: людина двічі клікає, натискає «Продовжити» →
«Встановити», вводить пароль, і плагін опиняється в /Library/OFX/Plugins.

Формат: product archive (xar) з Distribution і одним компонентом svitfilm.pkg
(PackageInfo + Bom + Payload(cpio.gz) + Scripts(cpio.gz)). Bom робить mkbom з bomutils.

  python3 mkpkg.py <SvitFilm.ofx.bundle> <версія> <вихід.pkg> [--mkbom шлях]
"""
import gzip
import hashlib
import os
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import time
import zlib
from xml.sax.saxutils import escape

IDENT = "com.sadsvit.svitfilm"
UID, GID = 0, 80  # root:admin, як у пакетах Apple

PREINSTALL = """#!/bin/bash
# прибрати попередню версію, щоб не лишилось старих файлів
mkdir -p "/Library/OFX/Plugins"
rm -rf "/Library/OFX/Plugins/SvitFilm.ofx.bundle"
exit 0
"""

POSTINSTALL = """#!/bin/bash
B="/Library/OFX/Plugins/SvitFilm.ofx.bundle"
chown -R root:wheel "$B" 2>/dev/null
chmod -R a+rX "$B" 2>/dev/null
xattr -dr com.apple.quarantine "$B" 2>/dev/null
# DaVinci кешує список OFX-плагінів; скидаємо кеш, щоб він перечитав Svit Film
U="$(stat -f%Su /dev/console 2>/dev/null)"
if [ -n "$U" ] && [ "$U" != "root" ]; then
  H="$(dscl . -read "/Users/$U" NFSHomeDirectory 2>/dev/null | awk '{print $2}')"
  [ -n "$H" ] && rm -f "$H/Library/Application Support/Blackmagic Design/DaVinci Resolve/OFXPluginCacheV2.xml"
fi
exit 0
"""


# ---------- cpio (odc), як у Payload пакетів Apple
def cpio_odc(root):
    out = bytearray()
    ino = 1

    def entry(name, mode, data=b"", mtime=0):
        nonlocal ino
        nb = name.encode("utf-8") + b"\0"
        hdr = "070707%06o%06o%06o%06o%06o%06o%06o%011o%06o%011o" % (
            0, ino, mode, UID, GID, 1, 0, mtime, len(nb), len(data))
        out.extend(hdr.encode("ascii") + nb + data)
        ino += 1

    entry(".", stat.S_IFDIR | 0o755)
    for dirpath, dirs, files in os.walk(root):
        dirs.sort(); files.sort()
        rel = os.path.relpath(dirpath, root)
        for d in dirs:
            p = os.path.join(dirpath, d)
            entry("./" + os.path.normpath(os.path.join(rel, d)), stat.S_IFDIR | 0o755, mtime=int(os.stat(p).st_mtime))
        for f in files:
            p = os.path.join(dirpath, f)
            st = os.stat(p)
            mode = 0o755 if st.st_mode & 0o111 else 0o644
            with open(p, "rb") as fh:
                entry("./" + os.path.normpath(os.path.join(rel, f)), stat.S_IFREG | mode, fh.read(), int(st.st_mtime))
    entry("TRAILER!!!", 0)
    return bytes(out)


def gz(data):
    return gzip.compress(data, compresslevel=9, mtime=0)


# ---------- xar
def xar(files, out_path):
    """files: список (ім'я в архіві, bytes) або (ім'я теки, список дітей)."""
    heap = bytearray(b"\0" * 20)  # місце під sha1 TOC
    ids = [0]

    def node(name, content):
        ids[0] += 1
        fid = ids[0]
        if isinstance(content, list):
            kids = "".join(node(n, c) for n, c in content)
            return ('<file id="%d"><name>%s</name><type>directory</type><mode>0755</mode>'
                    '<uid>0</uid><gid>0</gid><user>root</user><group>wheel</group>%s</file>'
                    % (fid, escape(name), kids))
        off = len(heap)
        heap.extend(content)
        h = hashlib.sha1(content).hexdigest()
        return ('<file id="%d"><name>%s</name><type>file</type><mode>0644</mode>'
                '<uid>0</uid><gid>0</gid><user>root</user><group>wheel</group>'
                '<data><offset>%d</offset><size>%d</size><length>%d</length>'
                '<encoding style="application/octet-stream"/>'
                '<archived-checksum style="sha1">%s</archived-checksum>'
                '<extracted-checksum style="sha1">%s</extracted-checksum></data></file>'
                % (fid, escape(name), off, len(content), len(content), h, h))

    body = "".join(node(n, c) for n, c in files)
    ctime = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    toc = ('<?xml version="1.0" encoding="UTF-8"?>\n<xar><toc><creation-time>%s</creation-time>'
           '<checksum style="sha1"><offset>0</offset><size>20</size></checksum>%s</toc></xar>'
           % (ctime, body)).encode("utf-8")
    ctoc = zlib.compress(toc, 9)
    heap[0:20] = hashlib.sha1(ctoc).digest()
    hdr = struct.pack(">4sHHQQI", b"xar!", 28, 1, len(ctoc), len(toc), 1)
    with open(out_path, "wb") as f:
        f.write(hdr + ctoc + bytes(heap))


def main():
    args = sys.argv[1:]
    mkbom = "mkbom"
    if "--mkbom" in args:
        i = args.index("--mkbom"); mkbom = args[i + 1]; del args[i:i + 2]
    bundle, version, out = args
    work = tempfile.mkdtemp()
    try:
        root = os.path.join(work, "root")
        os.makedirs(root)
        shutil.copytree(bundle, os.path.join(root, "SvitFilm.ofx.bundle"), symlinks=True)
        payload = gz(cpio_odc(root))
        subprocess.check_call([mkbom, "-u", str(UID), "-g", str(GID), root, os.path.join(work, "Bom")])
        bom = open(os.path.join(work, "Bom"), "rb").read()

        sdir = os.path.join(work, "scripts")
        os.makedirs(sdir)
        for name, text in (("preinstall", PREINSTALL), ("postinstall", POSTINSTALL)):
            p = os.path.join(sdir, name)
            open(p, "w").write(text)
            os.chmod(p, 0o755)
        scripts = gz(cpio_odc(sdir))

        nfiles = sum(len(f) + len(d) for _, d, f in os.walk(root)) + 1
        kbytes = (sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(root) for f in fs) + 1023) // 1024
        pkginfo = ('<?xml version="1.0" encoding="utf-8"?>\n'
                   '<pkg-info format-version="2" identifier="%s" version="%s" install-location="/Library/OFX/Plugins" '
                   'auth="root" overwrite-permissions="true" relocatable="false" postinstall-action="none">'
                   '<payload numberOfFiles="%d" installKBytes="%d"/>'
                   '<scripts><preinstall file="./preinstall"/><postinstall file="./postinstall"/></scripts>'
                   '</pkg-info>\n' % (IDENT, version, nfiles, kbytes)).encode()

        dist = ('<?xml version="1.0" encoding="utf-8"?>\n'
                '<installer-gui-script minSpecVersion="2">\n'
                '  <title>Svit Film %s</title>\n'
                '  <welcome file="welcome.html" mime-type="text/html"/>\n'
                '  <conclusion file="conclusion.html" mime-type="text/html"/>\n'
                '  <options customize="never" require-scripts="false" hostArchitectures="arm64,x86_64"/>\n'
                '  <domains enable_anywhere="false" enable_currentUserHome="false" enable_localSystem="true"/>\n'
                '  <volume-check><allowed-os-versions><os-version min="11.0"/></allowed-os-versions></volume-check>\n'
                '  <choices-outline><line choice="default"><line choice="%s"/></line></choices-outline>\n'
                '  <choice id="default"/>\n'
                '  <choice id="%s" visible="false"><pkg-ref id="%s"/></choice>\n'
                '  <pkg-ref id="%s" version="%s" onConclusion="none" installKBytes="%d">#svitfilm.pkg</pkg-ref>\n'
                '</installer-gui-script>\n' % (version, IDENT, IDENT, IDENT, IDENT, version, kbytes)).encode()

        style = ("<style>body{font-family:-apple-system,Helvetica;font-size:13px;line-height:1.5}"
                 "h2{font-size:17px;margin:0 0 8px}code{font-size:12px}</style>")
        welcome = ("<html><head><meta charset='utf-8'>%s</head><body><h2>Svit Film %s</h2>"
                   "<p>Плагін плівки для DaVinci Resolve: 8 плівок, halation, bloom, зерно, віньєтка, "
                   "дрижання кадру.</p><p>Перед встановленням закрий DaVinci Resolve.</p>"
                   "<p>Плагін ляже в <code>/Library/OFX/Plugins</code>.</p></body></html>" % (style, version))
        concl = ("<html><head><meta charset='utf-8'>%s</head><body><h2>Готово</h2>"
                 "<p>1. Відкрий DaVinci Resolve.</p>"
                 "<p>2. <b>Preferences → System → Video Plugins</b>: постав галочку біля <b>SvitFilm</b> "
                 "і перезапусти DaVinci.</p>"
                 "<p>3. <b>Effects → OpenFX → Svit → Svit Film</b>: перетягни на кліп або ноду.</p>"
                 "<p>Нові версії: кнопка <b>Update Svit Film</b> внизу налаштувань плагіна.</p>"
                 "</body></html>" % style)

        xar([
            ("Distribution", dist),
            ("Resources", [("uk.lproj", [("welcome.html", welcome.encode()), ("conclusion.html", concl.encode())]),
                           ("en.lproj", [("welcome.html", welcome.encode()), ("conclusion.html", concl.encode())])]),
            ("svitfilm.pkg", [("PackageInfo", pkginfo), ("Bom", bom), ("Payload", payload), ("Scripts", scripts)]),
        ], out)
        print("OK:", out, os.path.getsize(out), "bytes")
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
