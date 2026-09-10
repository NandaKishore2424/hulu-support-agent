"""Build the human rating pass used to validate the LLM judge.

An LLM judge is worthless as evidence until someone checks it against a person.
This page collects human ratings on the same rubric and the same items the judge
scored, so agreement can be measured rather than asserted.

Sampling is across systems on purpose. If a human only rated the agent's replies,
almost every rating would be a 4 and agreement statistics would be unstable,
because kappa needs variance to be meaningful. Drawing the same cases from the
majority baseline, the copy baseline and the agent guarantees a spread of real
quality.

The rater never sees which system wrote a reply, and the replies for a given case
are shuffled, so a rater cannot infer the system from its position.

Usage:  python scripts/07_make_rater.py --n-cases 14 --systems agent keyword_knn majority
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agent import config as C                       # noqa: E402
from agent.judge import RUBRIC                      # noqa: E402

PRED_DIR = C.REPORT_DIR / "predictions"

HTML = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>Reply rating</title>
<style>
:root{--bg:#101216;--fg:#e8eaed;--dim:#9aa0a6;--line:#2a2e35;--acc:#60a5fa;--warn:#fbbf24}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;display:flex}
#main{flex:1;padding:24px 28px;max-width:840px}
#side{width:400px;border-left:1px solid var(--line);padding:18px 20px;height:100vh;overflow:auto;
      font-size:12.5px;color:var(--dim);white-space:pre-wrap}
#bar{height:4px;background:var(--line);border-radius:2px;margin-bottom:18px}
#bar>div{height:100%;background:var(--acc);border-radius:2px;transition:width .15s}
.meta{color:var(--dim);font-size:12px;display:flex;gap:16px;margin-bottom:10px}
.box{padding:14px 18px;border-radius:6px;white-space:pre-wrap;margin-bottom:12px}
#msg{background:#171a1f;border:1px solid var(--line);border-left:3px solid #6b7280;font-size:16px}
#cand{background:#141b26;border:1px solid #24344a;border-left:3px solid var(--acc);font-size:18px}
h4{margin:16px 0 6px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--dim)}
.dim{margin-bottom:10px;padding:8px 10px;border-radius:5px;border:1px solid transparent}
.dim.active{border-color:var(--acc);background:#131a24}
.dim .lbl{font-size:13px;color:var(--fg);margin-bottom:4px}
.scale{display:flex;gap:6px}
.sc{padding:4px 12px;border:1px solid var(--line);border-radius:4px;cursor:pointer;font-size:13px}
.sc:hover{border-color:var(--acc)}
.sc.sel{background:#1d2b3d;border-color:var(--acc);color:var(--acc)}
kbd{background:#22262d;border:1px solid var(--line);border-bottom-width:2px;border-radius:4px;
    padding:1px 6px;font:12px ui-monospace,monospace}
button{background:#22262d;color:var(--fg);border:1px solid var(--line);border-radius:5px;
       padding:7px 14px;cursor:pointer;font-size:13px}
button:hover{border-color:var(--acc)}
#hud{position:fixed;bottom:0;left:0;right:400px;background:#0b0d10;border-top:1px solid var(--line);
     padding:9px 28px;font-size:12px;color:var(--dim);display:flex;gap:20px}
</style></head><body>
<div id="main">
  <div id="bar"><div style="width:0"></div></div>
  <div class="meta"><span id="pos"></span><span id="done"></span>
    <span id="nostore" hidden style="color:var(--warn)">no browser storage &mdash; auto-exporting every 15 ratings</span></div>
  <h4>customer wrote</h4>
  <div id="msg" class="box"></div>
  <h4>draft reply to grade</h4>
  <div id="cand" class="box"></div>
  <div id="dims"></div>
  <div style="margin:20px 0 60px;display:flex;gap:10px">
    <button onclick="prev()">&larr; back</button>
    <button onclick="next()">skip &rarr;</button>
    <button onclick="exportJSON()" style="border-color:var(--acc);color:var(--acc)">export JSON</button>
  </div>
</div>
<div id="side"><h4 style="margin-top:0">rubric</h4><div id="rubric"></div></div>
<div id="hud">
  <span><kbd>1</kbd>&ndash;<kbd>5</kbd> score the highlighted line</span>
  <span>usable: <kbd>0</kbd> no &middot; <kbd>1</kbd> yes</span>
  <span><kbd>&larr;</kbd><kbd>&rarr;</kbd> navigate</span>
</div>
<script>
const ITEMS = __ITEMS__, RUBRIC = __RUBRIC__;
const DIMS = ["grounded","actionable","safe","voice","usable"];
const LABELS = {grounded:"grounded in how the brand actually handles this",
                actionable:"moves the case forward",
                safe:"promises nothing it cannot keep",
                voice:"sounds like this brand",
                usable:"would you post this unedited?"};
const KEY = "reply_ratings_v1";
let STORAGE_OK = true;
function store(k,v){ try{ localStorage.setItem(k,v);}catch(e){ STORAGE_OK=false; } }
function loadS(k){ try{ return localStorage.getItem(k);}catch(e){ STORAGE_OK=false; return null; } }
let ratings = JSON.parse(loadS(KEY) || "{}");
let i = 0, d = 0, sinceBackup = 0;

function cur(){ return ITEMS[i]; }
function rec(){ const k = cur().rating_id; return ratings[k] || (ratings[k] = {rating_id:k, case_id:cur().case_id, system:cur().system}); }
function complete(r){ return DIMS.every(x => r && r[x] !== undefined); }
function save(){ store(KEY, JSON.stringify(ratings));
  if(!STORAGE_OK && ++sinceBackup >= 15){ sinceBackup = 0; exportJSON(true); } }

function render(){
  const c = cur(), r = ratings[c.rating_id] || {};
  const n = Object.values(ratings).filter(complete).length;
  document.querySelector("#bar>div").style.width = (100*n/ITEMS.length)+"%";
  document.getElementById("pos").textContent = `reply ${i+1} / ${ITEMS.length}`;
  document.getElementById("done").textContent = `${n} complete`;
  document.getElementById("nostore").hidden = STORAGE_OK;
  document.getElementById("msg").textContent = c.customer_opening;
  document.getElementById("cand").textContent = c.reply || "(empty reply)";
  document.getElementById("dims").innerHTML = DIMS.map((dim,n2)=>{
    const opts = dim==="usable" ? [0,1] : [1,2,3,4,5];
    return `<div class="dim ${n2===d?'active':''}"><div class="lbl">${dim} &mdash; ${LABELS[dim]}</div>
      <div class="scale">${opts.map(o=>
        `<div class="sc ${r[dim]===o?'sel':''}" onclick="setScore('${dim}',${o})">${o}</div>`).join("")}</div></div>`;
  }).join("");
  window.scrollTo(0,0);
}
function setScore(dim, val){
  const r = rec(); r[dim] = val; r.t = Date.now(); save();
  const at = DIMS.indexOf(dim);
  if(at === DIMS.length-1){ d = 0; render(); next(); }
  else { d = at+1; render(); }
}
function next(){ if(i<ITEMS.length-1){ i++; d=0; render(); } else { alert("End. Export when ready."); } }
function prev(){ if(i>0){ i--; d=0; render(); } }
document.addEventListener("keydown", e=>{
  if(e.metaKey||e.ctrlKey||e.altKey) return;
  const k = e.key;
  if(k==="ArrowRight"){ next(); return; } if(k==="ArrowLeft"){ prev(); return; }
  const dim = DIMS[d];
  if(dim==="usable" && /^[01]$/.test(k)){ setScore(dim, +k); return; }
  if(dim!=="usable" && /^[1-5]$/.test(k)){ setScore(dim, +k); }
});
function exportJSON(auto){
  const rows = ITEMS.map(c=>({...(ratings[c.rating_id]||{rating_id:c.rating_id,case_id:c.case_id,system:c.system})}));
  const blob = new Blob([rows.map(r=>JSON.stringify(r)).join("\n")], {type:"application/x-ndjson"});
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
  a.download = auto ? "reply_ratings_autosave.jsonl" : "reply_ratings.jsonl"; a.click();
}
document.getElementById("rubric").textContent = RUBRIC;
render();
</script></body></html>
"""


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default="hulu_support")
    ap.add_argument("--n-cases", type=int, default=14)
    ap.add_argument("--systems", nargs="*",
                    default=["agent", "keyword_knn", "majority"])
    args = ap.parse_args()

    golden = {r["case_id"]: r for r in read_jsonl(
        C.GOLDEN_DIR / f"golden_unlabelled_{args.brand}.jsonl")}
    preds = {s: {r["case_id"]: r for r in read_jsonl(PRED_DIR / f"{s}.jsonl")}
             for s in args.systems}
    missing = [s for s, p in preds.items() if not p]
    if missing:
        sys.exit(f"no predictions for {missing}; run scripts/05_run_systems.py first")

    shared = set(golden) & set.intersection(*(set(p) for p in preds.values()))
    shared = [cid for cid in shared if golden[cid]["slice"] == "random"]
    rng = random.Random(C.RANDOM_SEED + 1)
    cases = sorted(shared)
    rng.shuffle(cases)
    cases = cases[:args.n_cases]

    items = []
    for cid in cases:
        for s in args.systems:
            items.append({
                "rating_id": f"{cid}::{s}",
                "case_id": cid,
                "system": s,                      # kept in data, never shown in the UI
                "customer_opening": golden[cid]["customer_opening"],
                "reply": preds[s][cid]["reply"],
            })
    rng.shuffle(items)
    # System is needed to join back to judge verdicts, but must not reach the page.
    public = [{k: v for k, v in it.items() if k != "system"} | {"system": None}
              for it in items]

    (C.GOLDEN_DIR / "rating_plan.jsonl").write_text(
        "\n".join(json.dumps(it, ensure_ascii=False) for it in items), encoding="utf-8")
    html = (HTML.replace("__ITEMS__", json.dumps(public, ensure_ascii=False))
                .replace("__RUBRIC__", json.dumps(RUBRIC)))
    out = C.GOLDEN_DIR / "rate.html"
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out}  ({len(items)} replies over {len(cases)} cases, "
          f"{len(args.systems)} systems)")
    print(f"wrote {C.GOLDEN_DIR / 'rating_plan.jsonl'} (holds the system each reply came from)")


if __name__ == "__main__":
    main()
