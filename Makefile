.PHONY: run test lint format format-check coverage seed migrate ci

run:
	python manage.py runserver

migrate:
	python manage.py migrate

seed:
	python manage.py seed_survey --with-admin

test:
	pytest

lint:
	ruff check apps config

format:
	black apps config
	ruff check apps config --fix

format-check:
	black --check apps config

coverage:
	coverage run -m pytest
	coverage report --fail-under=100 --include="apps/surveys/*" --omit="*/migrations/*,*/tests/*"

# Mirror of .github/workflows/ci.yml — run before pushing to catch what CI would.
ci: lint format-check migrate coverage
