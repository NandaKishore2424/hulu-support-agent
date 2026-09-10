# Hulu support agent — intent, grounded replies, escalation triage

An AI support agent for one brand's public Twitter support stream, built from the
[Customer Support on Twitter](https://www.kaggle.com/datasets/thoughtvector/customer-support-on-twitter)
dataset, together with the evidence that it works and an account of where that
evidence is weak.

The agent does three things for every incoming customer message:

1. **Classifies** it into one of ten intents induced from the data.
2. **Drafts a reply** grounded in how this brand has actually resolved similar
   issues before, retrieved from its own history.
3. **Decides** whether it can be auto-handled or needs a human, with a stated
   reason.

## Reproduce the headline numbers

Every LLM call this project ever made is cached in `cache/llm/` and committed.
Reproduction recomputes the reported numbers from those cached responses and
needs no API key and no network.

```bash
make setup
make reproduce
```

`make reproduce` runs two scripts. `scripts/06_metrics.py` prints the intent,
triage and reply-quality tables. `scripts/08_judge_agreement.py` prints how well
the LLM judge agrees with a human on the same replies.

To re-run against the live APIs instead, put a `GROQ_API_KEY` and a
`GEMINI_API_KEY` in `.env` and run `make predict && make judge`. That takes about
an hour on the free tiers, which are token-limited rather than request-limited.

## Rebuilding from the raw data

```bash
make data      # download twcs.csv, rank brands, build case splits, sample the golden set
make label     # serve the labelling UI, then export golden_labels.jsonl
make predict   # run all four systems over the golden set
make judge     # score the replies with the judge
make rate      # serve the reply-rating UI, then export reply_ratings.jsonl
make reproduce # print every table
```

`make data` needs Kaggle credentials at `~/.kaggle/kaggle.json`.

## Why Hulu

Brand choice was made on measured properties of the data, not reputation, because
it decides whether the reply half of the project can be evaluated at all. A brand
whose standard move is "please DM us" resolves its cases off-platform, so its
visible replies are handoffs and there is nothing to ground a drafted reply in.

Counting both handoff idioms matters. A regex for "DM us" alone ranks AmazonHelp
as the most substantive brand in the dataset at a 0.7% deflection rate. Amazon
actually deflects by pasting a web-form link, and once channel-switch phrasing is
counted its rate rises to 12.1%.

| brand | outbound tweets | handoff rate | groundable replies |
|---|---:|---:|---:|
| hulu_support | 21,872 | 7.1% | 38.5% |
| AmazonHelp | 169,840 | 12.1% | 33.0% |
| AppleSupport | 106,860 | 54.1% | 32.6% |
| SpotifyCares | 43,265 | 31.1% | 27.5% |
| TMobileHelp | 34,317 | 82.9% | 4.5% |

Hulu has the lowest handoff rate of any high-volume brand, writes concrete
troubleshooting steps, and covers a bounded problem space that makes a defensible
intent taxonomy possible. Reproduce the table with
`python scripts/01_brand_report.py`.

## Repository layout

```
src/agent/
  config.py      all tunable settings, including model ids and rate budgets
  data.py        thread reconstruction from the flat tweet dump
  taxonomy.py    intent definitions, boundary rules, escalation policy
  retrieve.py    BM25 + character TF-IDF retrieval over the brand's history
  agent.py       the classify / draft / triage call and the policy layer
  baselines.py   majority, keyword+nearest-neighbour, and a no-retrieval ablation
  judge.py       the LLM-as-judge rubric
  evaluate.py    metrics, bootstrap intervals, agreement statistics
  llm.py         cached, rate-budgeted client for Groq and Gemini

scripts/         numbered pipeline stages, each runnable on its own
data/golden/     the hand-labelled evaluation set and the labelling UIs
reports/         predictions, judgements, and the computed metrics
cache/llm/       every LLM response, keyed by prompt hash
```

## Models

The agent generates on Groq with `openai/gpt-oss-120b`. The judge scores on
Google's `gemini-3.5-flash-lite`. Different vendors and different model families
on purpose: a judge from the same family as the generator tends to prefer its own
phrasing, which would inflate every reply-quality number in the report.

Both free tiers bind in ways that shaped the code. Groq caps tokens per minute
rather than requests, so `llm.py` keeps a rolling 60-second token budget and
reconciles its reservation against real usage after each call. Gemini caps
requests per day *per model*, so exhausting one model's allowance leaves its
siblings untouched; the judge is pinned to one model and refuses to fail over,
because a quota wall must stop a run rather than silently change the instrument
mid-experiment. Every verdict records the model that produced it and the scripts
refuse to aggregate verdicts from more than one judge.

## Report

`reports/REPORT.md` covers problem framing, results against the baselines, the
top failure modes with real examples, what is misleading about the headline
number, and what a further week would buy. `reports/DECISION_LOG.md` lists the
non-obvious choices and the reasoning behind each.

## Credits

- Dataset: Customer Support on Twitter, Kaggle, user `thoughtvector`.
- BM25 implementation: `rank-bm25` by Dorian Brown.
- TF-IDF and vectorisation: scikit-learn.
- Reciprocal rank fusion follows Cormack, Clarke and Buettcher (2009).
- The `<URL>` and `@user` tokens in quoted examples come from this project's own
  normalisation, not from the source data.
