"""Database CLI entry point"""

import argparse
import sys
from pathlib import Path

from intel.config import Config
from intel.db import init_db


def main():
    parser = argparse.ArgumentParser(description="Intelligence Feed Database")
    parser.add_argument("--init", action="store_true", help="Initialize the database")
    parser.add_argument("--path", help="Override database path")

    args = parser.parse_args()

    if args.init:
        db_path = args.path or Config().db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = init_db(db_path)
        conn.close()
        print(f"Database initialized at: {db_path}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
