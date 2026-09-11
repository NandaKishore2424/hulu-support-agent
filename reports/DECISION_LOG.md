# Decision log

Fifteen non-obvious decisions, and why. Each changes a number in the report.

**1. Brand chosen by measured handoff rate, not by volume.** The reply half of this
project can only be evaluated for a brand that resolves cases in public. My first
metric counted only "DM us" and ranked AmazonHelp top at a 0.7% deflection rate.
Reading Amazon's actual replies showed it deflects by pasting a web-form link
instead. Counting channel-switch phrasing raised Amazon to 12.1% and moved
hulu_support, at 7.1%, to the front. The first version of the metric was wrong and
the ranking it produced was wrong.

**2. Chronological split rather than random.** The same complaint recurs daily on
this account, so a random split would let the agent retrieve a near-duplicate of
the case being scored and inflate every reply-quality number. The boundary is
2017-11-17; the last 3,697 cases are held out.

**3. Taxonomy induced from the history split only, with written boundary rules.**
The label set was designed by reading 120 sampled openings from history; the
holdout was never read while designing it. `playback_error` versus
`service_outage`, and `content_availability` versus `plans_billing`, are genuinely
ambiguous, so both pairs have an explicit rule shown identically to the labeller
and to the model. Without a stated rule, disagreement there is noise rather than a
finding.

**4. 120 uniform-random plus 80 keyword-probed, with headline numbers on the random
slice only.** Rare intents appear twice in 120 messages, which cannot support
per-class recall. The boost slice fixes that but does not reflect real traffic, so
mixing them would quietly change what accuracy means. The probes are hand-written
regexes, never the classifier under test, because choosing evaluation items with
the model being evaluated is circular.

**5. The labelling page hides slice membership and the brand's real reply.**
Knowing an item came from the `ads_experience` probe would nudge the label toward
that intent. Hulu's actual reply sits behind a reveal key because reading it first
anchors the label to how Hulu happened to answer, which is the thing the agent is
scored against. Reveals are counted and reported.

**6. Escalation is decided by policy code, not by the prompt.** The model proposes;
hard rules in `apply_policy` can override it. A policy living only inside a prompt
cannot be unit tested, cannot be audited, and changes silently when the model is
swapped. Evidence it was right: across 31 accidental repeat runs at temperature
zero, reply wording changed 71% of the time and the handling decision never
changed.

**7. The retrieval pool excludes handoff replies.** Roughly one Hulu reply in ten
redirects to phone or chat. Leaving those in teaches the agent to deflect, the
behaviour this brand was chosen for not doing. 9,996 of 11,091 cases survive.

**8. Hybrid retrieval, fused by rank rather than score.** BM25 over words catches
the tokens that decide the answer, since Roku and PS4 need different steps.
Character 3-5 gram TF-IDF survives "buffring" and "chromcast". Their scores are on
incomparable scales, so they combine by reciprocal rank fusion.

**9. The judge is a different vendor, pinned to one model, and never sees the real
reply.** A judge from the generator's family prefers its own phrasing. It sees the
same exemplars the agent saw, not the case's true answer, because otherwise it
would score similarity to one response and punish a correct alternative. When
`gemini-3.5-flash` exhausted its daily allowance mid-run, its 16 verdicts were
deleted rather than mixed with the replacement's: scores from two judges are not
comparable. Every verdict records its model and the scripts refuse a mixed set.

**10. The rubric is anchored at 1, 3 and 5, postability is separate from quality,
and the whole thing was then checked against a human.** Unanchored scales drift to
4 for everything. Separating postability was immediately load-bearing: a reply
leaking the `<URL>` placeholder scored 4.5 on advice and 0 on postable, exactly the
decomposition an operator needs.

Checking the judge against 37 hand-rated replies showed the anchors did not do
their main job. Weighted kappa is at or below zero on every dimension, and the
judge runs about 1.5 points harsher than me on groundedness and 1.4 more generous
on safety. Both of us still rank the agent first, so the comparative claim holds,
but no absolute reply-quality number in this report is validated. Measuring this
cost the report a section of confidence and is the main reason to trust the rest of
it.

**11. Escalation errors are two numbers, never averaged.** Auto-handling something
that needed a human is customer-visible. Escalating something automatable costs a
minute. An F1 blending them hides the one that matters.

**12. Every response is cached and committed, and the client throttles on measured
limits.** Reproduction needs no API key and takes a second. Groq's binding limit is
8,000 tokens per minute against a 200,000-per-day ceiling that appears in no
response header and surfaces only inside a 429 body; Gemini's is requests per
minute, per model. The client keeps rolling per-provider budgets for both and
reconciles reservations against real usage, which took throughput from one call a
minute to over five. A daily cap raises a distinct error that stops the run instead
of retrying into silence.

**13. The ablation runs both arms on a third model.** The agent's model and its
sibling had both exhausted their daily allowances. Reusing the existing
gpt-oss-120b predictions as the with-retrieval arm would have confounded retrieval
with model size and produced something that looks like an ablation and is not.
Re-running both arms costs twice the calls and answers the actual question; what it
gives up is any claim about magnitude on the deployed model.

**14. Duplicate predictions were measured before being collapsed.** Two runs
overlapped and regenerated 31 cases. Rather than delete them, they were used as the
only repeat samples in the project, showing that temperature zero is not
deterministic here: intent agrees 94% across reruns, replies 29%, handling 100%.
Deduplication then keeps the first occurrence in file order, a rule independent of
which copy scores better so it cannot be used to select favourable results.

**15. The set was hand-labelled in the end, and the machine labels were kept as
evidence.** An earlier version used 199 reference labels from
`gemini-3.1-flash-lite`. All 200 were then labelled by hand, and the machine
labels were archived rather than deleted.

That turned out to be the most valuable decision in the project. The two
references agree on intent 44.7% of the time. Scored against the machine
reference the agent gets 79.9%; against hand labels, on identical predictions, it
gets 44.2%. The mechanism is measurable rather than speculative: on 80 of 199
items the agent and the machine reference made the same error relative to the
human. Two models built on similar data make correlated mistakes, so scoring one
against the other rewards precisely the errors they share.

Reporting both numbers costs the headline 28 points. It is also the only part of
this evaluation that generalises beyond this dataset.
