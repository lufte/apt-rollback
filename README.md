[![Build Status](https://travis-ci.org/lufte/apt-rollback.svg?branch=master)](https://travis-ci.org/lufte/apt-rollback)

# apt-rollback

Upgraded some packages and something broke? You're not alone.

This tool will revert all package operations on an apt-based system back to a specific time that you provide. It retrieves action logs from dpkg logs, so it doesn't matter if you use apt, aptitude, synaptic or other tools.

## Installation

This is a simple, self-contained python3 script with no extra dependencies. If you have python3 (3.5+ particularly) you're good to go, just download [the script](https://raw.githubusercontent.com/lufte/apt-rollback/master/apt-rollback.py), give it execution permissions and read its help with `./apt-rollback.py -h`.

## Dependencies

* python 3.5+
* Debian: packages are downloaded from http://snapshot.debian.org/ which only keeps track of Debian packages. Supporting other distros could be possible without much trouble though.
