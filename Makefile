.PHONY: run test lint format coverage seed migrate

run:
	python manage.py runserver

migrate:
	python manage.py migrate

seed:
	python manage.py seed_survey --with-admin

test:
	pytest

lint:
	ruff check .

format:
	black .
	ruff check . --fix

coverage:
	coverage run -m pytest
	coverage report --fail-under=99 --include="apps/surveys/*" --omit="*/migrations/*,*/tests/*"
