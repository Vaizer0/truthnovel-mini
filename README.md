# Truth Novel — mini reader

A single-file reader for the Arabic web novel **Lord of Truth** (سيد الحقيقة), with
optional machine translation. No build step, no framework, no bundled novel text —
everything is fetched at runtime.

Live page: **https://vaizer0.github.io/truthnovel-mini/**

---

## How it works

The page is one static `index.html`. It cannot talk to `truthnovel.top` directly for
two independent reasons, and both had to be solved for it to work at all:

1. **The site returns an empty body** to many networks. You get `HTTP 200` with
   **0 bytes** — not an error, just nothing. A naive client treats that as success
   and renders an empty chapter list.
2. **The site sends no CORS headers**, so a browser cannot read the response even
   when the network allows it.

GitHub Pages is static and cannot proxy at request time, so a relay is required.
`index.html` tries routes in order and uses the first that returns real content:

| Order | Route | When it is used |
|---|---|---|
| 1 | `/_p?url=…` (same origin) | page opened from `localhost` — the local dev relay |
| 2 | direct `fetch` | network where the site is reachable and CORS-permissive |
| 3 | **configured relay** | normal case on a hosted page — your Cloudflare Worker |
| 4 | `api.allorigins.win` | legacy public proxy, currently offline, kept as a last resort |

Every route has a 25 s timeout and rejects bodies under 2000 bytes, so a blank
`200` is treated as a failure rather than an empty chapter.

## Setting up the relay (required for the hosted page)

The Worker is in [`worker/`](worker/). It fetches the upstream page, enforces CORS,
and falls back to `r.jina.ai` if the direct fetch is empty. It also blocks
private/loopback hosts so it cannot be used as an open proxy.

```bash
cd worker
npm install -g wrangler
wrangler deploy
```

Then put the printed `https://<name>.<you>.workers.dev` URL into **one** of:

- `relay.txt` in this repo (first line) and redeploy — applies to every visitor, or
- **Settings → Fetch relay URL** in the page — applies to your browser only

## Local development

```bash
python3 tools/local-relay.py 8080
# open http://127.0.0.1:8080/index.html
```

`tools/local-relay.py` serves this directory and implements `/_p?url=…`, caching
pages in `.relay-cache/`. Only needed offline; the hosted page uses the Worker.

To rebuild `index.html` from the original file after editing `build.py`:

```bash
python3 build.py     # every patch is asserted; it aborts rather than half-patching
```

## Translation

Translation is **not** included in this repo — there is no API key here, and the
original page never contained one. The page posts to any OpenAI-compatible
`/v1/chat/completions` endpoint that you configure in Settings. The default is
`http://127.0.0.1:8081/v1`, which works with
[gemini-web2api](https://github.com/HnDK0/gemini-web2api) running on the same device.

> **Important:** on a hosted page `127.0.0.1` means **the device you are viewing it
> on**, not a server. To translate from a public URL, either run gemini-web2api
> locally on that device, or paste another OpenAI-compatible base URL in Settings.

Reliability changes in this version, all covered by `tools/test-sanitizer.js`:

- the full style/terminology prompt is sent in the **`system` role** instead of being
  glued onto the user turn, where models treat it as content to translate
- output is sanitized: code fences, `**bold**`, `Here is the translation:`
  preambles, and trailing *translator's note* / *hope this helps* blocks are removed
- output is **validated** — paragraph count is compared against the source, and a
  reply that is still in Arabic is treated as a failure
- each chunk is retried once with an explicit repair instruction
- every request has a hard 90 s timeout via `AbortController`; chunks are 3500 chars
  instead of 6000 to reduce drift

**Known limitation.** Gemini's web backend refuses to translate this novel's text
(it returns *"I'm just a language model and I can't help you with that."* for a
single paragraph). The page now detects that and reports it as an explicit
`The model refused to translate this text (content policy)` error instead of
silently rendering the refusal as if it were a translation. That detection is
deliberate; no attempt is made to work around the model's content policy. Use an
endpoint you have the right to send this text to.

## Chapter reader fixes

- `read()` picked the **first** `<article class="small single">`, which is an empty
  ad slot. It now selects the article containing the most paragraphs.
- The embedded Lua block (for Lua Reader–style hosts) is preserved as shipped.

## Deployment

`.github/workflows/deploy.yml` publishes to GitHub Pages on every push to `main`.
The build step extracts the page's script block and runs `node --check` on it, and
asserts no local-dev endpoints leaked into the published file.

## Legal

This repository contains **reader code only** — no chapter text, no images from the
novel, and no keys. It is a personal reading tool. You are responsible for
complying with the novel's terms of use and with the law in your jurisdiction.
