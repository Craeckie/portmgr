#!/bin/bash
set -x
set -e
python setup.py sdist
twine upload dist/*
curl -X PURGE https://pypi.org/project/portmgr
rm -rf build/ dist/ portmgr.egg-info/
