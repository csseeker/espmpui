.PHONY: test lint build-web clean install-dev build-dist release-check

test:
	python3 -m unittest discover -s tests -p "test_*.py"

lint:
	ruff check .

build-web:
	python3 web/build.py

build-dist: build-web
	python3 -m pip install --upgrade build flit
	python3 -m build

release-check: build-dist
	python3 -m pip install --upgrade twine
	python3 -m twine check dist/*

install-dev:
	pip install -e .[dev]

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf build/ dist/ *.egg-info .ruff_cache/ .pytest_cache/
