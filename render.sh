#!/usr/bin/env bash
# Render an issue HTML to a 2-page A4 PDF.
# Usage: ./render.sh issues/2026-09-17-issue-002.html
# Tries, in order: system Chrome/Chromium, Playwright's Chromium, WeasyPrint.
# Prints the PDF path on success. Exit 1 if nothing worked.
set -u
IN="$1"
OUT="${IN%.html}.pdf"
ABS="$(cd "$(dirname "$IN")" && pwd)/$(basename "$IN")"

for BIN in google-chrome google-chrome-stable chromium chromium-browser \
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  "$HOME"/Library/Caches/ms-playwright/chromium-*/chrome-mac-arm64/"Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing" \
  "$HOME"/Library/Caches/ms-playwright/chromium-*/chrome-mac-arm64/Chromium.app/Contents/MacOS/Chromium; do
  if command -v "$BIN" >/dev/null 2>&1 || [ -x "$BIN" ]; then
    "$BIN" --headless=new --disable-gpu --no-sandbox --no-pdf-header-footer \
      --virtual-time-budget=10000 --print-to-pdf="$OUT" "file://$ABS" >/dev/null 2>&1
    if [ -s "$OUT" ]; then echo "$OUT"; exit 0; fi
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
