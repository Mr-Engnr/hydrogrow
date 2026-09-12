.PHONY: models mock test dashboard-up dashboard-down clean

REPO := <you>/hydrogrow
RELEASE := v1.0.0

# Download model weights from the GitHub Release instead of committing them.
models:
	mkdir -p ml/disease-detection/models
	curl -L -o ml/disease-detection/models/lettuce_mobilenetv2.h5 \
	  https://github.com/$(REPO)/releases/download/$(RELEASE)/lettuce_mobilenetv2.h5

# Run the firmware control loop with no hardware, replaying sample telemetry.
mock:
	python -m firmware.main --mock --speed 60x

test:
	pytest firmware/tests/ -v

dashboard-up:
	docker compose up

dashboard-down:
	docker compose down

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	rm -rf backend/build backend/node_modules dashboard/node_modules
