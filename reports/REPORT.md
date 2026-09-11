# Hulu support agent: what it does, how well, and where the evidence is thin

## 1. Problem framing

### What "good" means for this brand

Hulu answers customers in public, on a channel where every reply is screenshot-
able. That single fact sets the objective. The dominant cost is not a slightly
clumsy reply, it is a confidently wrong one: a promised refund the brand will not
honour, an invented release date, a claim to have inspected an account the agent
cannot see. Those are reputational events. A reply that is merely bland costs
almost nothing.

So the target is not maximum automation. It is:

> Never auto-send a reply that commits Hulu to something it cannot keep, and
> subject to that, handle as much of the volume as possible without a human.

That asymmetry is why escalation errors are reported as two separate numbers
throughout, never averaged into one score. Auto-handling a case that needed a
person is a customer-visible failure. Escalating a case the agent could have
handled costs an agent one minute of attention. A blended F1 hides the one that
matters.

The second half of "good" is groundedness. Hulu's replies have a recognisable
shape: a short warm acknowledgement, then exactly one concrete step or one
diagnostic question, under 280 characters. A reply that invents a plausible-
sounding troubleshooting step is worse than one that reuses a step Hulu
demonstrably uses, even when the invented step reads better. Retrieval over the
brand's own history is therefore not a performance optimisation, it is the
mechanism by which the reply is allowed to make claims at all.

### What I chose not to build

Each of these was a deliberate cut, not an oversight.

**Multi-turn dialogue management.** The agent handles the opening message and
drafts the first reply. Hulu's public threads mostly end with the conversation
moving to DM, so the multi-turn public data that exists is largely logistics
rather than problem solving. Building a dialogue manager on top of it would be
modelling an artefact of the channel.

**Fine-tuning.** With 11,091 historical cases a fine-tune is feasible, but
retrieval plus a strong instruct model gets the same grounding with an auditable
provenance trail: for every reply I can name the past cases that informed it. A
fine-tune buries that in weights, and the assignment is about proving the system
works.

**Auto-sending.** The agent drafts and triages; a human posts. This is not
timidity, it changes what "auto" means in the metrics. "Auto" here means "no
human judgement needed on the content", which is the decision an operator
actually wants to automate first.

**Banking77.** The assignment offers it for intent work and I declined it.
Its 77 labels describe retail banking operations, a domain with almost no overlap
with streaming-service support. Transferring that taxonomy would import
distinctions Hulu's traffic does not contain, and validating my classifier
against it would measure domain transfer rather than performance on the task.
The honest use would have been to calibrate a classifier on a labelled set to
sanity-check my pipeline, which is worth less than spending the same hours
labelling Hulu data by hand.

**A separate urgency or sentiment model.** Anger is a signal for escalation, but
it is already available inside the single call that reads the message. A second
model would add a failure surface and another thing to evaluate for a signal the
first model can already report.

**Production concerns.** No queue integration, no auth, no serving layer, no
retry semantics beyond what the offline pipeline needs. The deliverable is a
measured system, not a deployed one.

## 2. Method

The pipeline, and the reasoning behind each step, is in `reports/DECISION_LOG.md`.
In brief:

Brand chosen by measured deflection rate. Threads rebuilt from the flat tweet
dump and split chronologically at 2017-11-17 into 11,091 retrievable history
cases and 3,697 held-out cases. Ten intents induced by reading the history split
only. A golden set of 200 held-out cases sampled as 120 uniform-random plus 80
keyword-probed, with reference labels from a third model rather than from a
person; the labelling interface built for the human pass is in the repository and
was used for one item before the pass was abandoned. One structured model call per case produces intent, confidence, a
reply grounded in retrieved exemplars, and a proposed handling decision, after
which policy code applies hard escalation rules that can override the model.
Reply quality is scored by an LLM judge running on a different vendor's model,
blind to which system wrote each reply, and that judge is itself validated
against human ratings.

## 3. Results

### Reply quality, and why this table stands on its own

Reply quality does not depend on the intent labels at all: the judge scores a
draft against retrieved history, not against a gold class. So this table is
complete and final even where the classification numbers are not.

Judged by `gemini-3.5-flash-lite` on a shared subset of random-slice cases, blind
to which system wrote each reply. Ranges are bootstrap 95% half-widths.

| system | grounded | actionable | safe | voice | mean | postable | overlap with real reply |
|---|---:|---:|---:|---:|---:|---:|---:|
| majority template | 2.56 ±0.35 | 3.80 ±0.21 | 4.92 ±0.10 | 3.34 ±0.28 | 3.65 | 90.0% | 0.179 |
| keyword + copy nearest | 3.20 ±0.40 | 3.24 ±0.31 | 4.72 ±0.22 | 4.36 ±0.23 | 3.88 | 28.0% | 0.223 |
| **agent** | **3.90 ±0.31** | 3.66 ±0.32 | **4.98 ±0.03** | **4.41 ±0.20** | **4.24** | 83.5% | 0.210 |

Four things to take from it, including two that do not flatter the agent.

**Retrieval works, and groundedness is where it shows.** The agent scores 3.90 on
groundedness against 3.20 for a system that copies a real Hulu reply verbatim and
2.56 for a fixed template. Those intervals do not overlap, so this is a real
difference rather than noise. This is the one claim in the report I would defend
without qualification.

**Safety is effectively solved on this metric, at 4.98 with an interval of
±0.03.** Given that the stated objective puts safety above everything else, that
matters. It is also the number I trust least as a predictor of production
behaviour, because the judge is checking for promises in the text and cannot know
whether a troubleshooting step is actually correct.

**The agent is not measurably more actionable than a hand-written generic
template.** 3.66 ±0.32 against 3.80 ±0.21. The template asks "what device are you
using?", which is a genuinely useful question on almost any support message. A
reader who only saw the mean quality column would conclude the agent is
comprehensively better; on the dimension that decides whether the customer's
problem moves forward, it is not distinguishable from one sentence someone wrote
once.

**Copying real human replies produces mostly unpostable text: 28% postable.** The
copy baseline has the second-best voice score, which makes sense because it *is*
Hulu's voice, and it still fails, because a reply written for a different customer
carries their name and a link resolved for their problem. It is a useful reminder
that "sounds right" and "can be sent" are different properties.

**Overlap with Hulu's real reply ranks the systems wrongly**, putting the copy
baseline first. That is the predicted failure of the metric and the reason it is
reported here only to be discounted. See section 5.

### What retrieval actually contributes

The tables above compare different systems. This one compares the same system
with one thing removed, which is the only way to attribute the gain to retrieval
rather than to the model.

Both arms run on `qwen/qwen3.8-27b`, paired on the same 35 random-slice cases,
same prompt, same temperature. They differ in exactly one respect: whether the
prompt carries retrieved exemplars. The model is not the one the agent deploys
on, because that model's daily token allowance was spent; the honest reading is
"grounding changes what this model writes", not "by this much for the deployed
agent". The wins column counts cases where the retrieval arm scored strictly
higher, then strictly lower.

| dimension | with retrieval | without | difference | 95% CI | wins / losses |
|---|---:|---:|---:|---:|---:|
| grounded | 4.66 | 2.31 | **+2.34** | +1.83 to +2.86 | 27 / 0 |
| voice | 4.77 | 3.09 | **+1.69** | +1.31 to +2.06 | 27 / 0 |
| actionable | 3.57 | 3.23 | +0.34 | −0.23 to +0.97 | 15 / 9 |
| safe | 4.89 | 4.71 | +0.17 | +0.00 to +0.46 | 2 / 0 |
| postable | 0.66 | 0.86 | **−0.20** | −0.37 to −0.03 | 2 / 9 |
| mean quality | 4.47 | 3.34 | **+1.14** | +0.90 to +1.36 | |

**Groundedness and voice are where retrieval pays, and it is not close.** 27 wins
against 0 losses on both, with intervals nowhere near zero. Without exemplars the
model writes generic support prose; with them it writes Hulu's. This is the
strongest single result in the report.

**Retrieval does not make replies more actionable.** +0.34 with an interval that
crosses zero, and it loses on 9 of 35 cases. This agrees with the cross-system
table, where the agent could not be separated from a hand-written template on the
same dimension. Two independent measurements now say the same thing, so I believe
it: retrieval teaches the model what this brand sounds like and what it has done
before, not how to solve a problem.

**Retrieval makes replies measurably less postable, and that is my fault.** The
one dimension where grounding actively hurts, −0.20 with an interval clear of
zero, losing 9 cases to 2. The mechanism is the `<URL>` placeholder from failure
mode 1: every exemplar carries it, so grounding a reply in real history is also
how the placeholder gets copied in. This quantifies the cost of a preprocessing
decision I made in the first hour, and it is the clearest argument in the project
for fixing it at the source rather than papering over it downstream.

**Retrieval barely moves classification.** The two arms agree on intent 89% of the
time, which is what I would expect: the intent is legible from the customer's own
words, and past cases mostly inform the answer rather than the label.

Also worth noting: with exemplars available the model cited at least one on 100%
of these cases, against the 15 ungrounded auto-answers in failure mode 4 on the
larger run.

### Classification and triage

**These are not accuracy figures. Read section 5 first.** The evaluation set was
meant to be hand-labelled and was not; the reference labels come from
`gemini-3.1-flash-lite`. Every number below measures agreement between the agent
and another model, not correctness. The word accuracy is used only because it
names the arithmetic.

Headline row is the random slice, which is the only one that reflects real
traffic. Intervals are 95% bootstrap.

| system | n | agreement | 95% CI | macro F1 | escalation precision | escalation recall |
|---|---:|---:|---:|---:|---:|---:|
| majority class | 120 | 20.8% | 14.2–28.3 | 0.034 | 0.0% | 0.0% |
| keyword + copy nearest | 120 | 40.0% | 30.8–49.2 | 0.364 | 61.9% | 28.9% |
| **agent** | 120 | **77.5%** | 70.0–85.0 | **0.707** | 72.7% | 35.6% |

**The agent clears both baselines on intent by a margin no amount of noise
explains.** 77.5% against 40.0%, with intervals nowhere near touching, and macro
F1 roughly doubled. Against the trivial floor it is more than three times better.
Even allowing for the six-point run-to-run instability measured in section 5, this
gap is real.

**Escalation recall is the serious failure, at 35.6%.** Of the cases the
reference says need a human, the agent auto-handles nearly two thirds. Set against
the objective stated in section 1, never auto-send something that commits Hulu to
what it cannot keep, that is the single worst result in the report and it would
block deployment on its own.

The per-class table explains the mechanism, and it is not the policy layer's
fault:

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

**Escalation fails because classification fails first.** The policy rules escalate
`service_outage` unconditionally, so they can only fire when the classifier says
`service_outage`, and it says so for 3 of 11 real cases. The top confusion in the
whole set is `service_outage` misread as `playback_error`, which is precisely the
boundary the taxonomy has a written rule for. When one customer says their stream
froze and another says Hulu is down for everyone, the model hears the same
complaint. Everything downstream inherits that.

Note the shape of the two failing classes. `service_outage` has perfect precision
and terrible recall: when the agent commits to calling something an outage it is
right every time, it simply almost never commits. `app_device_problem` fails in
both directions and is genuinely tangled with `product_feedback`, which is the
other boundary the taxonomy tried to pin down and evidently did not pin down well
enough.

## 4. Failure analysis

Rates are over 163 agent replies, measured mechanically by
`scripts/10_failure_scan.py`. None of these needed the gold labels, which is why
they are the most solid part of the evaluation.

### 1. Leaked placeholder tokens, 22.3% of replies

The agent writes the literal string `<URL>` into replies that would post broken.

> customer: @user episodes 2 and 3 of The Good Doctor aren't available????
> reply: Sorry to hear that! If you haven't already, you can catch the most recent episode here: `<URL>` Enjoy!

**Hypothesis: I caused this.** My own preprocessing replaced every link with
`<URL>`, so every retrieved exemplar contains it, and the model correctly infers
that Hulu replies contain that token. It is imitating the data faithfully. This is
the clearest case in the project of an evaluation artefact becoming a product
defect, and it is the single largest contributor to the 16.5% of agent replies
that are unpostable.

### 2. Inconsistent addressing, 50% of replies missing the @user prefix

Half the replies open without addressing anyone, which on Twitter means the reply
is not directed at the customer.

**Hypothesis:** normalisation stripped real handles into `@user`, so exemplars are
split between those that open with it and those where it fell mid-sentence. The
model has no consistent pattern to copy. Unlike the placeholder leak this one is
fully repairable in post-processing, since the correct handle is known at send
time.

### 3. Empathy opener on messages with nothing to apologise for, 31.1%

> customer: @user hi where is season 3 of Fargo I need it
> reply: Oh no! We don't have Season 3 of Fargo right now, but we'll pass your request along.

**Hypothesis:** the overwhelming majority of exemplars are complaints, so the
acknowledgement is learned as an unconditional opener rather than a response to
something going wrong. It is a small tonal error but it is the kind that makes a
support account sound automated, which is the specific impression the brand voice
work was meant to avoid.

### 4. Confident answers with no supporting precedent, 15 replies auto-handled

The agent reports which past cases it used. In 15 cases it reported none and still
answered, with high confidence.

> customer: Glad I pay for @user and can't use it while I am overseas. Oh well, lost a customer!
> intent=content_availability, confidence=0.92
> reply: Sorry to hear that! Hulu is only available in the US. Try accessing it from a US-based connection or device.

The answer happens to be correct, which is what makes it the most dangerous
failure mode here: the model is drawing on world knowledge about Hulu rather than
on this brand's retrieved history, and nothing in the current design distinguishes
"grounded and right" from "ungrounded and right" from "ungrounded and wrong".

**This is a design gap, not a model error.** An empty `grounded_in` is a signal
the policy layer already receives and ignores. It should escalate, and does not.

### 5. My own escalation policy conflates two different billing cases

Policy overrode the model 18 times, 14 of them on `plans_billing`. Most were
correct. This one was not:

> customer: I'm definitely making the switch. How much is Hulu per month?
> policy: escalate, reason account_or_payment_specific

That is a prospective customer asking a public pricing question, and the agent had
already drafted a good reply with a link to the plans page. My taxonomy puts
general pricing questions and account-specific payment disputes in one intent, and
my policy escalates the whole intent.

**I have not fixed it, deliberately.** Splitting the intent now would invalidate
the hand-labelled golden set, which was labelled against the current taxonomy.
Changing the label space after seeing which classes cause errors is how evaluation
sets get quietly fitted to the system. The fix belongs in the next iteration, with
relabelling, and it is item 4 in section 6.

## 5. What is misleading about my headline number

This section is mandatory in the brief and it is the one I would read first.

**The evaluation set is not hand-labelled, and this invalidates more than it
first appears.** The brief asks for 150 to 250 examples labelled by hand. The
human pass was started and abandoned after one item. The remaining 199 reference
labels were produced by `gemini-3.1-flash-lite`.

Three consequences, in order of severity.

*There is no ground truth anywhere in this project.* The agent is a model, the
reply judge is a model, and now the reference labels are a model. Nothing in the
pipeline has been checked by a person. The 77.5% headline is agreement between
two language models, and two models can agree confidently and both be wrong in the
same direction with nothing here able to detect it. Calling that number accuracy
is a convenience of arithmetic, not a claim about correctness.

*The escalation numbers are worse affected than the intent numbers.* What counts
as needing a human is a policy judgement, not a fact recoverable from the text.
The reference labeller marked 41.5% of messages as needing escalation, which is
high, and there is no way to tell whether that reflects the policy as written or
the labeller being cautious. The agent's 35.6% escalation recall is measured
against that, so the headline failure could be partly an artefact of a
disagreement between two models about where the line sits.

*The labeller read the same instructions the agent reads.* Both were given the
taxonomy and boundary rules verbatim from `taxonomy.py`. A flaw in that text, and
section 4 identifies at least one, cannot show up as disagreement, because both
sides inherit it.

What limits the damage, and it is limited rather than removed: the labeller is a
different model family from the agent, and deliberately not the model used as the
reply judge, so the agreement measured is at least between independent systems
rather than a model checking itself. `scripts/14_make_spotcheck.py` builds a short
human validation pass; it has not been completed, so there is no figure for how
far these labels track a person's judgement.

**The judge-versus-human agreement evidence the brief asks for does not exist.**
The rating pass that would have produced it was not completed. The judge's rubric,
its blindness to system identity and the discrimination probes in `judge.py` are
all still in place, and the ablation and cross-system comparisons it produced are
internally consistent, but there is no human anchor for any of it. This is a
deliverable that is missing, not one that was attempted and came out weak.

**The headline slice is 120 items.** The bootstrap intervals are reported for
exactly this reason. On 120 items a 5-point difference in accuracy is usually
indistinguishable from noise, so any comparison whose intervals overlap should be
read as "no measured difference", not as a win.

**The escalation labels are my policy, not Hulu's.** I decided that billing
disputes need a human. Hulu may well auto-handle them through a DM flow. The
triage numbers measure agreement with a policy I invented and then implemented,
which is close to grading my own homework. What they do legitimately show is
whether the system implements a stated policy consistently.

**No outcome data exists, so "quality" means plausibility.** Nothing in this
dataset says whether a reply fixed the customer's problem. The judge scores
whether advice is grounded, actionable, safe and on-voice. A reply can score 5
across the board and still not solve anything. Every reply-quality number in this
report is a measure of well-formedness, not of resolution.

**Similarity to Hulu's real reply is a trap and is reported only to be
dismissed.** Roughly one Hulu reply in ten is a redirect to phone or chat. A
system that learned to deflect would score *well* on overlap with the real reply.
Where token overlap appears in the tables it is context, never evidence.

**The chronological split does not fully prevent leakage.** It stops the agent
retrieving cases from the future, but the same complaints recur on this account
for months. A held-out case about a Roku login failure may have a near-identical
predecessor in the history split. That is realistic, since a deployed system
would have the same advantage, but it means groundedness scores are flattered
relative to genuinely novel problems.

**Accuracy is dominated by one class.** The intent distribution is skewed toward
playback and app problems, which is why macro F1 is reported next to accuracy.
Read the macro figure when comparing systems and the per-class table when asking
whether a specific intent works.

**The agent was scored on 163 of 200 golden items, not all of them.** Groq's free
tier enforces a ceiling of 200,000 tokens per day that appears in no response
header: the rate-limit headers report a healthy per-minute token bucket and 993
remaining requests while the daily budget is finished, and the real limit surfaces
only inside the body of a 429. One agent call costs roughly 2,400 tokens, so the
allowance is about 83 calls a day, so the 200 golden predictions had to be
collected across three days in chunks as the budget refilled. All 200 completed in
the end, but the run was interrupted repeatedly, and one of those interruptions
caused the duplicate-prediction accident described below.

**The ablation is on a different model from the agent.** The same wall meant the
retrieval ablation could not run on gpt-oss-120b, so both of its arms run on
qwen3.8-27b instead. The comparison is internally valid, since the arms differ
only in whether exemplars are present, but it measures retrieval's effect on a
different model. The direction of the effect is so large, +2.34 on groundedness
with 27 wins and no losses, that I would be surprised if it reversed on the
deployed model, but the magnitude should not be transferred.

**Temperature zero is not deterministic here, and I can now put a number on it.**
Two prediction runs briefly overlapped and regenerated 31 golden cases a second
time, which by accident produced 31 independent repeat samples of the same prompt.

| repeated at temperature 0 | identical across runs |
|---|---:|
| escalation decision | 100% |
| intent label | 94% |
| confidence score | 58% |
| reply wording | 29% |

Three things follow. An intent accuracy gap smaller than about six points between
two systems could be run-to-run noise alone, on top of the sampling uncertainty
the bootstrap intervals already show, so small differences in the classification
tables should not be read as real. Reply-quality scores rest on wording that
changes on 71% of reruns, so the judged means are estimates of a distribution
rather than measurements of a fixed artefact. And the escalation decision did not
move once, which is the strongest evidence in the report for putting that decision
in policy code rather than in the prompt: the deterministic layer absorbed the
model's variance entirely.

This estimate is opportunistic rather than designed. 31 cases is small, they are
not a random subset, and a proper study would rerun the whole set several times.

**The judge's own validation is small.** Agreement is measured on roughly 40
rated replies from a single human. That is enough to detect a badly broken judge
and not enough to certify a good one.

## 6. What I would do with one more week

In priority order, because the first item changes how every other number should
be read.

1. **Label the evaluation set by hand.** Nothing else on this list matters until
   this is done. Every headline number is currently agreement between two models
   and cannot be called accuracy. Two hours of human labelling would convert the
   entire results section from suggestive to real, and the same pass would give
   the judge-versus-human agreement figure the brief asks for and this submission
   does not have. `scripts/14_make_spotcheck.py` builds a 30-item version that
   would at least measure how far the machine labels track a person.
2. **An outcome proxy.** Follow each held-out thread past the first brand reply.
   A customer who answers with thanks is weak evidence of resolution; one who
   restates the problem is weak evidence against. Noisy, but it would move reply
   evaluation from plausibility toward effect, which is the gap I am most
   uncomfortable about.
3. **Evaluate retrieval on its own.** Right now retrieval is only visible through
   the agent's output, so a retrieval failure and a generation failure are
   indistinguishable. Hand-labelling relevance for 50 queries would give
   recall@k and show whether the fusion weights are doing anything.
4. **Calibrate the confidence floor instead of choosing it.** The 0.55 threshold
   is a guess. A reliability curve on a dev slice would let the escalation rate
   be set from a stated tolerance for missed escalations rather than from taste.
5. **Fix the placeholder leak at the source.** Resolve the `<URL>` token to the
   real Hulu help URLs present in the raw data, so grounded replies can carry a
   link that works instead of a token that does not.
6. **Test whether the method transfers.** Run the whole pipeline on a second
   brand. The taxonomy is Hulu-specific by design, but if the *procedure* for
   inducing one does not transfer then the contribution is a Hulu classifier
   rather than a method.
