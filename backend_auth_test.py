import json
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8005"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiIsImV4cCI6MTc4NTg3NjczMn0.UGVG2gLg_lddgB5X43BErncspQksnm0QP6wxdu67kUs"
for path in ["/documents", "/policies", "/upload-history?document_type=policy"]:
    req = urllib.request.Request(BASE_URL + path, headers={"Authorization": f"Bearer {TOKEN}"})
    try:
        with urllib.request.urlopen(req) as resp:
            print(path, resp.status, resp.read().decode("utf-8")[:400])
    except urllib.error.HTTPError as e:
        print(path, "HTTPError", e.code, e.read().decode("utf-8"))
