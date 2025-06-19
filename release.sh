#!/bin/bash
set -x
set -e
rm -rf dist/ portmgr.egg-info/
uv build
uv publish
#curl -X PURGE https://pypi.org/project/portmgr
rm -rf build/ dist/ portmgr.egg-info/
