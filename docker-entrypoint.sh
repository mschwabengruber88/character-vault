#!/bin/sh
set -e

mkdir -p /data
chown -R appuser:appuser /data /app

exec gosu appuser "$@"
