import json
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8000"
LOGIN_URL = BASE_URL + "/auth/login"

payload = {"username": "admin", "password": "admin123"}
req = urllib.request.Request(LOGIN_URL, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})

try:
    with urllib.request.urlopen(req) as resp:
        body = resp.read().decode("utf-8")
        print("LOGIN", resp.status, body)
        token = json.loads(body).get("access_token")
        if not token:
            raise SystemExit("No token returned")
        paths = ["/documents", "/policies", "/upload-history?document_type=policy", "/profile"]
        for path in paths:
            req2 = urllib.request.Request(BASE_URL + path, headers={"Authorization": f"Bearer {token}"})
            try:
                with urllib.request.urlopen(req2) as resp2:
                    text = resp2.read().decode("utf-8")
                    print(path, resp2.status, text[:400])
            except urllib.error.HTTPError as e2:
                err = e2.read().decode("utf-8")
                print(path, "HTTPError", e2.code, err)
except urllib.error.HTTPError as e:
    print("LOGIN_ERROR", e.code, e.read().decode("utf-8"))
except Exception as exc:
    import traceback
    traceback.print_exc()
