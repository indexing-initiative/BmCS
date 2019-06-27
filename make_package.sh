#!/usr/bin/env bash
# For Max's use only
rm -r build
rm -r dist
python setup.py bdist_wheel
cp -r dist ../BmCS_installation_env
