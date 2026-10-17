.PHONY: test lint build-web clean install-dev

test:
	python3 -m unittest discover -s tests -p "test_*.py"

lint:
	ruff check .

build-web:
	python3 web/build.py

install-dev:
	pip install -e .[dev]

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf build/ dist/ *.egg-info .ruff_cache/ .pytest_cache/
