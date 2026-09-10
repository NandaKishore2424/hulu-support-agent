VENV := .venv/bin
BRAND ?= hulu_support

.PHONY: help setup data reproduce predict judge metrics agreement label rate test clean

help:
	@echo "make setup      install dependencies into .venv"
	@echo "make data       download twcs from Kaggle and build the case splits"
	@echo "make reproduce  recompute every reported number from the committed cache (no API key)"
	@echo "make predict    run all systems over the golden set (needs GROQ_API_KEY)"
	@echo "make judge      score replies with the LLM judge (needs GEMINI_API_KEY)"
	@echo "make label      serve the golden-set labelling UI"
	@echo "make rate       serve the reply-rating UI used to validate the judge"

setup:
	uv venv --python 3.12
	uv pip install -e ".[dev]" kaggle

data:
	$(VENV)/kaggle datasets download -d thoughtvector/customer-support-on-twitter -p data/raw --unzip
	$(VENV)/python scripts/01_brand_report.py
	$(VENV)/python scripts/02_build_cases.py --brand $(BRAND)
	$(VENV)/python scripts/03_sample_golden.py --brand $(BRAND)

reproduce: metrics agreement

predict:
	$(VENV)/python scripts/05_run_systems.py --stage predict --live

judge:
	$(VENV)/python scripts/05_run_systems.py --stage judge --live

metrics:
	$(VENV)/python scripts/06_metrics.py --brand $(BRAND)

agreement:
	$(VENV)/python scripts/08_judge_agreement.py

label:
	$(VENV)/python scripts/04_make_labeller.py --brand $(BRAND)
	$(VENV)/python scripts/label_server.py

rate:
	$(VENV)/python scripts/07_make_rater.py
	$(VENV)/python scripts/label_server.py

test:
	$(VENV)/python -m pytest tests -q

clean:
	rm -rf reports/predictions reports/judgements reports/metrics.json
