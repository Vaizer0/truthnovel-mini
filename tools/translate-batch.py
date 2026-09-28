#!/usr/bin/env python3
"""Translate chapters with an OpenAI-compatible Gemini backend and cache the
result as i18n/<chapter-id>.json, which the hosted page loads same-origin.

This is what makes translation work online with nothing running locally: the
GitHub Actions workflow `translate.yml` runs this script, and the page then
serves the cached translation straight from GitHub Pages.

    python3 tools/translate-batch.py --count 20            # newest 20 missing
    python3 tools/translate-batch.py --count 20 --start 500
    python3 tools/translate-batch.py --only 2465           # one chapter, by number
    python3 tools/translate-batch.py --count 5 --dry-run

Requires GEMINI_API_BASE (default http://127.0.0.1:8083/v1) and optionally
GEMINI_API_KEY. Refusals are recorded, not retried forever: if Gemini declines
the text, the chapter is reported as refused and no file is written, so a run
cannot silently fill the repo with junk.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I18N = os.path.join(ROOT, "i18n")
JINA = "https://r.jina.ai/"

# Same refusal shapes the page detects, kept in sync with REFUSE in index.html.
REFUSE = re.compile(
    r"(can(?:no|')?t (?:help|assist|comply|provide|translate)"
    r"|i'?m just a language model|as a language model"
    r"|unable to (?:help|assist|translate|comply|provide)"
    r"|i cannot (?:help|assist|translate|provide)"
    r"|not able to (?:help|translate|provide)"
    r"|something went wrong|cannot fulfill|please try your request again"
    r"|hard time fulfilling)",
    re.I,
)
AR = re.compile(r"[\u0600-\u06ff]")
LATIN = re.compile(r"[A-Za-z]")

PROMPT = (
    "You are a professional literary translator working on an Arabic novel. "
    "Translate the user's Arabic passage into fluent, natural, literary English. "
    "Keep the meaning faithful and preserve paragraph breaks exactly: output only "
    "the translated paragraphs, in order, separated by one blank line. "
    "No preamble, no notes, no markdown, no commentary, no translator name."
)


def http(url, data=None, headers=None, timeout=120):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def get_text(url):
    """Chapter text: direct fetch first, then the r.jina.ai text mirror.

    GitHub runner IPs are sometimes served an empty 200 by the origin, so the
    fallback is not optional.
    """
    for attempt, candidate in enumerate((url, JINA + url)):
        try:
            raw = http(candidate, headers={"User-Agent": "Mozilla/5.0"}, timeout=90)
        except Exception as e:
            print("      fetch %s failed: %s" % ("direct" if attempt == 0 else "jina", e))
            continue
        if len(raw) < 5000:
            continue
        if attempt == 1:
            # jina returns markdown when it cannot pass HTML through
            return clean_markdown(raw)
        return extract_articles(raw)
    raise RuntimeError("could not fetch chapter (direct + jina both failed)")


def extract_articles(html):
    """Pick the chapter body: the best <article>, else the densest container.

    Scanning every div first would happily return the comments block, which on
    this site holds more <p> tags than the chapter itself.
    """
    for tags in (r"article", r"main|div"):
        best, best_score = "", 0
        for m in re.finditer(r"<(%s)([^>]*)>(.*?)</\1>" % tags, html, re.S | re.I):
            ps = re.findall(r"<p[^>]*>(.*?)</p>", m.group(3), re.S | re.I)
            if len(ps) < 3:
                continue
            score = len(ps) * 1000
            if score > best_score:
                best, best_score = m.group(3), score
        if best:
            return strip_html(best)
    raise RuntimeError("no article container found")


def clean_markdown(md):
    lines = [re.sub(r"^#+\s*", "", l) for l in md.splitlines()]
    return "\n\n".join(p for p in ("\n".join(lines)).split("\n\n") if p.strip()).strip()


def strip_html(frag):
    frag = re.sub(r"<(script|style|ins|iframe|noscript)\b.*?</\1>", " ", frag, flags=re.S | re.I)
    ps = re.findall(r"<p[^>]*>(.*?)</p>", frag, re.S | re.I)
    out, seen = [], set()
    for p in ps:
        t = html_unescape(re.sub(r"<[^>]+>", " ", p))
        t = re.sub(r"\s+", " ", t.replace("\u00a0", " ")).strip()
        if not t or t in seen:
            continue
        if len(t) < 2 and not AR.search(t):
            continue
        seen.add(t)
        out.append(t)
    if not out:
        raise RuntimeError("article had no readable paragraphs")
    return "\n\n".join(out)


def html_unescape(s):
    import html as H

    return H.unescape(s)


def clean_out(s):
    """Strip fences / preambles so only paragraphs remain."""
    s = re.sub(r"^\s*```[a-z]*\s*|\s*```\s*$", "", s or "").strip()
    s = re.sub(
        r"^(sure[,!.]?\s*)?(here('s| is)[^:\n]{0,60}:|the translation is)[\s:]*",
        "",
        s,
        flags=re.I,
    )
    s = re.sub(r"^(?:translator'?s note|note)\s*:.*$", "", s, flags=re.I | re.M)
    s = re.sub(r"\n\s*(?:let me know|i hope this helps|hope this helps)[^\n]*$", "", s, flags=re.I)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def paragraphs(t):
    return [p for p in t.split("\n\n") if p.strip()]


def translate(base, key, model, text, target="English"):
    chunks, buf, size = [], "", 0
    for p in paragraphs(text):
        if buf and size + len(p) + 2 > 3500:
            chunks.append(buf)
            buf, size = "", 0
        buf += ("\n\n" if buf else "") + p
        size += len(p) + 2
    if buf:
        chunks.append(buf)

    out = []
    for i, chunk in enumerate(chunks):
        body = json.dumps(
            {
                "model": model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": PROMPT},
                    {"role": "user", "content": chunk},
                ],
            }
        ).encode()
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
        last = None
        for attempt in range(2):
            try:
                raw = http(base.rstrip("/") + "/chat/completions", body, headers, timeout=180)
                j = json.loads(raw)
            except Exception as e:
                last = "request failed: %s" % e
                time.sleep(2 + attempt * 3)
                continue
            got = clean_out((j.get("choices") or [{}])[0].get("message", {}).get("content"))
            if not got:
                last = "empty reply"
                continue
            if REFUSE.search(got):
                raise RuntimeError("model refused (content policy)")
            if AR.search(got) and not LATIN.search(got):
                last = "source echoed back"
                continue
            want = len(paragraphs(chunk))
            have = len(paragraphs(got))
            if want > 2 and not (want * 0.5 <= have <= want * 1.5):
                last = "paragraph mismatch (%d of %d)" % (have, want)
                continue
            return got
        raise RuntimeError(last or "translation failed")
    return "\n\n".join(out)


def selftest(base, key, model):
    """Prove the backend works before blaming the novel.

    Distinguishes the two failure modes that look identical from the outside:
    a bad/expired cookie (backend hangs or 401s on a trivial question) versus
    Gemini declining this book's text (backend fine, novel refused).
    """
    checks = [
        ("plain question", "What is the capital of France? Answer in one word.", None),
        (
            "generic translation",
            "Translate to English: The central bank raised interest rates by "
            "half a percentage point on Tuesday.",
            None,
        ),
    ]
    for label, text, sysmsg in checks:
        body = json.dumps(
            {
                "model": model,
                "stream": False,
                "messages": ([{"role": "system", "content": sysmsg}] if sysmsg else [])
                + [{"role": "user", "content": text}],
            }
        ).encode()
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
        t = time.time()
        try:
            raw = http(base.rstrip("/") + "/chat/completions", body, headers, timeout=90)
            out = clean_out((json.loads(raw).get("choices") or [{}])[0].get("message", {}).get("content"))
        except Exception as e:
            print("  %-20s FAIL after %.0fs: %s" % (label, time.time() - t, e))
            return False
        if not out:
            print("  %-20s FAIL: empty reply" % label)
            return False
        print("  %-20s OK (%.0fs): %s" % (label, time.time() - t, out[:70]))
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--start", type=int, default=0, help="0 = newest first")
    ap.add_argument("--only", type=str, default="", help="single chapter number")
    ap.add_argument("--model", default=os.environ.get("GEMINI_MODEL", "gemini-3.6-flash"))
    ap.add_argument("--base", default=os.environ.get("GEMINI_API_BASE", "http://127.0.0.1:8083/v1"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true", help="check the backend, translate nothing")
    a = ap.parse_args()

    catalog = json.load(open(os.path.join(ROOT, "chapters.json"), encoding="utf-8"))["chapters"]
    os.makedirs(I18N, exist_ok=True)

    if a.only:
        targets = [c for c in catalog if str(c["n"]) == a.only or c["id"] == a.only]
    else:
        pending = [c for c in catalog if not os.path.exists(os.path.join(I18N, c["id"] + ".json"))]
        targets = pending[a.start : a.start + a.count] if a.count > 0 else []

    if not targets:
        print("nothing to do (%d chapters already cached)" % (len(catalog) - len(pending) if not a.only else len(catalog)))
        return 0

    key = os.environ.get("GEMINI_API_KEY", "")
    if a.selftest:
        print("selftest against %s (model %s)" % (a.base, a.model))
        if not selftest(a.base, key, a.model):
            print("\nRESULT: backend unusable - the cookie is missing, expired, or rate limited.")
            return 2
        print("\nRESULT: backend healthy. If chapters still fail, Gemini is refusing this novel.")
        return 0
    print("backend %s  model %s  targets %d" % (a.base, a.model, len(targets)))
    if a.dry_run:
        for c in targets:
            print("  would translate n=%s %s" % (c["n"], c["id"][:44]))
        return 0

    ok = refused = failed = 0
    for i, c in enumerate(targets, 1):
        print("[%d/%d] n=%s %s" % (i, len(targets), c["n"], c["id"][:44]))
        try:
            text = get_text(c["url"])
        except Exception as e:
            print("   fetch failed: %s" % e)
            failed += 1
            continue
        print("   %d chars, %d paragraphs" % (len(text), len(paragraphs(text))))
        try:
            en = translate(a.base, key, a.model, text)
        except Exception as e:
            print("   TRANSLATE FAILED: %s" % e)
            if "refused" in str(e):
                refused += 1
            failed += 1
            continue
        with open(os.path.join(I18N, c["id"] + ".json"), "w", encoding="utf-8") as f:
            json.dump(
                {"n": c["n"], "title": c["title"], "text": en, "model": a.model},
                f,
                ensure_ascii=False,
            )
        print("   OK -> i18n/%s.json (%d chars)" % (c["id"], len(en)))
        ok += 1

    print("\ndone: %d translated, %d refused, %d failed" % (ok, refused, failed))
    return 0 if ok or refused == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
