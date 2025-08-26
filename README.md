# Trace UI

## Installation

Requires python 3.6 or newer

If running outside a virtual python environment:
```
sudo -H pip install pandas pyside6==6.2.4
git clone ...
cd traceui
```

If using a virtual environment:
```
pip install pandas pyside6==6.2.4
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
./run.sh
```
Which will check for updates and then launch the gui. Follow the onscreen instructions from there.

## Outputs

All outputs are stored int the tmp/* folder in the script run directory.
