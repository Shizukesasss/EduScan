import urllib.request
import json
import urllib.parse
import os

login_data = json.dumps({"username": "admin", "password": "admin123"}).encode('utf-8')
req = urllib.request.Request("http://127.0.0.1:8000/api/auth/login", data=login_data, headers={'Content-Type': 'application/json'})
token = json.loads(urllib.request.urlopen(req).read().decode())['access_token']

req2 = urllib.request.Request("http://127.0.0.1:8000/api/gradebooks/103/report.xlsx?region=V&division=V&school_id=301874", headers={'Authorization': 'Bearer ' + token})
res = urllib.request.urlopen(req2)
with open("test_export.xlsx", "wb") as f:
    f.write(res.read())

print(f"Exported successfully! File size: {os.path.getsize('test_export.xlsx')} bytes.")
