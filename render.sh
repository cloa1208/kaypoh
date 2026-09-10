#!/usr/bin/env bash
# Render an issue HTML to a 2-page A4 PDF.
# Usage: ./render.sh issues/2026-09-17-issue-002.html
# Tries, in order: system Chrome/Chromium, Playwright's Chromium, WeasyPrint.
# Prints the PDF path on success. Exit 1 if nothing worked.
set -u
IN="$1"
OUT="${IN%.html}.pdf"
# Downscale hotlinked photos into a render copy so the PDF stays small (see prep_images.py).
HERE="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$HERE/prep_images.py" ] && [ "${IN%.render.html}" = "$IN" ]; then
  if python3 "$HERE/prep_images.py" "$IN" >&2; then IN="${IN%.html}.render.html"; fi
fi
ABS="$(cd "$(dirname "$IN")" && pwd)/$(basename "$IN")"

for BIN in google-chrome google-chrome-stable chromium chromium-browser \
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  "$HOME"/Library/Caches/ms-playwright/chromium-*/chrome-mac-arm64/"Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing" \
  "$HOME"/Library/Caches/ms-playwright/chromium-*/chrome-mac-arm64/Chromium.app/Contents/MacOS/Chromium; do
  if command -v "$BIN" >/dev/null 2>&1 || [ -x "$BIN" ]; then
    "$BIN" --headless=new --disable-gpu --no-sandbox --no-pdf-header-footer \
      --virtual-time-budget=10000 --print-to-pdf="$OUT" "file://$ABS" >/dev/null 2>&1
    if [ -s "$OUT" ]; then
      # Fit report: the page script zooms overflowing content down so nothing prints over the
      # footer; anything under 1.00 means the editor should cut a line or an item on that page.
      "$BIN" --headless=new --disable-gpu --no-sandbox --virtual-time-budget=10000 --dump-dom "file://$ABS" 2>/dev/null \
        | grep -o 'class="page[^"]*"[^>]*data-fit="[0-9.]*"\( data-overflow="[0-9]*"\)\?' \
        | sed -E 's/class="page ([a-z]+)".*data-fit="([0-9.]+)"( data-overflow="([0-9]+)")?/\1 \2 \4/' \
        | while read -r PG FITZ OVF; do
            if [ "$FITZ" != "1.00" ]; then
              echo "FIT WARNING: page '$PG' content was scaled to $FITZ to clear the footer${OVF:+ (still ${OVF}px over)}. Cut a line or a list item on that page and re-render until it reports 1.00." >&2
            fi
          done
      echo "$OUT"; exit 0
    fi
  fi
done

if command -v npx >/dev/null 2>&1; then
  npx -y playwright install chromium >/dev/null 2>&1 || true
  node -e '
    const {chromium}=require("playwright");
    (async()=>{const b=await chromium.launch();const p=await b.newPage();
      await p.goto("file://"+process.argv[1],{waitUntil:"networkidle"});
      await p.pdf({path:process.argv[2],format:"A4",printBackground:true,preferCSSPageSize:true});
      await b.close();})().catch(e=>{console.error(e);process.exit(1)});
  ' "$ABS" "$OUT" 2>/dev/null
  if [ -s "$OUT" ]; then echo "$OUT"; exit 0; fi
fi

if python3 -c "import weasyprint" 2>/dev/null || pip install -q weasyprint >/dev/null 2>&1; then
  python3 -c "from weasyprint import HTML;HTML('$ABS').write_pdf('$OUT')" 2>/dev/null
  if [ -s "$OUT" ]; then echo "$OUT"; exit 0; fi
fi

echo "render failed" >&2
exit 1
