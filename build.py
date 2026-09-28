#!/usr/bin/env python3
"""Build index.html from truthnovel-mini.html.

Every substitution is asserted, so a failed patch aborts loudly instead of
silently producing a half-patched page.
"""
import os
import sys

SRC = "/storage/emulated/0/Download/truthnovel-mini.html"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")

PATCHES = []


def patch(name, old, new):
    PATCHES.append((name, old, new))


# --- A. layered fetch chain: local proxy -> direct -> relay -> legacy --------
patch(
    "fetch-chain",
    'async function ft(u,p=false){const x=p?"https://api.allorigins.win/raw?url="+encodeURIComponent(u):u,r=await fetch(x,{cache:"no-store"});if(!r.ok)throw Error("HTTP "+r.status);return r.text()}\n'
    'async function get(u){try{return await ft(u)}catch{try{return await ft(u,true)}catch{throw Error("Source request failed (direct + CORS fallback).")}}}',
    'const LOCAL=/^(127\\.0\\.0\\.1|localhost|0\\.0\\.0\\.0)$/.test(location.hostname);\n'
    'function chain(u){const c=[];if(LOCAL)c.push("/_p?url="+encodeURIComponent(u));c.push(u);const r=(d.relay||"").trim();if(r)c.push(r+(r.includes("?")?"&":"?")+"url="+encodeURIComponent(u));c.push("https://api.allorigins.win/raw?url="+encodeURIComponent(u));return c}\n'
    'async function raw(x,ms){const ac=new AbortController(),t=setTimeout(()=>ac.abort(),ms||25000);try{const r=await fetch(x,{cache:"no-store",signal:ac.signal});if(!r.ok)throw Error("HTTP "+r.status);const h=await r.text();if(h.length<2000)throw Error("empty body ("+h.length+"B)");return h}finally{clearTimeout(t)}}\n'
    'async function get(u){const c=chain(u);let e;for(const x of c){try{return await raw(x)}catch(err){e=err}}throw Error("All fetch routes failed"+(e?" ("+e.message+")":""))}',
)

# --- B. read(): pick the article that actually has paragraphs ---------------
patch(
    "read-best-article",
    'const d=new DOMParser().parseFromString(h,"text/html"),a=d.querySelector(".bs-blog-post.single > article")||d.querySelector("article");if(!a)throw Error("Chapter article not found")',
    'const d=new DOMParser().parseFromString(h,"text/html"),c=[...d.querySelectorAll("article,.entry-content,.post-content")].map(x=>[x,x.querySelectorAll("p").length]).sort((x,y)=>y[1]-x[1]),a=c[0]&&c[0][0];if(!a)throw Error("Chapter article not found")',
)

# --- C. translation: system-role prompt, sanitize, validate, retry ----------
PATCHES.append(
    (
        "translate",
        None,
        r'''const AR=/[\u0600-\u06FF]/;
const REFUSE=/(can(?:no|')t (?:help|assist|comply|provide)|i'?m just a language model|unable to (?:help|assist|translate|comply|provide)|i cannot (?:help|assist|translate|provide)|as a language model|not able to (?:help|translate|provide)|something went wrong|cannot fulfill|please try your request again)/i;
function paras(x){return String(x||"").split(/\n{2,}/).map(s=>s.trim()).filter(Boolean)}
function cleanOut(o){let t=String(o||"").trim();t=t.replace(/^```[a-z]*\s*/i,"").replace(/\s*```$/,"").trim();t=t.replace(/^(?:[*_#>`\s]|\*\*|__)*(?:sure[,!.\s]*)?(?:here(?:\s+is|\x27s)\b[^\n:]{0,80}:|translation:|translated text:|english:)(?:[*_`\s:]|\*\*|__)*\s*/i,"").trim();t=t.replace(/\*\*|__/g,"");const ps=t.split(/\n{2,}/);while(ps.length>1&&/^\s*(?:[*_#>`\s-])*(translator\x27?s?\s+note|notes?|hope (this|that)|let me know|disclaimer|if you (need|want)|i hope|feel free)(?:[*_`\s:.-])*[:\s]/i.test(ps[ps.length-1]))ps.pop();return ps.join("\n\n").replace(/\n{3,}/g,"\n\n").trim()}
async function api(text){const u=d.api.replace(/\/+$/,"")+"/chat/completions",sys=P.replace("{source_language}","Arabic").replace("{target_language}",d.target),want=paras(text).length;let last;for(let i=0;i<2;i++){const hint=i?"\n\n[IMPORTANT: your previous reply was rejected. Output ONLY the "+want+" translated paragraphs in order, separated by blank lines. No preamble, no notes, no markdown, no commentary.]":"";const ac=new AbortController(),tm=setTimeout(()=>ac.abort(),90000);let j;try{const r=await fetch(u,{method:"POST",headers:{"Content-Type":"application/json",...(d.key?{"Authorization":"Bearer "+d.key}:{})},body:JSON.stringify({model:d.model,stream:false,messages:[{role:"system",content:sys},{role:"user",content:text+hint}]}),signal:ac.signal});if(!r.ok){let z="";try{z=(await r.json())?.error?.message||""}catch{}throw Error("Web2API HTTP "+r.status+(z?": "+z.slice(0,120):""))}j=await r.json()}catch(e){last=e;continue}finally{clearTimeout(tm)}const out=cleanOut(j?.choices?.[0]?.message?.content);if(!out){last=Error("empty translation");continue}if(REFUSE.test(out)){throw Error("The model refused to translate this text (content policy). This is a backend limit, not a page bug - try a different translation endpoint in Settings.")}if(AR.test(out)&&!/[A-Za-z]/.test(out)){last=Error("source echoed instead of translated");continue}const got=paras(out).length;if(want>2&&(got<Math.ceil(want*0.5)||got>Math.ceil(want*1.5))){last=Error("paragraph mismatch ("+got+" of "+want+")");continue}return out}throw last||Error("translation failed")}
async function translate(){if(!txt)return;const cached=localStorage.getItem(T+"-"+(ch[cur].n||cur+1));if(cached){eng=cached;show(eng,true);showEng=true;return}$("state").classList.add("on");$("stateMsg").textContent="Preparing translation…";$("prog").style.width="0%";$("translate").disabled=true;const ps=paras(txt),chunks=[];let b="",len=0;for(const p of ps){if(b&&len+p.length+2>3500){chunks.push(b);b="";len=0}b+=b?"\n\n"+p:p;len+=p.length+2}if(b)chunks.push(b);const out=[];try{for(let i=0;i<chunks.length;i++){$("stateMsg").textContent=`Translating part ${i+1} of ${chunks.length}…`;$("prog").style.width=Math.round(i/chunks.length*100)+"%";out.push(await api(chunks[i]))}eng=out.join("\n\n");localStorage.setItem(T+"-"+(ch[cur].n||cur+1),eng);$("prog").style.width="100%";$("stateMsg").textContent="Translation complete · cached locally";show(eng,true);showEng=true;$("translate").textContent="Show original"}catch(e){$("stateMsg").textContent="Translation failed: "+e.message;msg("Translation failed")}finally{$("translate").disabled=false}}''',
    )
)

# --- D. settings: relay field, clearer notice, test relay button ------------
patch(
    "relay-field",
    '<label>API key<input class="input" id="key" type="password" value="sk-gemini"></label>',
    '<label>API key<input class="input" id="key" type="password" value="sk-gemini"></label>\n'
    '<label>Fetch relay URL<input class="input" id="relay" value=""><div class="hint">Optional. A relay that returns raw page HTML with CORS enabled. Required when this page is hosted publicly, because truthnovel.top refuses direct browser requests. Deploy <code>worker/</code> from the repo and paste its URL here.</div></label>',
)

patch(
    "notice",
    '<div class="notice">The public page does not contain a Gemini API key. Translation uses the Web2API endpoint you configure.</div>',
    '<div class="notice">This page ships no Gemini key. On a hosted page <b>127.0.0.1 means the device you are viewing it on</b> &#8212; to translate, either run gemini-web2api locally on that device (port 8081) or paste any OpenAI-compatible base URL above.</div>',
)

patch(
    "test-relay-button",
    '<div class="ma"><button class="btn" id="test">Test API</button>',
    '<div class="ma"><button class="btn" id="testRelay">Test relay</button><button class="btn" id="test">Test translation</button>',
)

# --- E. defaults, load, save ------------------------------------------------
patch(
    "defaults",
    'const d={api:"http://127.0.0.1:8081/v1",key:"sk-gemini",model:"gemini-3.6-flash",target:"English"},LS=',
    'const d={api:"http://127.0.0.1:8081/v1",key:"sk-gemini",model:"gemini-3.6-flash",target:"English",relay:""},LS=',
)

patch(
    "load-settings",
    '$("api").value=d.api;$("key").value=d.key;',
    '$("api").value=d.api;$("relay").value=d.relay||"";$("key").value=d.key;',
)

patch(
    "save-settings",
    'd.api=$("api").value.trim().replace(/\\/+$/,"");d.key=',
    'd.api=$("api").value.trim().replace(/\\/+$/,"");d.relay=$("relay").value.trim();d.key=',
)

# --- F. real translation test + relay test ---------------------------------
patch(
    "test-handlers",
    '$("test").onclick=async()=>{try{const r=await fetch($("api").value.trim().replace(/\\/+$/,"")+"/models",{headers:$("key").value.trim()?{"Authorization":"Bearer "+$("key").value.trim()}:{} });if(!r.ok)throw Error("HTTP "+r.status);msg("Web2API connection works")}catch(e){msg("API test failed: "+e.message)}};',
    '$("test").onclick=async()=>{try{const base=$("api").value.trim().replace(/\\/+$/,""),kh=$("key").value.trim(),hd={"Content-Type":"application/json",...(kh?{"Authorization":"Bearer "+kh}:{})};const r=await fetch(base+"/chat/completions",{method:"POST",headers:hd,body:JSON.stringify({model:$("model").value.trim()||"gemini-3.6-flash",stream:false,messages:[{role:"user",content:"Reply with the single word: ready"}]})});if(!r.ok)throw Error("HTTP "+r.status);const j=await r.json(),c=j?.choices?.[0]?.message?.content;if(!c)throw Error("no completion in reply");msg("Translation API OK - model replied: "+String(c).trim().slice(0,24))}catch(e){msg("API test failed: "+e.message)}};'
    '$("testRelay").onclick=async()=>{const r=($("relay").value||"").trim();if(!r)return msg("Relay URL is empty");try{const u=r+(r.includes("?")?"&":"?")+"url="+encodeURIComponent(S.lists[0]),h=await raw(u,30000);msg("Relay OK - "+h.length+" bytes returned")}catch(e){msg("Relay failed: "+e.message)}};',
)

# --- G. surface the real error when the catalog fails -----------------------
patch(
    "load-error",
    'for(const u of S.lists)try{const x=parse(await get(u));if(x.length>10){ch=x;try{localStorage.setItem(C,JSON.stringify({at:Date.now(),chapters:ch}))}catch{};render();return}}catch{};if(!ch.length){list.innerHTML=\'<div class=empty>Could not load the live chapter list.</div>\';status.textContent="Load failed"}',
    'let err="";for(const u of S.lists)try{const x=parse(await get(u));if(x.length>10){ch=x;try{localStorage.setItem(C,JSON.stringify({at:Date.now(),chapters:ch}))}catch{};render();return}}catch(e){err=e.message};if(!ch.length){list.innerHTML=\'<div class=empty>Could not load the live chapter list.<br><small>\'+esc(err||"no route returned content")+\'</small><br><br>If the source is blocked on your network, deploy the relay from <code>worker/</code> and paste its URL into Settings.</div>\';status.textContent="Load failed"}',
)


# --- H. relay.txt bootstrap: set the relay once, redeploy ------------------
patch(
    "relay-bootstrap",
    '$("api").value=d.api;$("relay").value=d.relay||"";$("key").value=d.key;',
    '$("api").value=d.api;$("relay").value=d.relay||"";$("key").value=d.key;'
    'fetch("relay.txt",{cache:"no-store"}).then(r=>r.ok?r.text():"").then(t=>{t=(t||"").trim();if(t&&!d.relay){d.relay=t;$("relay").value=t;msg("Relay loaded from relay.txt")}}).catch(()=>{});',
)


# --- I. bundled catalog: load chapters.json before hitting any relay -------
patch(
    "bundled-catalog",
    'if(!force)try{const c=JSON.parse(localStorage.getItem(C)||"null");if(c?.chapters){ch=c.chapters;render()}}catch{};let err="";',
    'if(!force)try{const c=JSON.parse(localStorage.getItem(C)||"null");if(c?.chapters){ch=c.chapters;render()}}catch{};let err="";'
    'if(!force)try{const j=JSON.parse(await raw("chapters.json",15000));if(j&&j.chapters&&j.chapters.length>10){ch=j.chapters;try{localStorage.setItem(C,JSON.stringify({at:Date.now(),chapters:ch}))}catch{};render();return}}catch(e){err="bundled catalog: "+e.message};',
)

# --- J. clearer guidance when a chapter body cannot be fetched ------------
patch(
    "read-error-hint",
    'If the source is blocked on your network, deploy the relay from <code>worker/</code> and paste its URL into Settings.',
    'Reading a chapter needs a relay: the site blocks direct browser requests. Deploy <code>worker/</code> from the repo and paste its URL into Settings (or into relay.txt).',
)

# --- K. a failed chapter read should say what to do, not just "Failed" -----
patch(
    "chapter-read-error",
    'catch(e){body.innerHTML="<div class=empty>Could not load this chapter.<br><small>"+esc(e.message)+"</small></div>"}',
    'catch(e){body.innerHTML="<div class=empty>Could not load this chapter.<br><small>"+esc(e.message)+"</small><br><br>'
    'The chapter list is bundled, but chapter text must be fetched live and this site blocks direct browser requests.<br>'
    'Deploy the free relay from the <code>worker/</code> folder in the repo, then paste its URL into Settings.'
    '</div>"}',
)


OLD_READ = (
    'async function read(h){const d=new DOMParser().parseFromString(h,"text/html"),'
    'c=[...d.querySelectorAll("article,.entry-content,.post-content")]'
    '.map(x=>[x,x.querySelectorAll("p").length]).sort((x,y)=>y[1]-x[1]),a=c[0]&&c[0][0];'
    'if(!a)throw Error("Chapter article not found");'
    'a.querySelectorAll("script,style").forEach(x=>x.remove());'
    'const p=[...a.querySelectorAll("p")].map(x=>(x.textContent||"").replace(/\\u00a0/g," ").trim()).filter(Boolean);'
    'return p.join("\\n\\n")}'
)

NEW_READ = (
    'const SEL="article,.entry-content,.post-content,.post-body,.td-post-content,'
    '.single-content,.entry,.content-area,#content,main";'
    'async function read(h){'
    'const d=new DOMParser().parseFromString(h,"text/html");'
    'if(!d.body)throw Error("empty response");'
    'const head=((d.querySelector("title")||{}).textContent||"")+" "+(d.body.textContent||"").slice(0,2000);'
    'if(/just a moment|attention required|enable javascript and cookies|access denied|'
    'checking your browser|cf-error|error 5\\d\\d|request blocked|forbidden/i.test(head))'
    'throw Error("the relay or your network returned a block/error page, not the chapter");'
    'let best=null,bs=0;'
    'for(const x of d.querySelectorAll(SEL)){const p=x.querySelectorAll("p").length,'
    's=p*1000+(x.textContent||"").trim().length;if(p>=3&&s>bs){bs=s;best=x}}'
    'if(!best){const g=new Map();'
    'for(const p of d.querySelectorAll("p")){const n=p.parentElement;if(!n)continue;'
    'g.set(n,(g.get(n)||0)+1)}'
    'for(const [n,c] of g){if(c>=3&&c*1000+(n.textContent||"").length>bs){bs=c*1000;best=n}}}'
    'if(!best)throw Error("no chapter text in the response ("+(d.body.textContent||"").trim().length+" chars returned)");'
    'best.querySelectorAll("script,style,ins,iframe,noscript,svg").forEach(x=>x.remove());'
    'const seen=new Set(),out=[];'
    'for(const p of best.querySelectorAll("p")){const s=(p.textContent||"").replace(/\\u00a0/g," ")'
    '.replace(/[ \\t]+/g," ").trim();if(!s||seen.has(s))continue;seen.add(s);out.push(s)}'
    'if(!out.length)throw Error("chapter container found but it held no readable paragraphs");'
    'return out.join("\\n\\n")}'
)

PATCHES.append(("read-robust", OLD_READ, NEW_READ))


# --- L. api.txt: hosted translation backend URL, same pattern as relay.txt --
patch(
    "api-bootstrap",
    '$("api").value=d.api;$("relay").value=d.relay||"";$("key").value=d.key;',
    '$("api").value=d.api;$("relay").value=d.relay||"";$("key").value=d.key;'
    'fetch("api.txt",{cache:"no-store"}).then(r=>r.ok?r.text():"").then(t=>{t=(t||"").trim();'
    'if(t&&t[0]!=="#"&&!d.api){d.api=t;$("api").value=t;msg("Translation API loaded from api.txt")}})'
    ".catch(()=>{});",
)

# --- M. serve chapters already translated by the Actions workflow ----------
patch(
    "i18n-cache",
    'async function translate(){if(!txt)return;const cached=localStorage.getItem(T+"-"+(ch[cur].n||cur+1));'
    'if(cached){eng=cached;show(eng,true);showEng=true;return}$("state").classList.add("on");',
    'async function translate(){if(!txt)return;const cached=localStorage.getItem(T+"-"+(ch[cur].n||cur+1));'
    'if(cached){eng=cached;show(eng,true);showEng=true;return}'
    'try{const r=await fetch("i18n/"+encodeURIComponent(ch[cur].id)+".json",{cache:"force-cache"});'
    'if(r.ok){const j=await r.json();if(j&&typeof j.text==="string"&&j.text.length>200){'
    'eng=j.text;show(eng,true);showEng=true;$("translate").textContent="Show original";'
    'try{localStorage.setItem(T+"-"+(ch[cur].n||cur+1),eng)}catch{};return}}}catch{}'
    '$("state").classList.add("on");',
)


def main():
    with open(SRC, encoding="utf-8", errors="replace") as f:
        s = f.read()
    for name, old, new in PATCHES:
        if old is None:
            # replace the two original translation functions as a block
            start = s.index("async function translate(){")
            end = s.index("async function close", start) if "async function close" in s[start:] else None
            marker = "function close(){"
            end = s.index(marker, start)
            s = s[:start] + new + "\n" + s[end:]
            print("  patched: %s (block replace)" % name)
            continue
        if old not in s:
            sys.exit("FAILED: anchor not found for patch %r" % name)
        if s.count(old) != 1:
            sys.exit("FAILED: anchor for %r appears %d times" % (name, s.count(old)))
        s = s.replace(old, new)
        print("  patched: %s" % name)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(s)
    print("wrote %s (%d bytes)" % (OUT, len(s)))


if __name__ == "__main__":
    main()
