#!/bin/bash
#
# Script to update artifacts on a new traceui release
#

touch .cached
mkdir -p artifacts

export TRACEUI_LATEST_RELEASE="r1p1"
export TRACEUI_CORE_URL="https://github.com/ARM-software/traceui/releases/download"
export TRACEUI_CACHED_VERSION=$(cat .cached)

GFXRECON_RELEASE="r4p2"
PATRACE_RELEASE="r5p4"

if [[ "${TRACEUI_LATEST_RELEASE}" != "$TRACEUI_CACHED_VERSION" ]]; then
  echo "Updating artifacts for ${TRACEUI_LATEST_RELEASE}..."

  wget $TRACEUI_CORE_URL/${TRACEUI_LATEST_RELEASE}/gfxreconstruct-arm-${GFXRECON_RELEASE}.tar.gz
  wget $TRACEUI_CORE_URL/${TRACEUI_LATEST_RELEASE}/hwcpipe.tar.gz
  wget $TRACEUI_CORE_URL/${TRACEUI_LATEST_RELEASE}/patrace-${PATRACE_RELEASE}.tar.gz

  tar xzf gfxreconstruct-arm-${GFXRECON_RELEASE}.tar.gz -C artifacts
  tar xzf hwcpipe.tar.gz -C artifacts
  tar xzf patrace-${PATRACE_RELEASE}.tar.gz -C artifacts
  rm -f gfxreconstruct-arm-${GFXRECON_RELEASE}.tar.gz hwcpipe.tar.gz patrace-${PATRACE_RELEASE}.tar.gz

  echo "${TRACEUI_LATEST_RELEASE}" >.cached
  echo "... done."
fi
