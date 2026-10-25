.PHONY: check lint test gates app seed eval

check: lint test gates

lint:
	ruff check .
	ruff format --check .

test:
	python -m pytest --cov --cov-fail-under=80

gates:
	python -m eval.run_eval --retrieval --hybrid
	python -m eval.run_eval --rescore eval/reports/agent-2026-10-25-dev.jsonl
	python -m eval.run_eval --rescore eval/reports/agent-2026-10-25-heldout.jsonl

app:
	streamlit run app.py

seed:
	python scripts/seed.py

eval:
	python -m eval.run_eval --runs 3 --price-in 0.1 --price-out 0.5
