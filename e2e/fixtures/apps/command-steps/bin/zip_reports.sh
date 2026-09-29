#!/usr/bin/env bash
# Zip the output folder contents into reports.zip (inside that folder).
[[ "$1" == "--dir" ]] && dir="$2"
cd "$dir" || exit 1
python3 - <<'PY'
import zipfile, os
with zipfile.ZipFile('reports.zip', 'w') as z:
    for name in sorted(os.listdir('.')):
        if name != 'reports.zip' and os.path.isfile(name):
            z.write(name)
PY
echo "zip_reports: wrote reports.zip"
