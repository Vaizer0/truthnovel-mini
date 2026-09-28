/**
 * Truth Novel fetch relay (Cloudflare Worker).
 *
 * truthnovel.top does not send CORS headers and returns an empty body to many
 * networks, so a browser cannot read it directly. GitHub Pages is static and
 * cannot proxy at request time, so this Worker sits in front of it.
 *
 * Usage:  GET /?url=<url-encoded absolute URL>
 * Deploy: npm i -g wrangler && wrangler deploy
 *         (or use the "Deploy to Cloudflare Workers" button in the repo README)
 */

const BLOCKED_HOSTS = new Set([
  "localhost",
  "127.0.0.1",
  "0.0.0.0",
  "::1",
  "metadata.google.internal",
]);

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "*",
  "Access-Control-Max-Age": "86400",
};

const MIN_BYTES = 2000;
const TIMEOUT_MS = 20000;

/** Reject anything that is not a public http(s) URL, to keep this from being an open proxy into private networks. */
function validate(raw) {
  let u;
  try {
    u = new URL(raw);
  } catch {
    throw new Error("Invalid URL");
  }
  if (u.protocol !== "http:" && u.protocol !== "https:") {
    throw new Error("Only http and https are allowed");
  }
  if (BLOCKED_HOSTS.has(u.hostname.toLowerCase())) {
    throw new Error("Host not allowed");
  }
  if (/^(10\.|127\.|192\.168\.|169\.254\.)/.test(u.hostname) || u.hostname.endsWith(".local")) {
    throw new Error("Host not allowed");
  }
  return u.href;
}

async function readBody(res) {
  const text = await res.text();
  return text.length < MIN_BYTES ? new Error(`upstream returned ${text.length} bytes`) : text;
}

async function fetchDirect(target) {
  const res = await fetch(target, {
    headers: { "User-Agent": "Mozilla/5.0 (compatible; TruthNovelRelay/1.0)", Accept: "text/html,*/*" },
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  if (!res.ok) throw new Error(`upstream HTTP ${res.status}`);
  return readBody(res);
}

async function fetchViaJina(target) {
  const res = await fetch(`https://r.jina.ai/${target}`, {
    headers: { "X-Return-Format": "html" },
    signal: AbortSignal.timeout(TIMEOUT_MS + 10000),
  });
  if (!res.ok) throw new Error(`jina HTTP ${res.status}`);
  return readBody(res);
}

export default {
  async fetch(request) {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS });
    }
    if (request.method !== "GET") {
      return new Response("Method not allowed", { status: 405, headers: { ...CORS, Allow: "GET, OPTIONS" } });
    }

    const target = new URL(request.url).searchParams.get("url");
    if (!target) {
      return new Response("Missing ?url= parameter", { status: 400, headers: { ...CORS, "Content-Type": "text/plain" } });
    }

    let url;
    try {
      url = validate(target);
    } catch (e) {
      return new Response(e.message, { status: 400, headers: { ...CORS, "Content-Type": "text/plain" } });
    }

    const tried = [];
    for (const [name, fn] of [["direct", fetchDirect], ["jina", fetchViaJina]]) {
      try {
        const body = await fn(url);
        return new Response(body, {
          status: 200,
          headers: {
            ...CORS,
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "public, max-age=1800",
            "X-Relay-Route": name,
          },
        });
      } catch (e) {
        tried.push(`${name}: ${e.message}`);
      }
    }

    return new Response(`All routes failed -> ${tried.join(" | ")}`, {
      status: 502,
      headers: { ...CORS, "Content-Type": "text/plain" },
    });
  },
};
