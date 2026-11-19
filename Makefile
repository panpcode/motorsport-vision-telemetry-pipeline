DRIVE ?= sample-data/2011_09_26_drive_0015
VIDEO ?= $(DRIVE)/front.mp4
# KITTI camera: 81 deg FOV, 1.65 m above road
CAM = --hfov 81 --cam-height 1.65
PY = .venv/bin/python
PYTHON ?= $(shell command -v python3.12 || echo python3)

.PHONY: up down setup sample cv compare cv-kafka

up:
	docker compose up -d

down:
	docker compose down

setup:
	$(PYTHON) -m venv .venv
	.venv/bin/pip install -r services/cv-ai-worker/requirements.txt

# Download a KITTI drive: front camera + GPS/IMU (~250 MB)
sample:
	$(PY) scripts/get_sample.py

# Run CV on the sample video, save annotated video + events
cv:
	mkdir -p output
	cd services/cv-ai-worker && ../../$(PY) -m worker.main ../../$(VIDEO) $(CAM) \
		--out ../../output/annotated.mp4 --events ../../output/events.jsonl

# CV estimates vs real GPS/IMU
compare:
	$(PY) scripts/compare_kitti.py output/events.jsonl --drive $(DRIVE)

# Stream events to Redpanda in real time
cv-kafka:
	cd services/cv-ai-worker && ../../$(PY) -m worker.main ../../$(VIDEO) $(CAM) \
		--kafka localhost:19092 --realtime --show
