#!/usr/bin/env python3
"""Make a render copy of an issue with hotlinked photos downloaded and downscaled.

Usage: prep_images.py issues/<stem>.html  ->  writes issues/<stem>.render.html + issues/<stem>-img/*.jpg
The committed HTML keeps its hotlinks; only the render copy points at local, resized files, so the
PDF stays a sensible size (Chrome otherwise embeds every photo at full resolution).
Resizing uses macOS `sips` when available, else Pillow if installed, else the original bytes.
Stdlib only.
"""
import os, re, sys, hashlib, shutil, subprocess, urllib.request

MAX_W = 1000          # px; tiles are ~260 CSS px wide, hero ~700, so 1000 is 2x for everything but the hero
QUALITY = "62"        # jpeg quality for sips


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


def rewrite_html(s, html_dir, imgdir, fetch_and_shrink):
    raw_by_decoded = {}
    for raw_src in re.findall(r'<img[^>]+src="(https?://[^"]+)"', s):
        decoded = raw_src.replace("&amp;", "&")
        raw_by_decoded.setdefault(decoded, []).append(raw_src)
    total_in = total_out = 0
    for decoded in sorted(raw_by_decoded):
        raw_variants = sorted(set(raw_by_decoded[decoded]))
        name = hashlib.sha1(decoded.encode()).hexdigest()[:12]
        raw = os.path.join(imgdir, name + ".orig")
        out = os.path.join(imgdir, name + ".jpg")
        try:
            fetch_and_shrink(decoded, raw, out)
            total_in += os.path.getsize(raw); total_out += os.path.getsize(out)
            os.remove(raw)
            rel = os.path.relpath(out, html_dir)
            for raw_variant in raw_variants:
                s = s.replace(f'src="{raw_variant}"', f'src="{rel}"')
        except Exception as e:
            for partial in (raw, out):
                try:
                    os.remove(partial)
                except OSError:
                    pass
            print(f"kept hotlink (fetch failed): {decoded[:80]} {e}", file=sys.stderr)
    return s, len(raw_by_decoded), total_in, total_out


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        sys.exit(2)
    html_path = sys.argv[1]
    stem = html_path[:-5] if html_path.endswith(".html") else html_path
    imgdir = stem + "-img"
    os.makedirs(imgdir, exist_ok=True)
    s = open(html_path, encoding="utf-8").read()

    def fetch_and_shrink(url, raw_path, out_path):
        fetch(url, raw_path)
        shrink(raw_path, out_path)

    new_html, n_urls, total_in, total_out = rewrite_html(
        s, os.path.dirname(html_path), imgdir, fetch_and_shrink)
    render = stem + ".render.html"
    open(render, "w", encoding="utf-8").write(new_html)
    print(f"{render} ({n_urls} images, {total_in//1024} KB -> {total_out//1024} KB)")


if __name__ == "__main__":
    main()
