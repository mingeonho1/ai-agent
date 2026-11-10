#!/usr/bin/env node
// Capture screenshots and mobile measurements for design-review, via headless Chrome over CDP.
// Node >= 22 (built-in WebSocket + fetch), no npm deps.
// Usage: node measure.mjs <url> --out <run dir> [--chrome <path>]
// Writes shot-1440.png, shot-768.png, shot-375.png (+ shot-<w>-full.png when tiling works) and measure.json.
// Exit 0 ok, 2 on failure.
//
// Primary CTA heuristic (M7): among visible button, a[class*=btn|button|cta], [role=button], input[type=submit]
// inside <main> or <header> (whole document if neither exists), take the first 3 in document order and pick
// the one with the largest area.
import { spawn, execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const CAPTURE_MS = 15000;
const die = (m) => { console.error(`measure.mjs: ${m}`); process.exitCode = 2; throw new Error(m); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function args() {
  const a = process.argv.slice(2);
  const o = { url: null, out: null, chrome: null };
  for (let i = 0; i < a.length; i++) {
    if (a[i] === "--out") o.out = a[++i];
    else if (a[i] === "--chrome") o.chrome = a[++i];
    else if (!o.url) o.url = a[i];
  }
  if (!o.url || !o.out) die("usage: node measure.mjs <url> --out <run dir> [--chrome <path>]");
  if (existsSync(o.url) && !/^[a-z]+:/i.test(o.url)) o.url = "file://" + resolve(o.url);
  return o;
}

function findChrome(given) {
  const c = [given, process.env.CHROME_PATH,
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium"].filter(Boolean);
  for (const p of c) if (existsSync(p)) return p;
  for (const n of ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]) {
    try { return execFileSync("which", [n], { encoding: "utf8" }).trim(); } catch {}
  }
  die("Chrome not found (set CHROME_PATH or --chrome)");
}

class CDP {
  constructor(ws) { this.ws = ws; this.id = 0; this.wait = new Map(); this.handlers = [];
    ws.onmessage = (e) => { const m = JSON.parse(e.data);
      if (m.id && this.wait.has(m.id)) { const [ok, ko] = this.wait.get(m.id); this.wait.delete(m.id); m.error ? ko(new Error(m.error.message)) : ok(m.result); }
      else this.handlers.forEach((h) => h(m)); }; }
  send(method, params = {}, sessionId, ms = CAPTURE_MS) {
    const id = ++this.id;
    return new Promise((ok, ko) => {
      this.wait.set(id, [ok, ko]);
      setTimeout(() => { if (this.wait.delete(id)) ko(new Error(`timeout: ${method}`)); }, ms);
      this.ws.send(JSON.stringify({ id, method, params, sessionId }));
    });
  }
}

async function launch(chromePath) {
  const profile = mkdtempSync(join(tmpdir(), "measure-chrome-"));
  const proc = spawn(chromePath, ["--headless=new", "--remote-debugging-port=0", `--user-data-dir=${profile}`,
    "--no-first-run", "--no-default-browser-check", "--disable-extensions", "--hide-scrollbars", "--mute-audio",
    "about:blank"], { stdio: "ignore" });
  const portFile = join(profile, "DevToolsActivePort");
  for (let i = 0; i < 100 && !existsSync(portFile); i++) await sleep(100);
  if (!existsSync(portFile)) { proc.kill("SIGKILL"); die("Chrome did not start (no DevToolsActivePort)"); }
  const [port, path] = readFileSync(portFile, "utf8").trim().split("\n");
  const ws = new WebSocket(`ws://127.0.0.1:${port}${path}`);
  await new Promise((ok, ko) => { ws.onopen = ok; ws.onerror = () => ko(new Error("CDP websocket failed")); });
  return { proc, profile, cdp: new CDP(ws), ws };
}

const FREEZE = `(() => { const s = document.createElement('style'); s.textContent =
  '*,*::before,*::after{animation:none!important;transition:none!important;backdrop-filter:none!important;-webkit-backdrop-filter:none!important;caret-color:transparent!important}';
  document.head.appendChild(s); document.documentElement.style.scrollBehavior = 'auto'; window.scrollTo(0, 0); })()`;

const MEASURE = `(() => {
  const vis = (el) => { const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity !== 0; };
  const sel = (el) => { let s = el.tagName.toLowerCase(); if (el.id) return s + '#' + el.id;
    const c = [...el.classList].slice(0, 2).join('.'); return c ? s + '.' + c : s; };
  const txt = (el) => (el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('placeholder') || '').trim().replace(/\\s+/g, ' ').slice(0, 40);
  const inText = (el) => { if (el.tagName !== 'A') return false; const p = el.parentElement; if (!p) return false;
    const own = [...p.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('').trim();
    return own.length > 20 && getComputedStyle(el).display === 'inline'; };
  const vh = innerHeight;
  const small24 = [], small44 = [];
  for (const el of document.querySelectorAll('a,button,input,select,textarea,summary,[role=button]')) {
    if (el.type === 'hidden') continue;
    let box = el;
    if ((el.type === 'checkbox' || el.type === 'radio') && el.closest('label')) box = el.closest('label');
    if (!vis(box)) continue;
    const r = box.getBoundingClientRect(), w = Math.round(r.width), h = Math.round(r.height);
    if (w >= 44 && h >= 44) continue;
    const item = { sel: sel(el), text: txt(el), w, h };
    if (inText(el)) item.exempt = 'inline-text-link';
    (w < 24 || h < 24 ? small24 : small44).push(item);
  }
  const inputs = [...document.querySelectorAll('input,select,textarea')].filter((el) => !['hidden','checkbox','radio','submit','button','image','reset','file','range','color'].includes(el.type) && vis(el))
    .map((el) => ({ sel: sel(el), type: el.type || el.tagName.toLowerCase(), fontSize: parseFloat(getComputedStyle(el).fontSize),
      inputmode: el.getAttribute('inputmode'), autocomplete: el.getAttribute('autocomplete') }));
  const h1 = [...document.querySelectorAll('h1')].find(vis);
  const scope = [...document.querySelectorAll('header,main')];
  const ctaSel = 'button,a[class*=btn],a[class*=button],a[class*=cta],[role=button],input[type=submit]';
  const pool = (scope.length ? scope.flatMap((s) => [...s.querySelectorAll(ctaSel)]) : [...document.querySelectorAll(ctaSel)])
    .filter(vis).sort((a, b) => a.compareDocumentPosition(b) & 2 ? 1 : -1).slice(0, 3);
  const area = (e) => { const r = e.getBoundingClientRect(); return r.width * r.height; };
  const cta = pool.sort((a, b) => area(b) - area(a))[0];
  const bottom = (e) => e ? { sel: sel(e), text: txt(e), bottom: Math.round(e.getBoundingClientRect().bottom + scrollY), inFirstScreen: e.getBoundingClientRect().bottom + scrollY <= vh } : null;
  const fixed = [...document.querySelectorAll('body *')].filter((el) => { const p = getComputedStyle(el).position; return (p === 'fixed' || p === 'sticky') && vis(el); })
    .map((el) => { const h = Math.round(el.getBoundingClientRect().height); return { sel: sel(el), position: getComputedStyle(el).position, height: h, pctOfViewport: Math.round(100 * h / vh) }; });
  return { tapTargets: { under24: small24, under44: small44 }, inputs, h1: bottom(h1), primaryCta: bottom(cta), fixed };
})()`;

async function main() {
  const o = args();
  mkdirSync(o.out, { recursive: true });
  const chrome = findChrome(o.chrome);
  const { proc, profile, cdp, ws } = await launch(chrome);
  const notes = [], consoleErrors = [];
  try {
    const { targetId } = await cdp.send("Target.createTarget", { url: "about:blank" });
    const { sessionId: s } = await cdp.send("Target.attachToTarget", { targetId, flatten: true });
    const send = (m, p, ms) => cdp.send(m, p, s, ms);
    cdp.handlers.push((m) => {
      if (m.sessionId !== s) return;
      if (m.method === "Runtime.consoleAPICalled" && m.params.type === "error")
        consoleErrors.push(m.params.args.map((a) => a.value ?? a.description ?? "").join(" ").slice(0, 200));
      if (m.method === "Runtime.exceptionThrown") consoleErrors.push((m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text).split("\n")[0].slice(0, 200));
      if (m.method === "Log.entryAdded" && m.params.entry.level === "error") consoleErrors.push(`${m.params.entry.text} ${m.params.entry.url || ""}`.trim().slice(0, 200));
    });
    await send("Page.enable"); await send("Runtime.enable"); await send("Log.enable");
    const evaluate = async (expr) => (await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true })).result.value;

    const setView = async (w, h, mobile) => {
      await send("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: 1, mobile });
      await send("Emulation.setTouchEmulationEnabled", mobile ? { enabled: true, maxTouchPoints: 5 } : { enabled: false });
    };
    const load = async () => {
      const loaded = new Promise((ok) => { const h = (m) => { if (m.sessionId === s && m.method === "Page.loadEventFired") ok(); }; cdp.handlers.push(h); });
      const nav = await send("Page.navigate", { url: o.url }, 30000);
      if (nav.errorText) die(`navigation failed: ${nav.errorText}`);
      await Promise.race([loaded, sleep(20000)]);
      await sleep(800);
      await evaluate(FREEZE);
      await evaluate("document.fonts ? document.fonts.ready.then(() => 1) : 1");
    };
    const overflow = async () => evaluate(`({ scrollWidth: document.documentElement.scrollWidth, overflowX: document.documentElement.scrollWidth > innerWidth })`);
    const shot = async (file, clip) => {
      const r = await send("Page.captureScreenshot", { format: "png", ...(clip ? { clip: { ...clip, scale: 1 } } : {}) });
      writeFileSync(join(o.out, file), Buffer.from(r.data, "base64"));
    };
    const fullPage = async (w, h) => {  // tile the page by scrolling; stitched tiles saved as -full-<n>.png
      const total = Math.min(await evaluate("document.documentElement.scrollHeight"), h * 12);
      const files = [];
      for (let y = 0, n = 1; y < total; y += h, n++) {
        await evaluate(`window.scrollTo(0, ${y})`); await sleep(150);
        const f = `shot-${w}-full-${n}.png`; await shot(f); files.push(f);
      }
      await evaluate("window.scrollTo(0, 0)");
      return files;
    };

    const viewports = {};
    let fullDone = true;
    for (const [w, h, mobile] of [[1440, 900, false], [768, 1024, true], [375, 812, true]]) {
      await setView(w, h, mobile); await load();
      viewports[w] = { width: w, height: h, ...(await overflow()) };
      await shot(`shot-${w}.png`);
      if (fullDone) {
        try { viewports[w].fullPage = await fullPage(w, h); }
        catch (e) { fullDone = false; notes.push(`full page skipped (${e.message})`); }
      }
      if (w === 375) Object.assign(viewports[w], await evaluate(MEASURE));
    }
    for (const w of [320, 1920]) {
      await setView(w, w === 320 ? 640 : 1080, w === 320); await load();
      viewports[w] = { width: w, height: w === 320 ? 640 : 1080, ...(await overflow()) };
    }
    const out = { url: o.url, chrome, viewports, consoleErrors: [...new Set(consoleErrors)].slice(0, 20), notes };
    writeFileSync(join(o.out, "measure.json"), JSON.stringify(out, null, 1));
    const m = viewports[375];
    console.log(`measure.json written: overflowX ${Object.values(viewports).filter((v) => v.overflowX).map((v) => v.width).join(",") || "none"}`
      + ` · tap<24 ${m.tapTargets.under24.length} · tap<44 ${m.tapTargets.under44.length} · fixed ${m.fixed.length}`
      + ` · console errors ${out.consoleErrors.length}${notes.length ? " · " + notes.join("; ") : ""}`);
  } finally {
    try { ws.close(); } catch {}
    proc.kill("SIGKILL");
    await sleep(200);
    try { rmSync(profile, { recursive: true, force: true }); } catch {}
  }
}

main().catch((e) => { if (!process.exitCode) console.error(`measure.mjs: ${e.message}`); process.exit(2); });
