"""Manual report download, never executed during import or test discovery."""
import argparse
from pathlib import Path


def main():
    from scripts.eduscan_api import school_api

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--gradebook-id", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    with school_api(args.base_url, args.username) as request:
        with request(f"/api/gradebooks/{args.gradebook_id}/report.xlsx", timeout=60) as response:
            data = response.read()
    # Do not overwrite an existing workbook.
    with args.output.open("xb") as target:
        target.write(data)
    print(f"Report saved: {args.output}")


if __name__ == "__main__":
    main()
