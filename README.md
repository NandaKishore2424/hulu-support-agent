# Hulu support agent

Take-home for Hiver. A support agent for one brand's public Twitter stream, built
from the Kaggle [Customer Support on Twitter](https://www.kaggle.com/datasets/thoughtvector/customer-support-on-twitter)
dump, plus the evaluation I needed to work out whether it's any good.

For each incoming message it does three things: picks an intent from ten I defined
by reading the data, drafts a reply using how Hulu handled similar cases before,
and decides whether a human needs to see it.

Short version of what I found: the agent beats both baselines on intent, it isn't
safe to deploy because escalation is bad in both directions, and the most useful
thing I learned had nothing to do with the agent. More on that below.

## Results

Evaluation set is 200 held-out cases I labelled by hand. Headline is the 120-item
random slice. Intervals are bootstrap, 95%.

| system | accuracy | 95% CI | macro F1 | esc. precision | esc. recall |
|---|---:|---:|---:|---:|---:|
| majority class | 11.7% | 5.8–17.5 | 0.021 | 0.0% | 0.0% |
| keyword + copy nearest reply | 29.2% | 20.8–37.5 | 0.235 | 28.6% | 35.3% |
| **agent** | **49.2%** | 40.8–58.3 | **0.404** | 27.3% | 35.3% |

Reply quality, scored blind by a judge model from a different vendor:

| system | grounded | actionable | safe | voice | mean | postable |
|---|---:|---:|---:|---:|---:|---:|
| majority class | 2.56 | 3.80 | 4.92 | 3.34 | 3.65 | 90.0% |
| keyword + copy nearest reply | 3.20 | 3.24 | 4.72 | 4.36 | 3.88 | 28.0% |
| **agent** | **3.92** | 3.62 | **4.98** | **4.40** | **4.23** | 84.0% |

Retrieval on vs off, same model both arms, paired on 35 cases:

| dimension | with | without | diff | wins / losses |
|---|---:|---:|---:|---:|
| grounded | 4.66 | 2.31 | **+2.34** | 27 / 0 |
| voice | 4.77 | 3.09 | **+1.69** | 27 / 0 |
| actionable | 3.57 | 3.23 | +0.34 | 15 / 9 |
| postable | 0.66 | 0.86 | **−0.20** | 2 / 9 |

### What I actually learned

**A machine-labelled eval set flattered this agent by 28 points.** I ran out of
time to hand-label, so I generated the reference labels with a model first. Scored
against those, the agent got 79.9%. I then labelled all 200 by hand and the same
predictions scored 44.2%. Same items, same outputs, different reference.

The reason is measurable, not hand-waving: on 80 of 199 items the agent and the
machine labeller made the *same* mistake against my label. Both call an outage a
playback error. Both call a device problem a playback error. Two models trained on
similar text get things wrong the same way, so grading one with the other rewards
whatever they both miss. Hand-labelling was the only thing that could have caught
it, and I nearly didn't do it.

**Escalation is bad in both directions.** 22 cases went to a human, 6 needed to.
17 needed a human, it caught 6. So it burns agent time and still isn't safe. The
cause is upstream: the policy escalates outages automatically, but the classifier
only spots an outage in 2 of 14 real ones, so the rule barely fires.

**Retrieval buys groundedness and voice and nothing else.** +2.34 on grounded, 27
wins to 0. Nothing on actionability. And it makes replies *less* postable, because
grounding in past replies is also how my own `<URL>` placeholder gets copied into
the output. That one annoyed me.

**The agent is no more actionable than a one-line template.** 3.62 vs 3.80,
intervals overlap. The template just asks what device you're on, which turns out
to be useful for almost anything.

Two caveats worth stating up front. All 200 labels are mine, and I also wrote the
taxonomy, so there's no second annotator and no ceiling estimate. And I never got
to check the reply judge against a human, so those quality scores rank the systems
against each other and mean nothing in absolute terms. Both are in
[the report](reports/REPORT.md).

## Running it

Every model response is cached and committed, so the numbers come back with no API
key and no network.

```bash
make setup
make reproduce
```

Takes about a second. For a live run, put `GROQ_API_KEY` and `GEMINI_API_KEY` in
`.env` and use `make predict && make judge`. Budget an hour, and see the note on
rate limits below.

## How it works

**Threads.** The raw file is 3M loose tweets with reply pointers. `data.py` walks
the pointers, then merges runs of tweets from the same person into one turn,
because people fire off three in a row and that's one message.

**Split by date, not randomly.** Same complaints come round every week on this
account. A random split lets the agent retrieve a near-copy of the case you're
scoring it on. Cut at 2017-11-17: 11,091 history cases, 3,697 held out.

**One call for all three outputs.** Intent, reply and proposed handling come back
together. Splitting them would let the reply contradict the intent, and it'd
triple the calls against a free tier.

**Two retrievers, fused by rank.** BM25 over words gets the tokens that actually
decide the answer, Roku vs PS4 need different steps. Character 3-5 grams cope with
"buffring" and "chromcast". The scores aren't on the same scale so I combine them
by rank position. Anything that deflects to DM is filtered out of the pool, or the
agent just learns to stall.

**Escalation is code, not prompt.** The model proposes, `apply_policy` can
override. A policy inside a prompt can't be tested and changes silently when you
swap models. I got accidental evidence for this: two runs overlapped and
regenerated 31 cases, and across those the reply wording changed 71% of the time
while the handling decision never changed once.

**Judge guards.** Different vendor from the generator. Blind to which system wrote
the reply. Doesn't see the case's real answer, or it'd score similarity to one
response instead of quality. Rubric anchored at 1, 3 and 5 because otherwise
everything drifts to 4.

## Why Hulu

I picked the brand by measuring, because it decides whether the reply half is
evaluable at all. A brand whose answer to everything is "please DM us" resolves
cases off-platform, so there's nothing to ground a reply in.

I got this wrong the first time. My first pass searched for "DM us" and put
AmazonHelp on top at 0.7%. Then I read Amazon's actual replies and found it
deflects by pasting a web-form link instead. Counting that too moved Amazon to
12.1% and Hulu to the front.

| brand | outbound tweets | handoff rate | groundable replies |
|---|---:|---:|---:|
| hulu_support | 21,872 | 7.1% | 38.5% |
| AmazonHelp | 169,840 | 12.1% | 33.0% |
| AppleSupport | 106,860 | 54.1% | 32.6% |
| SpotifyCares | 43,265 | 31.1% | 27.5% |
| TMobileHelp | 34,317 | 82.9% | 4.5% |

`python scripts/01_brand_report.py` regenerates it.

## Layout

```
src/agent/
  config.py      model ids, rate budgets, paths
  data.py        thread rebuilding from the flat dump
  taxonomy.py    the ten intents, boundary rules, escalation policy
  retrieve.py    BM25 + character TF-IDF over Hulu's history
  agent.py       the classify/draft/triage call and the policy layer
  baselines.py   majority, keyword + nearest-neighbour, no-retrieval ablation
  judge.py       reply-quality rubric
  evaluate.py    metrics, bootstrap intervals, agreement stats
  llm.py         cached, rate-budgeted client for Groq and Gemini

scripts/         numbered pipeline stages, each runs on its own
data/golden/     the 200 hand-labelled items and the labelling UI
reports/         predictions, judgements, metrics, the report
cache/llm/       every model response, keyed by prompt hash
tests/           41 tests, mostly on the bits where a silent bug ruins a number
```

## Models, and the rate limits that shaped the client

Agent runs on Groq with `openai/gpt-oss-120b`. Judge is Google's
`gemini-3.5-flash-lite`. Different families on purpose, since a judge from the
generator's own family likes its own phrasing.

Both free tiers bind, in opposite ways, and both ended up in the code.

Groq caps tokens per day at 200,000 and it shows up in no response header. The
rate-limit headers happily report a healthy per-minute bucket and 993 requests
left while the daily budget is gone. You only see the real limit inside a 429
body. Three of my runs died silently before I found it, so `llm.py` now raises a
specific error for it and stops instead of retrying into nothing.

Gemini is the opposite, tight on requests per minute and counted per model. The
client keeps rolling per-provider budgets for tokens and requests both, and
reconciles what it reserved against what the call actually used. That took
sustained throughput from about one call a minute to over five.

## Also worth reading

- [`reports/REPORT.md`](reports/REPORT.md) — framing, results, five failure modes
  with real examples, what's misleading about the headline, what I'd do next.
- [`reports/DECISION_LOG.md`](reports/DECISION_LOG.md) — the 15 decisions that
  weren't obvious, and why I made them.
- [`data/golden/GOLDEN_SET.md`](data/golden/GOLDEN_SET.md) — how I sampled and
  labelled the eval set, and what's wrong with it.

## Credits

- Dataset: Customer Support on Twitter, Kaggle, user `thoughtvector`.
- `rank-bm25` by Dorian Brown. scikit-learn for vectorisation.
- Reciprocal rank fusion follows Cormack, Clarke and Buettcher (2009).
- Built with an AI coding assistant, which the brief allows. Every non-obvious
  choice and its reasoning is in `reports/DECISION_LOG.md`.
- `<URL>` and `@user` in the quoted examples are my own normalisation, not
  something in the source data.
