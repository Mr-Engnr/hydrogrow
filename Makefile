.PHONY: test dashboard-up dashboard-down clean

test:
	pytest firmware/tests/ -v

dashboard-up:
	docker compose up

dashboard-down:
	docker compose down

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	rm -rf backend/build backend/node_modules dashboard/node_modules
