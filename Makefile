.PHONY: all build push test

all: test up

test: lint
	rm -f unittest.log
	pytest --log-file=unittest.log --log-level=INFO tests

lint:
	flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
	flake8 . --count --statistics --config .style.yapf

up:
	python3 main.py --syncdb
	python3 main.py --port=5002 --host=0.0.0.0 --logging=debug --log-file-prefix=/tmp/brs.log

