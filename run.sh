#!/bin/bash
#
# Try to never change this file, as this would break it as it updates itself!
#

if [[ $(git diff --quiet) ]]; then
	echo "Differences in checked out code - not running update!"
else
	echo "Updating..."
	git pull --rebase --quiet
	echo "... update done."
fi

. ./update-artifacts.sh

python traceui.py
