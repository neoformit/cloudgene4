#!/usr/bin/env bash
# Prints something (stdout) and a note on stderr; never fails.
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir) dir="$2"; shift 2 ;;
    --label) label="$2"; shift 2 ;;
    *) shift ;;
  esac
done
echo "collect_errors: dir=$(basename "$dir") label=[$label] cwd=$(basename "$PWD")"
echo "collect_errors: $(grep -c ERROR "$dir/run.log") error lines"
echo "collect_errors: note on stderr" >&2
