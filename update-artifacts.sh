#!/bin/bash

touch .cached
mkdir -p artifacts

export TRACEUI_LATEST_RELEASE="r1p0"
export TRACEUI_CORE_URL="https://github.com/ARM-software/traceui/releases/download"
export TRACEUI_CACHED_VERSION=$(cat .cached)

if [[ "${TRACEUI_LATEST_RELEASE}" != "$TRACEUI_CACHED_VERSION" ]]; then
	echo "Updating artifacts for ${TRACEUI_LATEST_RELEASE}..."

	wget $TRACEUI_CORE_URL/${TRACEUI_LATEST_RELEASE}/gfxreconstruct-arm.tar.gz
	wget $TRACEUI_CORE_URL/${TRACEUI_LATEST_RELEASE}/hwcpipe.tar.gz
	wget $TRACEUI_CORE_URL/${TRACEUI_LATEST_RELEASE}/patrace.tar.gz

	tar xzf gfxreconstruct-arm.tar.gz -C artifacts
	tar xzf hwcpipe.tar.gz -C artifacts
	tar xzf patrace.tar.gz -C artifacts
	rm -f gfxreconstruct-arm.tar.gz hwcpipe.tar.gz patrace.tar.gz

	echo "${TRACEUI_LATEST_RELEASE}" >> .cached
	echo "... done."
fi
