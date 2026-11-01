"""Operator CLI.

    python -m app.cli create-admin --phone 98xxxxxxxx --name "State Admin"   # prints a generated PIN once
    python -m app.cli reset-pin --phone 98xxxxxxxx    # forgotten PIN (e.g. the top-level admin): new PIN, printed once
    python -m app.cli generate-cards [--force]
    python -m app.cli discover            # run the bug discovery loop once
    python -m app.cli validate-content
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC

from sqlalchemy import select


def main() -> None:
    ap = argparse.ArgumentParser(prog="app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("create-admin")
    a.add_argument("--phone", required=True)
    a.add_argument("--pin", help="omit to generate a strong PIN (printed once; only its hash is stored)")
    a.add_argument("--name", default="Admin")
    r = sub.add_parser("reset-pin")
    r.add_argument("--phone", required=True)
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
    with SessionLocal() as db:
        if args.cmd == "create-admin":
            from .models import User
            from .security import generate_pin, hash_phone, hash_pin, pin_problem
            pin = args.pin or generate_pin(8)  # admins get a longer PIN
            problem = pin_problem(pin, args.phone)
            if problem:
                raise SystemExit(f"weak PIN: {problem}")
            if db.scalar(select(User).where(User.phone_hash == hash_phone(args.phone))):
                raise SystemExit("phone already registered")
            u = User(role="admin", phone_hash=hash_phone(args.phone), pin_hash=hash_pin(pin), display_name=args.name)
            db.add(u)
            db.commit()
            print("admin created:", u.id)
            if not args.pin:
                print("PIN (shown once, not stored in readable form):", pin)
        elif args.cmd == "reset-pin":
            from datetime import datetime

            from .models import User
            from .security import generate_pin, hash_phone, hash_pin
            u = db.scalar(select(User).where(User.phone_hash == hash_phone(args.phone)))
            if u is None:
                raise SystemExit("no account with this phone")
            pin = generate_pin(8 if u.role == "admin" else 6)
            u.pin_hash, u.active = hash_pin(pin), True
            u.credentials_changed_at = datetime.now(UTC)  # ends every existing session
            db.commit()
            print(f"new PIN for {u.display_name} ({u.role}), shown once:", pin)
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
