#!/bin/bash
set -x
set -e
rm -rf dist/ portmgr.egg-info/
python setup.py sdist
twine upload dist/*
curl -X PURGE https://pypi.org/project/portmgr
rm -rf build/ dist/ portmgr.egg-info/
