# Hulu support agent: what it does, how well, and where the evidence is thin

## 1. Problem framing

### What "good" means for this brand

Hulu answers customers in public, on a channel where every reply is
screenshot-able. That sets the objective. The dominant cost is not a clumsy reply,
it is a confidently wrong one: a promised refund, an invented release date, a claim
to have inspected an account the agent cannot see. Those are reputational events. A
bland reply costs almost nothing.

So the target is not maximum automation:

> Never auto-send a reply that commits Hulu to something it cannot keep, and
> subject to that, handle as much volume as possible without a human.

That asymmetry is why escalation errors are reported as two separate numbers
throughout and never averaged. Auto-handling a case that needed a person is
customer-visible. Escalating one the agent could have handled costs an agent a
minute.

The second half of "good" is groundedness. Hulu's replies have a recognisable
shape: a short acknowledgement, then one concrete step or one diagnostic question,
under 280 characters. A reply that invents a plausible-sounding step is worse than
one reusing a step Hulu demonstrably uses, even when the invented one reads better.
Retrieval over the brand's own history is therefore not an optimisation, it is the
mechanism by which the reply is allowed to make claims at all.

### What I chose not to build

**Multi-turn dialogue.** The agent handles the opening message and drafts the
first reply. Hulu's public threads mostly end by moving to DM, so the multi-turn
public data is largely logistics rather than problem solving. Modelling it would be
modelling an artefact of the channel.

**Fine-tuning.** Retrieval plus an instruct model gets the same grounding with an
auditable provenance trail: for every reply I can name the past cases that informed
it. A fine-tune buries that in weights, and this assignment is about proving the
system works.

**Auto-sending.** The agent drafts and triages; a human posts. This changes what
"auto" means in the metrics: it means no human judgement needed on the content,
which is the decision an operator wants to automate first.

**Banking77.** Its 77 labels describe retail banking, a domain with almost no
overlap with streaming support. Validating against it would measure domain transfer
rather than performance on this task.

**A separate sentiment model.** Anger is a signal for escalation, but it is
already available inside the single call that reads the message. A second model
adds a failure surface for a signal the first can already report.

## 2. Method

Brand chosen by measured deflection rate. Threads rebuilt from the flat tweet dump
and split chronologically at 2017-11-17 into 11,091 retrievable history cases and
3,697 held out. Ten intents induced by reading the history split only. A golden set
of 200 held-out cases, 120 uniform-random and 80 keyword-probed. One structured
call per case produces intent, confidence, a reply grounded in retrieved
exemplars, and a proposed handling, after which policy code applies hard escalation
rules that can override the model. Reply quality is scored by a judge on a
different vendor's model, blind to which system wrote each reply. Full reasoning is
in `reports/DECISION_LOG.md`.

## 3. Results

All 200 evaluation items are hand-labelled by me. Headline numbers use the
120-item uniform-random slice only, since the boost slice does not reflect real
traffic. Intervals are 95% bootstrap.

### Intent and triage

| system | n | accuracy | 95% CI | macro F1 | esc. precision | esc. recall |
|---|---:|---:|---:|---:|---:|---:|
| majority class | 120 | 11.7% | 5.8–17.5 | 0.021 | 0.0% | 0.0% |
| keyword + copy nearest | 120 | 29.2% | 20.8–37.5 | 0.235 | 28.6% | 35.3% |
| **agent** | 120 | **49.2%** | 40.8–58.3 | **0.404** | 27.3% | 35.3% |

**The agent beats both baselines and the intervals do not overlap**, 49.2%
against 29.2% against 11.7%, with macro F1 roughly doubled against the simple
baseline. That ordering is solid.

**49.2% is a modest absolute result and should not be dressed up.** On a ten-class
problem it is well above chance and well above a keyword system, and it is still
wrong on half of real traffic.

**Escalation is poor in both directions.** Of the 22 cases the agent sent to a
human, 6 needed it. Of the 17 that needed a human, it caught 6. It both
over-escalates, 16 cases, and misses, 11 cases, which is the worst combination:
it wastes agent time without buying safety.

| intent | n | precision | recall | F1 |
|---|---:|---:|---:|---:|
| plans_billing | 29 | 81.0% | 58.6% | 0.680 |
| login_access | 11 | 53.8% | 63.6% | 0.583 |
| content_availability | 40 | 51.0% | 62.5% | 0.562 |
| product_feedback | 31 | 50.0% | 45.2% | 0.475 |
| ads_experience | 11 | 35.3% | 54.5% | 0.429 |
| playback_error | 18 | 28.2% | 61.1% | 0.386 |
| unactionable_or_churn | 18 | 33.3% | 22.2% | 0.267 |
| service_outage | 14 | 66.7% | 14.3% | 0.235 |
| app_device_problem | 27 | 27.3% | 11.1% | 0.158 |

**`playback_error` is a sink.** 28.2% precision against 61.1% recall means the
agent reaches for it constantly and is usually wrong. The two commonest confusions
in the whole set are `app_device_problem` read as `playback_error`, 7 cases, and
`service_outage` read as `playback_error`, 7 cases. Both are boundaries the
taxonomy wrote explicit rules for, and both rules failed.

**`service_outage` has the same shape as before:** decent precision, 66.7%,
terrible recall, 14.3%. The agent rarely commits to calling something an outage,
so the policy rule that escalates outages almost never fires.

### The headline my own evaluation nearly reported

Before hand-labelling, the reference labels were machine-generated by
`gemini-3.1-flash-lite`. Scored against that reference the agent looked far
better:

| reference used | agent intent accuracy |
|---|---:|
| machine-generated labels | **79.9%** |
| hand labels | **44.2%** |

The same predictions, the same 199 items, a 35.7-point difference purely from who
wrote the reference. The machine reference agrees with me on intent 44.7% of the
time, kappa 0.372, and on handling 65.3%, kappa 0.201. It escalated 41.2% of
messages where I escalated 12.6%.

**The mechanism is shared bias, and it is measurable.** On 80 of 199 items, 40%,
the agent and the machine reference made *the same* error relative to my label.
They agree on calling an outage a playback error, on calling a device problem a
playback error, on calling feedback a catalogue question. Two models built on
similar data make correlated mistakes, so scoring one against the other rewards
exactly the errors they share.

Had I not hand-labelled, this report would have led with 77.5% and a claim that
the agent nearly doubles the simple baseline. The real figure is 49.2%. That gap
is the single most useful thing I learned here.

### Reply quality

Scored blind by `gemini-3.5-flash-lite` against retrieved history, so these
numbers never touch the labels above.

| system | grounded | actionable | safe | voice | mean | postable |
|---|---:|---:|---:|---:|---:|---:|
| majority class | 2.56 | 3.80 | 4.92 | 3.34 | 3.65 | 90.0% |
| keyword + copy nearest | 3.20 | 3.24 | 4.72 | 4.36 | 3.88 | 28.0% |
| **agent** | **3.92** | 3.62 | **4.98** | **4.40** | **4.23** | 84.0% |

**The agent is not measurably more actionable than a one-line template**, 3.62
against 3.80 with overlapping intervals.

**Copying real human replies produces mostly unpostable text**, 28% postable,
despite the second-best voice score, because a reply written for another customer
carries their name and their link.

**Overlap with Hulu's real reply ranks the copy baseline first**, the predicted
failure of that metric and why it is reported only to be discounted.

These scores carry a heavy caveat, measured below: the judge does not agree with a
human beyond chance at the item level, so the absolute values mean little. The
ordering between systems is what survives.

### Does the judge agree with a human?

37 replies were rated by hand on the judge's own rubric, blind to which system
wrote each one. The brief asks for this evidence and it is the least flattering
measurement in the report.

| dimension | exact | within 1 | quadratic weighted kappa | human mean | judge mean |
|---|---:|---:|---:|---:|---:|
| grounded | 38% | 46% | +0.024 | 4.54 | 2.95 |
| actionable | 16% | 38% | +0.008 | 4.35 | 2.95 |
| safe | 16% | 41% | −0.100 | 3.51 | 4.89 |
| voice | 14% | 46% | −0.107 | 3.19 | 3.84 |
| postable | 68% | — | +0.018 | 0.92 | 0.70 |

**The judge does not agree with me beyond chance on any dimension.** Weighted
kappa is at or below zero throughout, and on two dimensions it is negative,
meaning the disagreement is worse than random. Agreement within one point never
reaches half the items. On a five-point scale that is close to no relationship.

**The disagreement is systematic rather than noisy, and it runs in opposite
directions per dimension.** The judge is 1.59 points harsher than me on
groundedness and 1.41 harsher on actionability, while being 1.38 points more
generous on safety and 0.65 on voice. The raw distributions show why: I marked 31
of 41 replies a 5 for groundedness while the judge split bimodally between 1 and 5,
and the judge called 39 of 41 replies perfectly safe while my modal score was 3.
We are not making noisy versions of the same judgement, we are applying different
standards.

**The one claim the report leans on survives.** Ranking systems by mean quality,
both raters put the agent first. We disagree on the order of the two baselines,
which the report does not rely on.

| system | n | human mean | judge mean |
|---|---:|---:|---:|
| agent | 10 | 4.05 | 4.33 |
| majority template | 14 | 3.88 | 3.07 |
| keyword + copy | 13 | 3.81 | 3.77 |

**What this costs the reply-quality section.** Every absolute number in it is now
unvalidated: a grounded score of 3.92 does not mean what a person would call 3.92.
The comparative ordering between systems, which is what the conclusions actually
use, holds under both raters. The retrieval ablation is scored by the same judge,
so its magnitudes inherit the same warning, though a 27-to-0 win count is hard to
explain away as miscalibration.

**Two caveats on this measurement itself.** It is one rater on 37 items, rated
quickly. And my grounded scores cluster hard at the top, 76% of them a 5, which
mechanically suppresses kappa regardless of how good the judge is. That excuse does
not cover safe and voice, where my scores were well spread and kappa still came out
negative.

### What retrieval contributes

Both arms on `qwen/qwen3.8-27b`, paired on 35 cases, differing only in whether
exemplars are present. A different model from the agent, because the agent model's
daily token allowance was exhausted; the direction transfers, the magnitude should
not.

| dimension | with | without | difference | 95% CI | wins / losses |
|---|---:|---:|---:|---:|---:|
| grounded | 4.66 | 2.31 | **+2.34** | +1.83 to +2.86 | 27 / 0 |
| voice | 4.77 | 3.09 | **+1.69** | +1.31 to +2.06 | 27 / 0 |
| actionable | 3.57 | 3.23 | +0.34 | −0.23 to +0.97 | 15 / 9 |
| postable | 0.66 | 0.86 | **−0.20** | −0.37 to −0.03 | 2 / 9 |

Groundedness and voice are where retrieval pays, 27 wins to 0 on both. It does
**not** make replies more actionable, agreeing with the cross-system table. And it
makes replies measurably **less postable**, because grounding in real history is
also how the `<URL>` placeholder gets copied in. The two arms agree on intent 89%
of the time, so retrieval informs the answer rather than the label.

## 4. Failure analysis

Rates over 200 agent replies, measured mechanically by
`scripts/10_failure_scan.py`. None needed gold labels, which is why they are the
most solid part of the evaluation.

**1. Leaked placeholder tokens, 22.3%.** The agent writes literal `<URL>` into
replies that would post broken.

> customer: episodes 2 and 3 of The Good Doctor aren't available????
> reply: Sorry to hear that! ...you can catch the most recent episode here: `<URL>`

*I caused this.* My preprocessing replaced every link with that token, so every
exemplar contains it and the model correctly infers Hulu's replies contain it. The
clearest case here of an evaluation artefact becoming a product defect, and the
largest contributor to unpostable output.

**2. Inconsistent addressing, 50% missing the @user prefix.** Half the replies open
without addressing anyone, which on Twitter means the reply is not directed at the
customer. *Hypothesis:* normalisation stripped real handles, so exemplars are split
between those opening with it and those where it fell mid-sentence. Repairable in
post-processing, since the handle is known at send time.

**3. Empathy opener on neutral messages, 31.1%.**

> customer: hi where is season 3 of Fargo I need it
> reply: Oh no! We don't have Season 3 of Fargo right now...

*Hypothesis:* the overwhelming majority of exemplars are complaints, so the
acknowledgement is learned unconditionally rather than as a response to something
going wrong.

**4. Confident answers with no supporting precedent, 15 replies.** The agent
reports which past cases it used. In 15 it reported none and answered anyway.

> customer: Glad I pay for @user and can't use it while I am overseas.
> intent=content_availability, confidence=0.92
> reply: Hulu is only available in the US. Try accessing it from a US-based connection.

The answer is correct, which is what makes it dangerous: the model is drawing on
world knowledge rather than retrieved history, and nothing distinguishes "grounded
and right" from "ungrounded and lucky". *This is a design gap.* An empty
`grounded_in` is a signal the policy layer already receives and ignores.

**5. My escalation policy conflates two billing cases.** Policy overrode the model
18 times, 14 on `plans_billing`. Most were right. This one was not:

> customer: I'm definitely making the switch. How much is Hulu per month?
> policy: escalate, reason account_or_payment_specific

A prospective customer asking a public pricing question, where the agent had
already drafted a good reply with a plans link. *Not fixed deliberately:* splitting
the intent would invalidate a golden set labelled against the current taxonomy.

## 5. What is misleading about my headline number

**49.2% is accuracy against one annotator, and that annotator designed the
taxonomy.** I wrote the label definitions, then applied them. Where a category is
badly drawn, my labels inherit the same flaw as the agent's prompt, and a shared
misreading cannot appear as disagreement. There is no second annotator, so there
is no inter-annotator agreement figure and therefore no estimate of the ceiling.
If two careful people would agree only 70% of the time on this taxonomy, then
49.2% sits much closer to the achievable limit than it looks; if they would agree
95%, it does not. I cannot tell you which, and that is the largest single gap in
this evaluation.

**Circumstantial evidence says the taxonomy is the problem, not only the model.**
The two commonest confusions are `app_device_problem` and `service_outage` both
collapsing into `playback_error`, and both are boundaries I wrote explicit rules
for. `app_device_problem` scores F1 0.158 against 27 real examples. When a
category with a written rule and adequate support fails that badly, the more
likely explanation is that the category does not carve the data at a real joint.

**The escalation labels encode a policy I invented.** I decided billing disputes
need a human and that a churn threat outranks the underlying issue. Hulu may well
handle both automatically in DMs. The triage numbers measure consistency with a
stated policy, not agreement with Hulu's real one.

**The judge does not agree with a human, and the reply-quality numbers inherit
that.** Weighted kappa is at or below zero on all four dimensions. The judge is
systematically harsher on groundedness and actionability and more generous on
safety and voice, which means its absolute scores cannot be read as a person's
would be. The system ordering survives, since both raters rank the agent first,
and that ordering is what the conclusions use. This was worth measuring precisely
because the result changes what the earlier table is allowed to claim.

**No outcome data, so "quality" means plausibility.** Nothing in this dataset says
whether a reply fixed the problem. A reply can score 5 across the rubric and solve
nothing.

**Temperature zero is not deterministic, and I can quantify it.** Two runs
overlapped and regenerated 31 cases, giving accidental repeat samples.

| repeated at temperature 0 | identical |
|---|---:|
| escalation decision | 100% |
| intent label | 94% |
| reply wording | 29% |

So an intent gap under about six points is inside the noise, on top of the
sampling intervals. The escalation decision never moved, which is the strongest
evidence here for putting that decision in policy code rather than in the prompt.

**The chronological split does not fully prevent leakage.** It stops retrieval
seeing the future, but the same complaints recur for months, so a held-out case
may have a near-identical predecessor. Realistic, since a deployed system would
have the same advantage, but it flatters groundedness relative to novel problems.

**120 items, and one class carries a fifth of the mass.** Read macro F1 when
comparing systems and the per-class table when asking whether a specific intent
works. `other` has a single example and its F1 of 0.000 means nothing.

**What is no longer misleading, and why it is worth saying.** An earlier draft of
this report reported 77.5%, measured against machine-generated reference labels.
That figure was wrong by 28 points, not because of a bug but because the reference
and the system under test shared their errors on 40% of items. The correction came
from hand-labelling, which is the one step that cannot be automated away. If there
is a single transferable lesson here, it is that an evaluation set produced by a
model related to the system being evaluated will flatter it, quietly, and by a
margin large enough to change every conclusion.

## 6. What I would do with one more week

1. **Rework the taxonomy, then relabel.** `app_device_problem` scores F1 0.158
   and `service_outage` 0.235, and both fail by collapsing into `playback_error`
   despite having written boundary rules. I would merge or redraw those three
   categories against the confusion matrix, then relabel. Chasing model accuracy
   against categories that do not carve the data is wasted effort.
2. **Get a second annotator on 60 items.** Without an inter-annotator figure
   there is no way to know whether 49.2% is near the ceiling or far from it, and
   that single number changes how every other result should be read.
3. **Escalate on empty `grounded_in`.** Two lines in `apply_policy`, and it closes
   failure mode 4, the one where the agent answers confidently with no precedent.
4. **Build an outcome proxy.** Follow each held-out thread past the first reply. A
   customer who thanks is weak evidence of resolution; one who restates the problem
   is weak evidence against. Noisy, but it moves reply evaluation from plausibility
   toward effect.
5. **Rewrite the judge rubric against the disagreement data.** The judge and I
   apply the scale in opposite directions on four dimensions, so the anchors are
   not doing their job. I would rewrite them using the cases we disagreed on as
   worked examples, then re-measure. After that, **evaluate retrieval on its own**,
   since a retrieval failure and a generation failure are currently
   indistinguishable from the outside. Right now a retrieval failure and a
   generation failure are indistinguishable from the outside. Hand-labelled
   relevance for 50 queries would give recall@k.
6. **Fix the placeholder leak at source**, resolving `<URL>` to the real Hulu help
   links present in the raw data, so grounded replies carry a link that works.
