"""Create a development organization and user explicitly (non-production).

Usage:
    python scripts/bootstrap_dev_user.py \
        --email owner@example.com \
        --organization "Demo EPC" \
        --password dev-password-123

The password can also be supplied via INDUSTRIAL_RFQ_BOOTSTRAP_PASSWORD so it
stays out of shell history. This script refuses to run when
INDUSTRIAL_RFQ_ENV=production: production environments must provision accounts
through the API (POST /auth/register) and explicit membership management,
never through an automated backdoor.
"""

from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import select

from freellmpool.api.db import (
    Organization,
    OrganizationMembership,
    SessionLocal,
    User,
    init_db,
)
from freellmpool.api.security import hash_password


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="login email for the user")
    parser.add_argument("--organization", required=True, help="organization name")
    parser.add_argument(
        "--password",
        default=os.getenv("INDUSTRIAL_RFQ_BOOTSTRAP_PASSWORD"),
        help="password (min 8 chars); prefer INDUSTRIAL_RFQ_BOOTSTRAP_PASSWORD",
    )
    parser.add_argument(
        "--role",
        default="OWNER",
        choices=["OWNER", "ADMIN", "MEMBER"],
        help="membership role granted to the user",
    )
    args = parser.parse_args()

    if os.getenv("INDUSTRIAL_RFQ_ENV", "").casefold() == "production":
        print("refusing to bootstrap accounts in production", file=sys.stderr)
        return 2
    email = args.email.strip().casefold()
    if "@" not in email or " " in email:
        print("a valid email address is required", file=sys.stderr)
        return 2
    if not args.password or len(args.password) < 8:
        print(
            "a password of at least 8 characters is required "
            "(--password or INDUSTRIAL_RFQ_BOOTSTRAP_PASSWORD)",
            file=sys.stderr,
        )
        return 2

    init_db()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, password_hash=hash_password(args.password))
            db.add(user)
            db.flush()
            print(f"created user {email}")
        else:
            print(f"user {email} already exists; password left unchanged")

        organization_name = args.organization.strip()
        organization = db.scalar(
            select(Organization).where(Organization.name == organization_name)
        )
        if organization is None:
            organization = Organization(name=organization_name)
            db.add(organization)
            db.flush()
            print(f"created organization {organization.name}")

        membership = db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization.id,
                OrganizationMembership.user_id == user.id,
            )
        )
        if membership is None:
            db.add(
                OrganizationMembership(
                    organization_id=organization.id,
                    user_id=user.id,
                    role=args.role,
                )
            )
            print(f"granted {args.role} on {organization.name}")

        db.commit()
    print("bootstrap complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
