#!/bin/bash
set -e
# If running as a Home Assistant add-on, options are available at /data/options.json
OPTIONS_FILE="/data/options.json"
if [ -f "$OPTIONS_FILE" ]; then
  # Use jq-style parsing via python to avoid adding jq dependency
  CLIENT_ID=$(python - <<'PY'
import json,sys
o=json.load(open('/data/options.json'))
print(o.get('client_id','') or '')
PY
)
  CLIENT_SECRET=$(python - <<'PY'
import json,sys
o=json.load(open('/data/options.json'))
print(o.get('client_secret','') or '')
PY
)
  TENANT_ID=$(python - <<'PY'
import json,sys
o=json.load(open('/data/options.json'))
print(o.get('tenant_id','') or '')
PY
)
  BACKUP_PATH=$(python - <<'PY'
import json,sys,os
o=json.load(open('/data/options.json'))
print(o.get('backup_path','/backup') or '/backup')
PY
)
  SECURE_KEY=$(python - <<'PY'
import json,sys
o=json.load(open('/data/options.json'))
print(o.get('secure_key','') or '')
PY
)
  # export to environment for the python app
  export CLIENT_ID
  export CLIENT_SECRET
  export TENANT_ID
  export BACKUP_PATH
  export SECURE_KEY
fi

python main.py
