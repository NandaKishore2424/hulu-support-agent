# The golden evaluation set: how it was sampled and labelled

200 held-out cases, hand-labelled through a purpose-built page. This note covers
how they were chosen, how they were labelled, and what is wrong with the result.

## Where the items come from

Every item is drawn from the holdout split: 3,697 Hulu cases from after
2017-11-17. Nothing here was visible to retrieval, and nothing here was read
while the intent taxonomy was being designed.

## Two slices, sampled differently, for different jobs

**120 items, uniform random.** This is what Hulu's inbound traffic actually looks
like, so it is the only slice that can support a headline accuracy number. It is
also the reason the boost slice is needed: on 120 random messages the rarest
intents show up twice or three times, which cannot support a per-class recall
estimate.

**80 items, keyword-probed.** Ten hand-written regexes, one per intent, run over
the holdout to surface candidates for the rarer classes, sampled without
replacement and de-duplicated against the random slice.

Two rules keep this from becoming circular.

The probes are hand-written guesses about surface wording, **never the
classifier under test**. Selecting evaluation items with the system being
evaluated guarantees the test set is easy in exactly the way the system is good
at.

A probe only *surfaces* an item. It does not label it. Whatever the probe
believed is discarded, and the item is labelled by a human like any other, so a
probe firing on the wrong thing costs nothing but a wasted slot.

The consequence is that the boost slice is not representative of real traffic.
Headline accuracy is therefore reported on the random 120 only, and the union of
200 is used only for per-class breakdowns, with every table stating which.

## How the labelling page is built to reduce bias

**Slice membership is hidden.** The page never shows whether an item came from
the random draw or from a probe, and never shows which probe. Knowing that an
item was pulled by the ads probe would drag the label toward `ads_experience`.

**Hulu's real reply is hidden behind a key.** It can be revealed, because
sometimes the brand's answer is the only way to tell what the customer meant, but
it is a deliberate act rather than the default. Reading it first anchors the label
to whatever Hulu happened to do, and Hulu's reply is the thing the agent is being
scored against. **Every reveal is recorded and the count is reported in the
results.**

**The taxonomy is on screen at all times**, including the written boundary rules
for the two genuinely ambiguous pairs, so a disagreement on those pairs reflects a
hard case rather than a forgotten definition.

**Ambiguous items can be flagged** rather than forced into a class, and the flag
count is reported.

Each item receives an intent, a handling decision of auto or escalate, and where
escalated, a reason.

## How these labels were produced

All 200 items were labelled by hand by the author through `label.html`, which
hides slice membership and keeps Hulu's real reply behind a reveal key. The reply
was never revealed and no item was flagged ambiguous.

The set was first labelled by `gemini-3.1-flash-lite` when the human pass had not
been completed. Those machine labels are kept in `golden_labels_machine.jsonl`
rather than deleted, because comparing them against the hand labels turned out to
be the most informative measurement in the project: they agree on intent 44.7% of
the time, and on 80 of 199 items the machine reference and the agent made the same
error relative to the human. Scoring the agent against the machine reference gave
79.9%; against hand labels the same predictions give 44.2%.

## What is still wrong with this set

**One annotator, who also designed the taxonomy.** There is no inter-annotator
agreement figure and therefore no ceiling estimate. Where a category is badly
drawn, the labels inherit the same flaw as the agent's prompt and a shared
misreading cannot surface as disagreement.

**Evidence the taxonomy is part of the problem.** `app_device_problem` scores F1
0.158 against 27 real examples and `service_outage` 0.235, and both fail by
collapsing into `playback_error` despite having written boundary rules. A category
with a rule and adequate support failing that badly suggests the category does not
carve the data at a real joint.

**The escalation labels encode an invented policy.** Whether billing disputes need
a human is a decision I made, not something recoverable from the data. The triage
numbers measure consistency with a stated policy.

**200 items is small**, which is why bootstrap intervals accompany every headline
number.

## Files

| file | what it is |
|---|---|
| `golden_unlabelled_hulu_support.jsonl` | the 200 sampled cases with slice membership |
| `golden_labels.jsonl` | the 200 hand labels, written as they were entered |
| `golden_labels_machine.jsonl` | the earlier machine labels, kept for comparison |
| `spotcheck_labels.jsonl` | the 30-item blind sample labelled first |
| `label.html` | the labelling page, generated by `scripts/04_make_labeller.py` |
| `rate.html` | the reply-rating page used to validate the LLM judge |
| `rating_plan.jsonl` | maps each rated reply back to the system that wrote it |
