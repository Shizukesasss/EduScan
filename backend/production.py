"""Start the production API after verifying the database and persistent data path."""

import os
import sys
from pathlib import Path


def main() -> None:
    required = ("DATABASE_URL", "EDUSCAN_SECRET_KEY", "EDUSCAN_ENCRYPTION_KEY", "EDUSCAN_DATA_DIR")
    missing = [name for name in required if not os.getenv(name, "").strip()]
    if missing:
        raise SystemExit("Missing production settings: " + ", ".join(missing))

    from sqlalchemy.exc import SQLAlchemyError

    from app.config import DATA_DIR
    from app.database import engine
    from app.migrations import verify_schema

    if DATA_DIR != Path(os.environ["EDUSCAN_DATA_DIR"]).resolve():
        raise SystemExit("EduScan could not open the configured persistent data directory.")
    if engine.url.get_backend_name() != "postgresql":
        raise SystemExit("Set DATABASE_URL to the school's restricted PostgreSQL login.")
    try:
        verify_schema(engine)
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
    except SQLAlchemyError:
        raise SystemExit("Could not verify the production PostgreSQL connection.") from None
    finally:
        engine.dispose()

    os.execv(sys.executable, [
        sys.executable, "-m", "uvicorn", "app.main:app",
        "--host", "0.0.0.0", "--port", "8000", "--workers", "1",
    ])


if __name__ == "__main__":
    main()
