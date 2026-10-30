"""Command line tasks: python -m app.cli <command>."""

import argparse
import json
import sys
import time
from pathlib import Path

from alembic.config import Config

from alembic import command

from .db import Base, SessionLocal, engine

ROOT = Path(__file__).resolve().parents[1]


def migrate() -> None:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    command.upgrade(cfg, "head")


def reset() -> None:
    from . import models  # noqa: F401

    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    migrate()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate", help="apply database migrations")
    p_seed = sub.add_parser("seed", help="load the demo dataset")
    p_seed.add_argument("--reset", action="store_true", help="drop all data first")
    p_seed.add_argument("--if-empty", action="store_true", help="seed only when the database has no users")
    p_seed.add_argument("--institutions", type=int, default=600)
    p_seed.add_argument("--samples", default=str(ROOT.parent / "samples"), help="where to write the sample FDRs for the demo")
    sub.add_parser("sweep", help="run the maturity monitor and re-score late-renewal risk now")
    args = parser.parse_args(argv)

    if args.cmd == "migrate":
        migrate()
        return 0
    if args.cmd == "seed":
        from .models import User
        from .seed.generate import seed

        if args.reset:
            reset()
        else:
            migrate()
        with SessionLocal() as db:
            if db.query(User.id).first():
                if args.if_empty:
                    print("Database already seeded; skipping.")
                    return 0
                print("Database already has data. Use --reset to start over.", file=sys.stderr)
                return 1
            started = time.time()
            result = seed(db, n_institutions=args.institutions, samples_dir=Path(args.samples))
        print(json.dumps(result, indent=2, default=str))
        print(f"Seeded in {time.time() - started:.0f}s. Sign in with any demo account, password Demo@2026.")
        return 0
    if args.cmd == "sweep":
        from .services.sweeps import run_sweep

        with SessionLocal() as db:
            print(run_sweep(db))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
