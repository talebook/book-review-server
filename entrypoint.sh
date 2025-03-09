#!/bin/sh

/app/wait-for-it.sh mysql:3306 || exit 1

python3 main.py --syncdb
python3 main.py --port=80 --host=0.0.0.0 --logging=debug --log-file-prefix=/app/brs.log

