import urllib.request
import json

def main():
    login_data = json.dumps({"username": "admin", "password": "admin123"}).encode('utf-8')
    req = urllib.request.Request("http://127.0.0.1:8000/api/auth/login", data=login_data, headers={'Content-Type': 'application/json'})
    token = json.loads(urllib.request.urlopen(req).read().decode())['access_token']

    req = urllib.request.Request("http://127.0.0.1:8000/api/grading-policies", headers={'Authorization': 'Bearer ' + token})
    res = json.loads(urllib.request.urlopen(req).read().decode())
    for p in res:
        print(f"Policy: {p['name']} (ID: {p['id']})")
        # Fetch the full policy to get components
        req2 = urllib.request.Request(f"http://127.0.0.1:8000/api/grading-policies/{p['id']}", headers={'Authorization': 'Bearer ' + token})
        pfull = json.loads(urllib.request.urlopen(req2).read().decode())
        for c in pfull.get('components', []):
            print(f"  - {c['name']}: {c['weight']}%")

if __name__ == "__main__":
    main()
