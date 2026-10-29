.PHONY: install run test sample report trap

install:
	pip install -r requirements.txt

run:
	streamlit run app.py

test:
	python -m pytest -q

sample:
	python -m checker.sample_data

report:
	python -m checker.cli data/sample_campaigns.csv --out out/report.html

trap:
	python -m checker.cli data/sample_campaigns.csv --out out/report-trap.html --offline --trap
