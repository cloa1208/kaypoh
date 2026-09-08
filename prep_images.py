#!/usr/bin/env python3
"""Make a render copy of an issue with hotlinked photos downloaded and downscaled.

Usage: prep_images.py issues/<stem>.html  ->  writes issues/<stem>.render.html + issues/<stem>-img/*.jpg
The committed HTML keeps its hotlinks; only the render copy points at local, resized files, so the
PDF stays a sensible size (Chrome otherwise embeds every photo at full resolution).
Resizing uses macOS `sips` when available, else Pillow if installed, else the original bytes.
Stdlib only.
"""
import os, re, sys, hashlib, shutil, subprocess, urllib.request

MAX_W = 1400          # px, plenty for an A4 page at print quality
QUALITY = "72"        # jpeg quality for sips


def fetch(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh) Kaypoh/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
        f.write(r.read())


def shrink(src, dst):
    if shutil.which("sips"):
        r = subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", QUALITY,
                            "-Z", str(MAX_W), src, "--out", dst], capture_output=True)
        if r.returncode == 0 and os.path.getsize(dst) > 0:
            return True
    try:
        from PIL import Image
        im = Image.open(src).convert("RGB")
        im.thumbnail((MAX_W, MAX_W * 3))
        im.save(dst, "JPEG", quality=int(QUALITY), optimize=True)
        return True
    except Exception:
        shutil.copy2(src, dst)
        return False


def main():
    html_path = sys.argv[1]
    stem = html_path[:-5] if html_path.endswith(".html") else html_path
    imgdir = stem + "-img"
    os.makedirs(imgdir, exist_ok=True)
    s = open(html_path, encoding="utf-8").read()
    urls = sorted(set(re.findall(r'<img[^>]+src="(https?://[^"]+)"', s)))
    total_in = total_out = 0
    for u in urls:
        clean = u.replace("&amp;", "&")
        name = hashlib.sha1(clean.encode()).hexdigest()[:12]
        raw = os.path.join(imgdir, name + ".orig")
        out = os.path.join(imgdir, name + ".jpg")
        try:
            fetch(clean, raw)
            shrink(raw, out)
            total_in += os.path.getsize(raw); total_out += os.path.getsize(out)
            os.remove(raw)
            rel = os.path.relpath(out, os.path.dirname(html_path))
            s = s.replace(f'src="{u}"', f'src="{rel}"')
        except Exception as e:
            print(f"kept hotlink (fetch failed): {clean[:80]} {e}", file=sys.stderr)
    render = stem + ".render.html"
    open(render, "w", encoding="utf-8").write(s)
    print(f"{render} ({len(urls)} images, {total_in//1024} KB -> {total_out//1024} KB)")


if __name__ == "__main__":
    main()
