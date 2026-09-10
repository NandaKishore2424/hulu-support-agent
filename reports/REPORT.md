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
only. A golden set of 200 held-out cases hand-labelled through a UI that hides
which sampling slice each item came from and hides Hulu's real reply behind a
reveal key. One structured model call per case produces intent, confidence, a
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

### Classification and triage

Incomplete. Both depend on the hand-labelled golden set, and on the free-tier
daily token ceiling described in section 5, which stopped the agent at 163 of 200
golden items. `scripts/06_metrics.py` prints these tables in full once the labels
are in place.

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

**I labelled my own evaluation set, alone.** There is no second annotator, so
there is no inter-annotator agreement figure for intent. That matters more than
it sounds: without it there is no estimate of the ceiling. If two careful people
would only agree 85% of the time on these labels, then a classifier at 85% is at
the ceiling and one at 92% is overfitting my personal reading of the taxonomy.
Every intent accuracy in this report is accuracy against one person's judgement,
and that person also designed the taxonomy and wrote the prompt that encodes it.
The agent and the gold labels share an author. That is the single largest threat
to validity here and no amount of bootstrapping fixes it.

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
allowance is about 83 calls a day, and it ran out with 37 golden items and the
retrieval ablation unmeasured. Those items are not a random subset of the golden
set, they are whatever remained in file order, so the missing 37 could be
systematically different from the 163 scored. The ablation gap is worse: without
it, the claim that retrieval is what drives the groundedness advantage rests on
comparing against a copy baseline rather than against the same model with
retrieval removed.

**One run, no variance estimate.** Results come from a single pass at temperature
zero. gpt-oss reasons before answering and is not perfectly deterministic, so
some of the reported difference between systems is run-to-run variation that I
have not measured.

**The judge's own validation is small.** Agreement is measured on roughly 40
rated replies from a single human. That is enough to detect a badly broken judge
and not enough to certify a good one.

## 6. What I would do with one more week

In priority order, because the first item changes how every other number should
be read.

1. **A second annotator on 60 items.** This is the highest-value hour in the
   whole project. It converts every accuracy figure from "agreement with me" into
   "agreement with a labelling standard", and it establishes the ceiling that
   tells me whether the agent has room to improve or is already at the limit of
   the task definition.
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
