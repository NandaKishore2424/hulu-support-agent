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

_To be completed once the golden labels are in._

## 4. Failure analysis

_To be completed from the labelled results._

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
