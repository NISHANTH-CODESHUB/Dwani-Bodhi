"""Operator CLI (run where DATABASE_URL points at the database, e.g. your laptop against the Vercel Postgres).

    python -m app.cli reset-pin --phone 98xxxxxxxx      # a teacher forgot the PIN: new PIN, printed once
    python -m app.cli bugs                               # Claude-proposed misconceptions waiting for review
    python -m app.cli bugs --approve <id> | --reject <id>  # pedagogy lead's decision (discovery loop)
    python -m app.cli reset-data --yes                   # wipe ALL teachers, classes, children and history
    python -m app.cli generate-cards [--force]
    python -m app.cli discover                           # run the bug discovery loop once
    python -m app.cli validate-content
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from sqlalchemy import select


def main() -> None:
    ap = argparse.ArgumentParser(prog="app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("reset-pin")
    r.add_argument("--phone", required=True)
    b = sub.add_parser("bugs")
    grp = b.add_mutually_exclusive_group()
    grp.add_argument("--approve", metavar="ID")
    grp.add_argument("--reject", metavar="ID")
    w = sub.add_parser("reset-data", help="delete every account, class, child, answer and media file")
    w.add_argument("--yes", action="store_true", help="confirm: this cannot be undone")
    g = sub.add_parser("generate-cards")
    g.add_argument("--force", action="store_true")
    sub.add_parser("discover")
    sub.add_parser("validate-content")
    args = ap.parse_args()

    from .db import SessionLocal

    if args.cmd == "validate-content":
        from .services.common import pack
        errs = pack().validate()
        print(json.dumps({"version": pack().version, "items": len(pack().items), "errors": errs}, ensure_ascii=False))
        raise SystemExit(1 if errs else 0)
    if args.cmd == "reset-data":
        if not args.yes:
            raise SystemExit("refusing without --yes: this deletes all teachers, children and their history")
        from .services.reset import reset_all_data
        print(json.dumps(reset_all_data(), indent=2))
        return
    with SessionLocal() as db:
        if args.cmd == "reset-pin":
            from .models import User
            from .security import generate_pin, hash_phone, hash_pin
            u = db.scalar(select(User).where(User.phone_hash == hash_phone(args.phone)))
            if u is None:
                raise SystemExit("no account with this phone")
            pin = generate_pin(6)
            u.pin_hash, u.active = hash_pin(pin), True
            u.credentials_changed_at = datetime.now(UTC)  # ends every existing session
            db.commit()
            print(f"new PIN for {u.display_name}, shown once:", pin)
        elif args.cmd == "bugs":
            from .models import BugProposal
            pid = args.approve or args.reject
            if pid:
                bp = db.get(BugProposal, pid)
                if bp is None:
                    raise SystemExit("no such proposal")
                bp.status, bp.reviewed_by = ("approved" if args.approve else "rejected"), "cli"
                db.commit()
                print(pid, bp.status)
                return
            for bp in db.scalars(select(BugProposal).where(BugProposal.status == "proposed")
                                 .order_by(BugProposal.created_at)):
                print(json.dumps({"id": bp.id, "description": bp.description, "spec": bp.spec,
                                  "explains": len(bp.explains or [])}, ensure_ascii=False))
        elif args.cmd == "generate-cards":
            from .models import Classroom
            from .services.cards import generate_card
            for room in db.scalars(select(Classroom)).all():
                row = generate_card(db, room.id, force=args.force)
                print(room.id, row.week, row.source)
        elif args.cmd == "discover":
            from .services.discovery import run_discovery
            print(run_discovery(db))


if __name__ == "__main__":
    main()
