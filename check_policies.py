import argparse
import json
from scripts.eduscan_api import school_api

def main():
    parser = argparse.ArgumentParser(description="List EduScan grading policies and their component weights.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="admin")
    args = parser.parse_args()
    with school_api(args.base_url, args.username) as request:
        with request("/api/grading-policies") as response:
            policies = json.load(response)
        for policy in policies:
            print(f"Policy: {policy['name']} (ID: {policy['id']})")
            with request(f"/api/grading-policies/{policy['id']}") as response:
                details = json.load(response)
            for component in details.get('components', []):
                print(f"  - {component['name']}: {component['weight']}%")

if __name__ == "__main__":
    main()
