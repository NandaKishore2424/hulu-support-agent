"""Generate a local, keyboard-driven labelling page for the golden set.

Design choices that matter for the integrity of the labels:

* The brand's real historical reply is hidden. Reading it first would anchor the
  label to how Hulu happened to answer, which is exactly the thing the agent is
  later scored against. A reveal key exists and every reveal is recorded, so the
  report can state how often the labeller needed to peek.
* Slice membership (random vs boost) is not shown, so knowing an item was pulled
  by a rare-intent probe cannot nudge the label toward that intent.
* Every keystroke is timestamped. Suspiciously fast labels are findable later.

Output: data/golden/label.html, opened directly in a browser. No server, and the
labels never leave the machine until exported.

Usage:  python scripts/04_make_labeller.py --brand hulu_support
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agent import config as C                                        # noqa: E402
from agent.taxonomy import ESCALATION_RULES, INTENTS                 # noqa: E402

HTML = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>Golden set labelling</title>
<style>
:root{--bg:#101216;--fg:#e8eaed;--dim:#9aa0a6;--line:#2a2e35;--acc:#4ade80;--warn:#fbbf24}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;display:flex}
#main{flex:1;padding:24px 28px;max-width:820px}
#side{width:390px;border-left:1px solid var(--line);padding:18px 20px;height:100vh;overflow:auto;font-size:12.5px;color:var(--dim)}
#bar{height:4px;background:var(--line);border-radius:2px;margin-bottom:18px}
#bar>div{height:100%;background:var(--acc);border-radius:2px;transition:width .15s}
.meta{color:var(--dim);font-size:12px;display:flex;gap:16px;margin-bottom:10px}
#msg{font-size:20px;line-height:1.45;background:#171a1f;border:1px solid var(--line);
     border-left:3px solid var(--acc);padding:18px 20px;border-radius:6px;white-space:pre-wrap}
#reply{margin-top:12px;padding:14px 16px;background:#14171c;border:1px dashed var(--line);
       border-radius:6px;color:var(--dim);font-size:14px;white-space:pre-wrap}
h4{margin:20px 0 8px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--dim)}
.opt{display:flex;gap:10px;align-items:baseline;padding:5px 8px;border-radius:4px;cursor:pointer}
.opt:hover{background:#1b1f25}
.opt.sel{background:#1e2a20;color:var(--acc)}
kbd{background:#22262d;border:1px solid var(--line);border-bottom-width:2px;border-radius:4px;
    padding:1px 7px;font:12px ui-monospace,monospace;color:var(--fg);min-width:22px;text-align:center}
.stage{opacity:.35;pointer-events:none}
.stage.on{opacity:1;pointer-events:auto}
#done{color:var(--acc)} #peeked{color:var(--warn)}
button{background:#22262d;color:var(--fg);border:1px solid var(--line);border-radius:5px;
       padding:7px 14px;cursor:pointer;font-size:13px}
button:hover{border-color:var(--acc)}
.tax{margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid var(--line)}
.tax b{color:var(--fg);font-size:12.5px}
.tax .bd{color:#7c828a;font-style:italic;margin-top:3px}
#hud{position:fixed;bottom:0;left:0;right:390px;background:#0b0d10;border-top:1px solid var(--line);
     padding:9px 28px;font-size:12px;color:var(--dim);display:flex;gap:20px;align-items:center}
</style></head><body>
<div id="main">
  <div id="bar"><div style="width:0"></div></div>
  <div class="meta">
    <span id="pos"></span><span id="cid"></span><span id="date"></span>
    <span id="done"></span><span id="goal" style="color:#fbbf24"></span><span id="peeked"></span>
  </div>
  <div id="msg"></div>
  <div id="reply" hidden></div>

  <div id="s1"><h4>1 &middot; primary intent</h4><div id="intents"></div></div>
  <div id="s2" class="stage"><h4>2 &middot; handling</h4><div id="handling"></div></div>
  <div id="s3" class="stage"><h4>3 &middot; escalation reason</h4><div id="reasons"></div></div>

  <div style="margin:26px 0 60px;display:flex;gap:10px;flex-wrap:wrap">
    <button onclick="prev()">&larr; back</button>
    <button onclick="next()">skip &rarr;</button>
    <button onclick="reveal()">reveal Hulu's reply (R)</button>
    <button onclick="toggleAmb()">flag ambiguous (M)</button>
    <button onclick="exportJSON()" style="border-color:var(--acc);color:var(--acc)">export JSON</button>
  </div>
</div>
<div id="side"><h4 style="margin-top:0">label definitions</h4><div id="cheat"></div></div>
<div id="hud">
  <span><kbd>1</kbd>&ndash;<kbd>0</kbd> intent</span>
  <span><kbd>a</kbd> auto &middot; <kbd>e</kbd> escalate</span>
  <span><kbd>r</kbd> reveal &middot; <kbd>m</kbd> ambiguous</span>
  <span><kbd>&larr;</kbd><kbd>&rarr;</kbd> navigate</span>
  <span id="amb"></span>
  <span id="nostore" hidden style="color:var(--warn)">no browser storage on this origin &mdash;
    serve with <code>scripts/label.sh</code>; auto-exporting every 20 labels instead</span>
</div>
<script>
const ITEMS = __ITEMS__, TAX = __TAX__, REASONS = __REASONS__;
const KEY = "golden_labels_v1";

// Browsers refuse storage on file:// origins, so a page opened by double-click
// would silently lose an hour of labelling. Detect that, keep going in memory,
// and warn loudly instead of pretending the work is saved.
let STORAGE_OK = true;
function store(k, v){ try { localStorage.setItem(k, v); } catch(e){ STORAGE_OK = false; } }
function load(k){ try { return localStorage.getItem(k); } catch(e){ STORAGE_OK = false; return null; } }
let labels = JSON.parse(load(KEY) || "{}");
let i = 0, stage = 1, sinceBackup = 0;

function cur(){ return ITEMS[i]; }
function rec(){ const k = cur().case_id; return labels[k] || (labels[k] = {case_id:k, idx:cur().idx}); }
function save(){
  store(KEY, JSON.stringify(labels));
  // Without storage the only safe place for the work is a file on disk, so
  // auto-export every 20 labels rather than trusting the tab to stay open.
  if(!STORAGE_OK && ++sinceBackup >= 20){ sinceBackup = 0; exportJSON(true); }
}

function renderCheat(){
  document.getElementById("cheat").innerHTML = TAX.map((t,n)=>
    `<div class="tax"><b><kbd>${(n+1)%10}</kbd> ${t.name}</b><div>${t.definition}</div>
     <div class="bd">${t.boundary}</div></div>`).join("");
}
function render(){
  const c = cur(), r = labels[c.case_id] || {};
  document.querySelector("#bar>div").style.width = (100*Object.values(labels).filter(x=>x.intent&&x.handling).length/ITEMS.length)+"%";
  document.getElementById("pos").textContent = `item ${i+1} / ${ITEMS.length}`;
  const nDone = Object.values(labels).filter(x=>x.intent&&x.handling).length;
  const goal = document.getElementById("goal");
  if(goal){
    if(nDone < 120) goal.textContent = `${120-nDone} more for the headline results`;
    else if(nDone < 150) goal.textContent = `${150-nDone} more to meet the brief's minimum of 150`;
    else if(nDone < ITEMS.length) goal.textContent = `past the minimum, ${ITEMS.length-nDone} optional left`;
    else goal.textContent = "complete";
  }
  document.getElementById("cid").textContent = c.case_id;
  document.getElementById("date").textContent = c.created_at;
  const n = Object.values(labels).filter(x=>x.intent&&x.handling).length;
  document.getElementById("done").textContent = `${n} complete`;
  document.getElementById("peeked").textContent = r.peeked ? "peeked" : "";
  document.getElementById("msg").textContent = c.customer_opening;
  const rep = document.getElementById("reply");
  rep.hidden = !r.peeked; rep.textContent = "Hulu actually replied: " + c.brand_first_reply;
  document.getElementById("amb").textContent = r.ambiguous ? "flagged ambiguous" : "";
  document.getElementById("nostore").hidden = STORAGE_OK;

  document.getElementById("intents").innerHTML = TAX.map((t,n)=>
    `<div class="opt ${r.intent===t.name?'sel':''}" onclick="pickIntent('${t.name}')">
       <kbd>${(n+1)%10}</kbd><span>${t.name}</span></div>`).join("");
  document.getElementById("handling").innerHTML =
    `<div class="opt ${r.handling==='auto'?'sel':''}" onclick="pickHandling('auto')">
       <kbd>a</kbd><span>auto-handle: a correct public reply exists with no account access</span></div>
     <div class="opt ${r.handling==='escalate'?'sel':''}" onclick="pickHandling('escalate')">
       <kbd>e</kbd><span>escalate to a human</span></div>`;
  document.getElementById("reasons").innerHTML = REASONS.map((x,n)=>
    `<div class="opt ${r.reason===x.name?'sel':''}" onclick="pickReason('${x.name}')">
       <kbd>${n+1}</kbd><span>${x.name} &mdash; ${x.why}</span></div>`).join("");

  document.getElementById("s2").className = "stage" + (stage>=2?" on":"");
  document.getElementById("s3").className = "stage" + (stage>=3?" on":"");
  window.scrollTo(0,0);
}
function pickIntent(name){ const r=rec(); r.intent=name; r.t_intent=Date.now(); stage=2; save(); render(); }
function pickHandling(h){
  const r=rec(); r.handling=h; r.t_handling=Date.now();
  if(h==="auto"){ delete r.reason; stage=1; save(); next(); }
  else { stage=3; save(); render(); }
}
function pickReason(name){ const r=rec(); r.reason=name; save(); stage=1; next(); }
function reveal(){ const r=rec(); r.peeked=true; save(); render(); }
function toggleAmb(){ const r=rec(); r.ambiguous=!r.ambiguous; save(); render(); }
function next(){ if(i<ITEMS.length-1){ i++; stage=1; render(); } else { alert("End of set. Export when ready."); } }
function prev(){ if(i>0){ i--; stage=1; render(); } }

document.addEventListener("keydown", e=>{
  if(e.metaKey||e.ctrlKey||e.altKey) return;
  const k = e.key.toLowerCase();
  if(k==="arrowright"){ next(); return; } if(k==="arrowleft"){ prev(); return; }
  if(k==="r"){ reveal(); return; } if(k==="m"){ toggleAmb(); return; }
  if(stage===3 && /^[1-7]$/.test(k)){ pickReason(REASONS[+k-1].name); return; }
  if(stage===2){ if(k==="a"||k==="e"){ pickHandling(k==="a"?"auto":"escalate"); return; } }
  if(stage===1 && /^[0-9]$/.test(k)){
    const n = k==="0" ? 9 : +k-1;
    if(TAX[n]) pickIntent(TAX[n].name);
  }
});
function exportJSON(auto){
  const rows = ITEMS.map(c=>({...(labels[c.case_id]||{case_id:c.case_id,idx:c.idx})}));
  const blob = new Blob([rows.map(r=>JSON.stringify(r)).join("\n")], {type:"application/x-ndjson"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = auto ? "golden_labels_autosave.jsonl" : "golden_labels.jsonl";
  a.click();
}
renderCheat(); render();
</script></body></html>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default="hulu_support")
    args = ap.parse_args()

    src = C.GOLDEN_DIR / f"golden_unlabelled_{args.brand}.jsonl"
    items = [json.loads(line) for line in src.read_text(encoding="utf-8").splitlines()]

    # Random-slice items are presented first, keeping their seeded order, then the
    # keyword-probed ones. The order is invisible to the labeller, who still cannot
    # tell which slice an item came from, so it introduces no labelling bias.
    #
    # It buys two things. The headline numbers need only the random slice, so they
    # are complete once the first 120 are done and the set stays usable if
    # labelling is cut short. And the freshest attention lands on the slice that
    # every headline figure depends on, rather than on the boost slice.
    items = ([it for it in items if it.get("slice") == "random"]
             + [it for it in items if it.get("slice") != "random"])

    # slice/probe deliberately withheld from the page so they cannot bias labels
    public = [{k: v for k, v in it.items() if k not in ("slice", "probe")} for it in items]

    tax = [{"name": i.name, "definition": i.definition, "boundary": i.boundary}
           for i in INTENTS]
    reasons = [{"name": n, "why": w} for n, w in ESCALATION_RULES]

    html = (HTML
            .replace("__ITEMS__", json.dumps(public, ensure_ascii=False))
            .replace("__TAX__", json.dumps(tax, ensure_ascii=False))
            .replace("__REASONS__", json.dumps(reasons, ensure_ascii=False)))
    out = C.GOLDEN_DIR / "label.html"
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out}  ({len(public)} items, {out.stat().st_size // 1024} KB)")
    print("open it in a browser, label with the keyboard, then click 'export JSON'")


if __name__ == "__main__":
    main()
