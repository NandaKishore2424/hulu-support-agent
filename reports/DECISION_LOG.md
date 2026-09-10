# Decision log

The non-obvious choices, and why. Each one changes a number in the report.

### 1. Brand chosen by measured handoff rate, not by volume
The reply half of this project can only be evaluated for a brand that resolves
cases in public. My first metric counted only "DM us" and ranked AmazonHelp top
at a 0.7% deflection rate. Reading Amazon's actual replies showed it deflects by
pasting a web-form link instead. Counting channel-switch phrasing raised Amazon
to 12.1% and moved hulu_support, at 7.1%, to the front. **The first version of
the metric was wrong and the ranking it produced was wrong.**

### 2. Chronological split rather than random
Retrieval may only see cases from before the evaluation window. The same
complaint recurs daily on this account, so a random split would let the agent
retrieve a near-duplicate of the very case being scored and every reply-quality
number would be inflated. The boundary is 2017-11-17; the last 3,697 cases are
held out.

### 3. Taxonomy induced from the history split only
The label set was designed by reading 120 sampled openings from the history
split. The holdout was never read while designing it, so the taxonomy is not
fitted to the examples it is later scored on.

### 4. Ten intents, including two that exist for the triage decision
`unactionable_or_churn` and `service_outage` are small classes and would be
tempting to fold into their neighbours. They are kept separate because they are
the intents whose correct handling is *escalate*. Collapsing them would hide the
triage decision inside the classifier.

### 5. Boundary rules written down for the confusable pairs
`playback_error` versus `service_outage`, and `content_availability` versus
`plans_billing`, are genuinely ambiguous. Both pairs have an explicit written
rule in `taxonomy.py`, and the same text is shown to the human labeller and to
the model. Without a stated rule, disagreement on those pairs is noise rather
than a finding.

### 6. Golden set is 120 uniform random plus 80 keyword-probed
Rare intents appear two or three times in 120 messages, which cannot support a
per-class recall estimate. The boost slice fixes that. **Headline accuracy is
reported on the random slice only**, because the boost slice does not reflect
real traffic; the union is used for per-class breakdowns and both are labelled as
such in every table.

### 7. The boost slice is selected by hand-written regexes, never by the classifier
Choosing evaluation items with the model under test makes per-class numbers
circular. The probes are guesses about surface form, they are allowed to be
wrong, and whatever they surface is still labelled by a human.

### 8. The labeller is blind to slice membership and to the brand's real reply
Knowing an item was pulled by the `ads_experience` probe would nudge the label
toward that intent, so slice and probe are stripped from the labelling page.
Hulu's actual reply is hidden behind a reveal key, because reading it first
anchors the label to how Hulu happened to answer, which is the thing the agent is
scored against. Every reveal is recorded and the count is reported.

### 9. Escalation is decided by policy code, not by the prompt
The model proposes a handling decision; hard rules in `apply_policy` can override
it. Billing always goes to a human, so does an outage, so does anything below a
0.55 confidence floor. A policy that lives only inside a prompt cannot be unit
tested, cannot be audited, and changes silently when the model is swapped. Every
override is counted, and in smoke testing the model wanted to auto-handle a
reported outage that policy correctly escalated.

### 10. The retrieval pool excludes handoff replies
Roughly one Hulu reply in ten is a redirect to phone or chat. Leaving those in
the exemplar pool teaches the agent to deflect, which is the behaviour this brand
was chosen for *not* doing. 9,996 of 11,091 history cases survive the filter.

### 11. Hybrid retrieval, fused by rank rather than score
BM25 over words catches the tokens that decide the answer, since Roku and PS4
need different steps. Character 3-5 gram TF-IDF survives "buffring" and
"chromcast", which are out of vocabulary for word matching. Their scores are on
incomparable scales, so they are combined by reciprocal rank fusion, which uses
only rank position.

### 12. The judge is a different vendor from the generator
The agent writes on Groq with `openai/gpt-oss-120b`; the judge scores on Google's
`gemini-3.5-flash-lite`. A judge from the same family tends to prefer its own
phrasing. For the same reason the emergency failover model is deliberately *not*
the judge model, and any run served by it is counted and reported.

### 12a. The judge is pinned to one model, and a quota wall stops the run
`gemini-3.5-flash` was the judge until its free-tier daily request allowance ran
out part way through the first judging pass. That allowance is per model, so a
sibling model had an untouched one. Two things followed. The 16 verdicts the old
judge had produced were **deleted rather than mixed in**, because scores from two
different judges are not comparable and quietly blending them would corrupt every
reply-quality comparison in the report. And the judge is now forbidden from
failing over to another model, so hitting a wall raises instead of silently
swapping the measuring instrument. Every verdict records its `judge_model` and
both reporting scripts exit if they are handed a mixed set.

### 13. The judge never sees the brand's real reply for the case it is scoring
It sees the same retrieved exemplars the agent saw. Showing it the true reply
would make it score similarity to one particular answer rather than quality, and
would punish a correct alternative. Similarity to the real reply is computed
separately as `token_f1`, and distrusted, because Hulu's own reply is frequently
a handoff and scoring high against it can mean the agent learned to deflect.

### 14. Rubric anchors at 1, 3 and 5, and `usable` is separated from quality
Unanchored 1-to-5 scales drift to 4 for everything. Separating postability from
quality was immediately load-bearing: a reply that leaked the literal `<URL>`
placeholder scored 4.5 on advice quality and 0 on usable, which is exactly the
decomposition an operator needs.

### 15. Escalation errors are reported as two numbers and never averaged
Auto-handling something that needed a human is customer-visible. Escalating
something automatable costs a human a minute. An F1 that blends them hides the
one that matters.

### 16. Every LLM response is cached to disk and committed
Reproduction of the headline numbers needs no API key, no network and about a
minute. The live path is behind an explicit `--live` flag so an accidental re-run
cannot silently burn a day's quota.

### 17. The client throttles on tokens per minute, not requests
Groq's own headers report the binding limit as 8,000 tokens per minute against
1,000 requests per day, and one agent prompt is roughly 1,900 tokens. A fixed
sleep cannot pace that, because prompts vary in size by a factor of two. The
client keeps a rolling 60-second token budget and reconciles its reservation
against the provider's real usage after each call, which raised sustained
throughput from about one call a minute to over five.

### 18. Judge quality is validated at two levels
Per item, against human ratings, using quadratic weighted kappa so that an
off-by-one disagreement is not treated like an opposite verdict. Per system, by
checking whether the judge ranks the systems in the same order a human does.
Every claim in the report is a comparison between systems, so ranking agreement
is the property the report actually depends on.

### 20. The ablation runs on a third model, and both arms move together
Groq's daily token allowance for the agent's model was gone before the retrieval
ablation could run, and the sibling model's allowance went the same way. Rather
than drop the ablation, both arms were re-run on `qwen/qwen3.8-27b`, which still
had budget.

The alternative on offer was cheaper and wrong: compare the existing
gpt-oss-120b-with-retrieval predictions against a fresh no-retrieval run on a
smaller model. That would have confounded retrieval with model size and produced
a number that looks like an ablation and is not one. Re-running both arms costs
twice the calls and answers the actual question. What it gives up is any claim
about the magnitude on the deployed model, which the report states plainly.

### 21. A quota wall must propagate, not fail over
The failover path caught `QuotaExhausted` along with everything else and reported
"all providers failed", so a spent daily allowance produced one doomed call per
item instead of one clear stop. It now propagates. The bug is worth recording
because it hid its own cause: the run looked like hundreds of unrelated errors.

### 22. `reasoning_effort` is a gpt-oss parameter and is now scoped to gpt-oss
Sending it to Qwen made the model spend its entire output budget thinking and
return an empty completion, which Groq rejects as a malformed-JSON 400 rather
than anything mentioning reasoning or length. The failure looked nothing like its
cause, which is the second time in this project a provider reported a limit as a
different kind of error.

### 23. Duplicate predictions were kept long enough to learn from, then collapsed by rule
Two runs overlapped and regenerated 31 golden cases, because each computed its
"already done" set before the other had written. Rather than delete the duplicates
immediately, they were measured first: they are the only independent repeat
samples in the project, and they show that temperature zero is not deterministic
here. Intent labels agree 94% of the time across reruns, replies only 29%, and the
escalation decision 100%.

That last figure is the strongest argument in the project for deciding escalation
in code. The model's output moved on nearly three quarters of reruns and the
handling decision did not move once.

Deduplication keeps the first occurrence in file order. That rule is deterministic
and, more importantly, independent of which copy scores better, so it cannot be
used to quietly select favourable results. `06_metrics.py` now refuses to build
tables from a file containing duplicates rather than silently using whichever copy
was written last.

### 24. Labels are written to disk as they are entered, not held in the browser
The first labelling page kept an hour of work in `localStorage` until the user
pressed export. That put the most expensive artefact in the project behind one
button and a storage API that silently returns nothing in a private window, after
a site-data clear, or on a `file://` origin. It produced a 200-row export
containing no labels and no error, which is the worst possible failure: it looks
like a finished file.

`scripts/label_server.py` now serves the pages and accepts a POST after every
keystroke, writing straight to `data/golden/`. The file on disk is always current
and export is optional. The export button also refuses to write an empty file
without confirmation, and the page shows a live count of what is actually saved
rather than what the browser believes.

Verified end to end by driving the page in a browser and confirming the row
appeared on disk, rather than assuming the wiring worked.
