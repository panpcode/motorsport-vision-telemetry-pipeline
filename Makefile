DRIVE ?= sample-data/2011_09_26_drive_0015
VIDEO ?= $(DRIVE)/front.mp4
# KITTI camera: 81 deg FOV, 1.65 m above road
CAM = --hfov 81 --cam-height 1.65
PY = .venv/bin/python
PYTHON ?= $(shell command -v python3.12 || echo python3)

.PHONY: up down migrate setup sample cv compare demo laps forza-decode forza-cv forza-sync forza-laps forza-demo

up:
	docker compose up -d

down:
	docker compose down

# Apply schema changes to an existing ClickHouse (all files are safe to re-run)
migrate:
	for f in infra/clickhouse/*.sql; do \
		docker compose exec -T clickhouse clickhouse-client --user motorsport --password motorsport \
			--database motorsport --multiquery < $$f || exit 1; done

setup:
	$(PYTHON) -m venv .venv
	.venv/bin/pip install -r services/cv-ai-worker/requirements.txt -r services/lap-analysis/requirements.txt

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

# Source time of the first telemetry sample, shared by both services
T0 = $(shell $(PY) -c "from datetime import datetime as d; print(d.strptime(open('$(DRIVE)/oxts/timestamps.txt').readline()[:26], '%Y-%m-%d %H:%M:%S.%f').timestamp()*1000)")

# Live replay: telemetry + CV events to Redpanda on the same clock (SHOW=1 for a preview window)
demo:
	@START=$$(( $$(date +%s) * 1000 + 8000 )); RUN=run-$$(date +%H%M%S); echo "run_id=$$RUN"; \
	$(PY) services/telemetry-producer/producer.py $(DRIVE) --kafka localhost:19092 \
		--run-id $$RUN --start-ms $$START --t0-ms $(T0) & \
	cd services/cv-ai-worker && ../../$(PY) -m worker.main ../../$(VIDEO) $(CAM) --kafka localhost:19092 \
		--realtime --run-id $$RUN --start-ms $$START --t0-ms $(T0) \
		--timestamps ../../$(DRIVE)/image_02/timestamps.txt $(if $(SHOW),--show); \
	wait

# Real F1 lap comparison (OpenF1): where time was gained/lost. Shows in Grafana > Lap Comparison
YEAR ?= 2025
EVENT ?= Yas Marina
SESSION ?= Qualifying
A ?= VER
B ?= NOR
laps:
	cd services/lap-analysis && ../../$(PY) -m laps.main $(A) $(B) --year $(YEAR) --event "$(EVENT)" \
		--session $(SESSION) --out ../../output --clickhouse http://localhost:8123

# --- Own data: Forza Motorsport on Xbox (see README) ---
# FORZA = folder with telemetry_*.csv (record_udp_telemetry.py) and the OBS video (.mp4)
FORZA ?= sample-data/forza/session
FDIR = $(abspath $(FORZA))
# Starting guess for the bumper camera; make forza-sync measures the real values
FORZA_CAM = --hfov 75 --cam-height 0.5 --obs-start --stride 2 --calib $(FDIR)/sync.json
FORZA_VIDEO = "$$(ls $(FDIR)/*.mp4 | head -1)"
FORZA_T0 = $(shell $(PY) -c "import csv; print(next(csv.DictReader(open('$(FDIR)/telemetry.csv')))['ts_ms'])")

# Raw packets -> telemetry.csv
forza-decode:
	$(PY) scripts/decode_forza.py $(FDIR)

# CV on the OBS video -> events.jsonl + annotated.mp4
forza-cv:
	cd services/cv-ai-worker && ../../$(PY) -m worker.main $(FORZA_VIDEO) $(FORZA_CAM) \
		--events $(FDIR)/events.jsonl --out $(FDIR)/annotated.mp4

# Exact video offset + camera FOV/height from the data -> sync.json (then forza-cv again)
forza-sync:
	$(PY) scripts/sync_video.py $(FDIR)

# Fastest vs second fastest lap (LAP_A=3 LAP_B=5 to choose). Shows in Grafana > Lap Comparison
forza-laps:
	cd services/lap-analysis && ../../$(PY) -m laps.main --csv $(FDIR)/telemetry.csv \
		$(if $(LAP_A),--lap-a $(LAP_A)) $(if $(LAP_B),--lap-b $(LAP_B)) \
		--out ../../output --clickhouse http://localhost:8123

# Live replay of the session: game telemetry + CV events on one clock
forza-demo:
	@START=$$(( $$(date +%s) * 1000 + 8000 )); RUN=forza-$$(date +%H%M%S); echo "run_id=$$RUN"; \
	$(PY) services/telemetry-producer/producer.py $(FDIR)/telemetry.csv --kafka localhost:19092 \
		--run-id $$RUN --start-ms $$START --t0-ms $(FORZA_T0) & \
	cd services/cv-ai-worker && ../../$(PY) -m worker.main $(FORZA_VIDEO) $(FORZA_CAM) --kafka localhost:19092 \
		--realtime --run-id $$RUN --start-ms $$START --t0-ms $(FORZA_T0) $(if $(SHOW),--show); \
	wait
