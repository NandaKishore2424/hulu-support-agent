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

### How far the reference labels track a person

The reference labels are machine-generated. 30 items were then hand-labelled blind
as validation. This is the only measurement of whether the reference means
anything, and it should be read before anything else.

| comparison | agreement | Cohen's kappa |
|---|---:|---:|
| intent | 45% | +0.357 |
| handling (auto vs escalate) | 79% | +0.563 |

**The intent reference is weak.** A human and the reference labeller pick the same
intent on fewer than half of messages, so agreeing closely with that reference does
not establish correctness. The handling reference holds up better: 79%, with
escalate rates of 34% human against 41% machine, so the triage findings rest on
firmer ground than the intent figures.

**The disagreements cluster rather than scatter.** On those 29 items the human used
`product_feedback` ten times where the machine used it five, spreading the
difference across `content_availability`, `playback_error` and `other`. One
category absorbing a third of a human's labels points at a definition problem, and
it independently corroborates a weak boundary already visible in the confusion
matrix below.

With one rater on 29 items there is no way to establish which side is closer to
correct. 45% is equally consistent with a poor reference, a rater applying the
taxonomy loosely, or genuinely overlapping categories.

### Intent and triage

Random slice only, since the boost slice does not reflect real traffic. Intervals
are 95% bootstrap.

| system | n | agreement | 95% CI | macro F1 | esc. precision | esc. recall |
|---|---:|---:|---:|---:|---:|---:|
| majority class | 120 | 20.8% | 14.2–28.3 | 0.034 | 0.0% | 0.0% |
| keyword + copy nearest | 120 | 40.0% | 30.8–49.2 | 0.364 | 61.9% | 28.9% |
| **agent** | 120 | **77.5%** | 70.0–85.0 | **0.707** | 72.7% | 35.6% |

**The agent clears both baselines by a margin no noise explains**, with intervals
nowhere near touching and macro F1 roughly doubled against the simple baseline.
Read as consistency with one labeller, not accuracy.

**Escalation recall of 35.6% is the worst result here.** The agent auto-handles
nearly two thirds of what should reach a human, against an objective that puts
safety first. The per-class table shows why, and it is not the policy layer's
fault.

| intent | n | precision | recall | F1 |
|---|---:|---:|---:|---:|
| ads_experience | 17 | 100.0% | 100.0% | 1.000 |
| login_access | 13 | 100.0% | 100.0% | 1.000 |
| plans_billing | 20 | 90.5% | 95.0% | 0.927 |
| content_availability | 42 | 79.6% | 92.9% | 0.857 |
| playback_error | 44 | 84.6% | 75.0% | 0.795 |
| product_feedback | 28 | 78.6% | 78.6% | 0.786 |
| unactionable_or_churn | 8 | 50.0% | 75.0% | 0.600 |
| other | 8 | 57.1% | 50.0% | 0.533 |
| **service_outage** | 11 | 100.0% | **27.3%** | 0.429 |
| app_device_problem | 9 | 36.4% | 44.4% | 0.400 |

**Triage fails because classification fails first.** Policy escalates
`service_outage` unconditionally, so it can only fire when the classifier says
`service_outage`, and it says so for 3 of 11 cases. The commonest confusion in the
set is an outage read as an ordinary playback error, precisely the boundary the
taxonomy wrote a rule for. `service_outage` has perfect precision and terrible
recall: when the agent commits, it is right; it almost never commits.

### Reply quality

Scored blind by `gemini-3.5-flash-lite` against retrieved history, so these
numbers do not depend on the labels above.

| system | grounded | actionable | safe | voice | mean | postable |
|---|---:|---:|---:|---:|---:|---:|
| majority class | 2.56 | 3.80 | 4.92 | 3.34 | 3.65 | 90.0% |
| keyword + copy nearest | 3.20 | 3.24 | 4.72 | 4.36 | 3.88 | 28.0% |
| **agent** | **3.92** | 3.62 | **4.98** | **4.40** | **4.23** | 84.0% |

**The agent is not measurably more actionable than a one-line template**, 3.62
against 3.80 with overlapping intervals. The template asks what device you are
using, which is useful on almost any support message.

**Copying real human replies produces mostly unpostable text**, 28% postable,
despite the second-best voice score, because a reply written for another customer
carries their name and their link.

**Overlap with Hulu's real reply ranks the copy baseline first**, which is the
predicted failure of that metric and why it is reported only to be discounted.

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
**not** make replies more actionable, agreeing with the cross-system table, so two
independent measurements say the same thing. And it makes replies measurably
**less postable**, because grounding in real history is also how the `<URL>`
placeholder gets copied in. The two arms agree on intent 89% of the time, so
retrieval informs the answer rather than the label.

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

**The intent headline does not survive its own validation.** The agent agrees with
the reference 77.5% of the time; the reference agrees with a human 45% of the time.
High agreement with a weak reference is not evidence of correctness. This was only
discoverable because the spot check was run; without it the 77.5% would have looked
like a result. The handling figures, at 79% reference-to-human agreement, are on
much better footing, which means the report's worst finding is also its most
trustworthy one.

**The set is not hand-labelled as the brief asks.** 199 of 200 reference labels are
machine-generated; 30 were hand-labelled as a validation sample. Both the labeller
and the agent read the same taxonomy text, so a flaw in that text, and section 4
identifies one, cannot surface as disagreement.

**No judge-versus-human evidence exists.** The reply-rating pass was not completed.
The judge's rubric, vendor independence and blindness to system identity are all in
place, and its discrimination probes behave correctly, but nothing anchors it to a
person. That deliverable is absent rather than weak.

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

So an intent gap under about six points is inside the noise, on top of the sampling
intervals. And the escalation decision never moved, which is the strongest evidence
here for putting that decision in policy code rather than in the prompt.

**The chronological split does not fully prevent leakage.** It stops retrieval
seeing the future, but the same complaints recur for months, so a held-out case may
have a near-identical predecessor. Realistic, since a deployed system would have
the same advantage, but it flatters groundedness relative to novel problems.

**120 items, and accuracy dominated by one class.** Read macro F1 when comparing
systems and the per-class table when asking whether a specific intent works.

## 6. What I would do with one more week

1. **Fix the taxonomy before labelling anything else.** Human-to-reference
   agreement is 45% and the disagreements pile on one boundary: feedback about a
   working product versus a report that something is broken. Relabelling against
   definitions two careful raters cannot apply consistently buys a more expensive
   version of the same problem. Tighten `product_feedback`, `app_device_problem`
   and `content_availability` against the 16 recorded disagreements, then
   hand-label the full set, then rerun everything.
2. **Escalate on empty `grounded_in`.** Two lines in `apply_policy`, and it closes
   failure mode 4, the one where the agent answers confidently with no precedent.
3. **Build an outcome proxy.** Follow each held-out thread past the first reply. A
   customer who thanks is weak evidence of resolution; one who restates the problem
   is weak evidence against. Noisy, but it moves reply evaluation from plausibility
   toward effect.
4. **Evaluate retrieval on its own.** Right now a retrieval failure and a
   generation failure are indistinguishable from the outside. Hand-labelled
   relevance for 50 queries would give recall@k.
5. **Fix the placeholder leak at source**, resolving `<URL>` to the real Hulu help
   links present in the raw data, so grounded replies carry a link that works.
