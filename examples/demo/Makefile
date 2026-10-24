.PHONY: migrate seed

migrate:
	psql "$$WHEELO_DATABASE_URL" -f src/schema.sql

seed:
	./scripts/seed.sh
