#!/usr/bin/env bash
# For Local use only, to make package. Instructions not included in README
# Must have BmCS_installation_env directory
rm -r build
rm -r dist
python setup.py bdist_wheel
cp -r dist ../BmCS_installation_env
