VIDEO ?= sample-data/onboard.mp4
PY = .venv/bin/python

.PHONY: up down setup cv cv-kafka

up:
	docker compose up -d

down:
	docker compose down

setup:
	python3 -m venv .venv
	.venv/bin/pip install -r services/cv-ai-worker/requirements.txt

# Run CV on the sample video, save annotated video + events
cv:
	mkdir -p output
	cd services/cv-ai-worker && ../../$(PY) -m worker.main ../../$(VIDEO) \
		--out ../../output/annotated.mp4 --events ../../output/events.jsonl

# Same, but stream events to Redpanda in real time
cv-kafka:
	cd services/cv-ai-worker && ../../$(PY) -m worker.main ../../$(VIDEO) \
		--kafka localhost:19092 --realtime --show
