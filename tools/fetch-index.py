#!/usr/bin/env python3
"""Generate chapters.json (the catalog) so the hosted page never needs a relay
to show the chapter list.

The source site is unreachable from most networks (it answers 200 with a
0-byte body) and sends no CORS headers, so a static page cannot fetch the
catalog live. But the catalog changes rarely, so we snapshot it into the repo
and the page loads it same-origin instead.

    python3 tools/fetch-index.py            # uses the local relay if running
    python3 tools/fetch-index.py <url>      # or pass the list page directly

The chapter *text* is far too large to snapshot for all ~2500 chapters
(~250 MB), so reading a chapter still needs a relay -- see worker/.
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "chapters.json")
LIST = "https://truthnovel.top/list/257/"
LOCAL = "http://127.0.0.1:8080/_p?url="


def fetch(url):
    """Prefer the local relay (it has the jina fallback + disk cache)."""
    try:
        with urllib.request.urlopen(LOCAL + urllib.parse.quote(url, safe=""), timeout=120) as r:
            body = r.read().decode("utf-8", "replace")
        if len(body) > 5000:
            return body
    except Exception as e:
        print("local relay unavailable (%s), trying direct" % e)
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def parse(html):
    links = re.findall(
        r'<a[^>]*class="[^"]*w4pl_post_title[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        html,
        re.S,
    )
    seen, out = set(), []
    for url, raw_title in links:
        url = urllib.parse.urljoin(LIST, url)
        if url in seen:
            continue
        seen.add(url)
        title = re.sub(r"<[^>]+>", " ", raw_title)
        title = re.sub(r"\s+", " ", title).strip()
        slug = url.rstrip("/").rsplit("/", 1)[-1]
        # Match the page's own numbering: it reads the number from the title
        # ("2078 - The Sultan"), which is authoritative. Some slugs carry an
        # unrelated internal id, so fall back to the slug only if needed.
        num = re.match(r"\s*(\d+(?:\.\d+)?)", title) or re.match(r"(\d+)", slug)
        out.append(
            {
                "id": slug,
                "url": url,
                "n": int(float(num.group(1))) if num else 0,
                "title": title or slug,
            }
        )
    out.sort(key=lambda c: -c["n"])
    return out


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else LIST
    html = fetch(src)
    items = parse(html)
    if len(items) < 10:
        sys.exit("refusing to write: only %d chapters parsed" % len(items))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"source": LIST, "count": len(items), "chapters": items}, f, ensure_ascii=False)
    print("wrote %s with %d chapters (%d bytes)" % (OUT, len(items), os.path.getsize(OUT)))


if __name__ == "__main__":
    main()
