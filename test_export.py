"""Manual report download, never executed during import or test discovery."""
import argparse
import getpass
import json
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--gradebook-id", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    login = json.dumps({"username": args.username, "password": getpass.getpass("Password: ")}).encode()
    request = urllib.request.Request(args.base_url.rstrip("/") + "/api/auth/login", data=login, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        token = json.load(response)["access_token"]
    request = urllib.request.Request(args.base_url.rstrip("/") + f"/api/gradebooks/{args.gradebook_id}/report.xlsx", headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()
    # Do not overwrite an existing workbook.
    with args.output.open("xb") as target:
        target.write(data)
    print(f"Report saved: {args.output}")


if __name__ == "__main__":
    main()
