# Trace UI

The Trace UI tool is a python application that is designed to streamline the process of creating and post
processing API traces from Android by automating as much of the workflow as possible.

Purpose
* Make tracing on Android faster, easier and more reliable.
* Streamline and standardize the trace generation process to increase consistency.
* Offer a reliable way to generate and verify fastforward traces on rootable devices available in the market.

## Installation

Requires python 3.6 or newer

If running outside a virtual python environment:
```
sudo -H pip install pandas pyside6==6.7.0
git clone ...
cd traceui
```

If using a virtual environment:
```
pip install pandas pyside6==6.7.0
git clone ...
cd traceui
```

In order to run fast forwarding verification, ensure to have imagemagick installed:
```
apt install imagemagick
```

## Development


## Running

Linux

```
./run.sh [--log-level info|debug|warning|error]
```
Which will check for updates and then launch the gui. Follow the onscreen instructions from there.

Logging
```
# default: console INFO, file DEBUG

```
Logs are written to `traceui.log` in the repo root.

## Outputs

All outputs are stored int the tmp/* folder in the script run directory.
