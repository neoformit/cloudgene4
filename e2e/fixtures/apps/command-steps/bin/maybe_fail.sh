#!/usr/bin/env bash
# $1 = ok|fail|sleep, $2 = seconds to sleep (mode sleep)
case "$1" in
  fail) echo "about to fail" >&2; exit 7 ;;
  sleep) exec sleep "${2:-60}" ;;
esac
echo "quiet step done"
