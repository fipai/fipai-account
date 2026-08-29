"""Safely inventory, rewrap, and retire TOTP encryption keys."""
from __future__ import annotations

import re
from collections import Counter

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import TwoFactorAuth
from accounts.totp_crypto import (
    PREFIX,
    TOTPSecretEncryptionError,
    decrypt_totp_secret,
    encrypt_totp_secret,
    get_totp_secret_key_id,
)

KEY_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,128}")


class Command(BaseCommand):
    help = "Inventory TOTP key references, rewrap them, or gate retirement of an old key"

    def add_arguments(self, parser):
        operation = parser.add_mutually_exclusive_group(required=True)
        operation.add_argument(
            "--from-key-id",
            help="rewrap secrets from this decrypt-only key to the configured active key",
        )
        operation.add_argument(
            "--check-retirement",
            metavar="KEY_ID",
            help="exit nonzero until this key has no references and all secrets are valid",
        )
        operation.add_argument(
            "--report",
            action="store_true",
            help="report reference counts without modifying records",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="preflight a rewrap without modifying records (requires --from-key-id)",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="rows per transaction during rewrap (default: 500; maximum: 10000)",
        )

    def handle(self, *args, **options):
        source_key_id = options["from_key_id"]
        retirement_key_id = options["check_retirement"]
        dry_run = options["dry_run"]
        batch_size = options["batch_size"]

        if dry_run and not source_key_id:
            raise CommandError("--dry-run requires --from-key-id.")
        if not 1 <= batch_size <= 10000:
            raise CommandError("--batch-size must be between 1 and 10000.")

        if options["report"]:
            references, invalid_count = self._inventory()
            self._write_report(references, invalid_count)
            self._require_valid_inventory(invalid_count)
            return

        if retirement_key_id:
            self._validate_key_id(retirement_key_id)
            references, invalid_count = self._inventory()
            self._write_report(references, invalid_count)
            self._require_valid_inventory(invalid_count)
            remaining = references.get(retirement_key_id, 0)
            if remaining:
                raise CommandError(
                    f"Retirement blocked: key {retirement_key_id!r} still has {remaining} reference(s)."
                )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Retirement gate passed: key {retirement_key_id!r} has no references."
                )
            )
            return

        self._rewrap(source_key_id, batch_size, dry_run)

    def _rewrap(self, source_key_id: str, batch_size: int, dry_run: bool) -> None:
        self._validate_key_id(source_key_id)
        active_key_id = settings.TOTP_ENCRYPTION_KEY_ID
        if source_key_id == active_key_id:
            raise CommandError("The source key must differ from the configured active key.")
        if source_key_id not in settings.TOTP_ENCRYPTION_KEYRING:
            raise CommandError("The source key is not available in the configured keyring.")

        references, invalid_count = self._inventory()
        self._write_report(references, invalid_count)
        self._require_valid_inventory(invalid_count)
        source_count = references.get(source_key_id, 0)

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Dry run passed: {source_count} secret(s) can be rewrapped from "
                    f"{source_key_id!r} to active key {active_key_id!r}."
                )
            )
            return
        if source_count == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"No references to {source_key_id!r}; nothing to rewrap."
                )
            )
            return

        source_prefix = f"{PREFIX}{source_key_id}:"
        source_ids = list(
            TwoFactorAuth.objects.filter(secret__startswith=source_prefix)
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        rewritten = 0
        for start in range(0, len(source_ids), batch_size):
            batch_ids = source_ids[start:start + batch_size]
            with transaction.atomic():
                rows = list(
                    TwoFactorAuth.objects.select_for_update()
                    .filter(pk__in=batch_ids)
                    .order_by("pk")
                    .only("pk", "secret")
                )
                for row in rows:
                    try:
                        current_key_id = get_totp_secret_key_id(row.secret)
                    except TOTPSecretEncryptionError as exc:
                        raise CommandError(
                            "Rewrap stopped because a locked TOTP secret is malformed."
                        ) from exc
                    if current_key_id != source_key_id:
                        continue
                    try:
                        plaintext = decrypt_totp_secret(row.secret)
                        replacement = encrypt_totp_secret(plaintext)
                    except TOTPSecretEncryptionError as exc:
                        raise CommandError(
                            "Rewrap stopped because a locked TOTP secret failed cryptographic validation."
                        ) from exc
                    updated = TwoFactorAuth.objects.filter(
                        pk=row.pk, secret=row.secret
                    ).update(secret=replacement)
                    if updated != 1:
                        raise CommandError(
                            "Rewrap stopped because a TOTP secret changed concurrently."
                        )
                    rewritten += 1

        final_references, final_invalid_count = self._inventory()
        self._require_valid_inventory(final_invalid_count)
        remaining = final_references.get(source_key_id, 0)
        if remaining:
            raise CommandError(
                f"Rewrap incomplete: key {source_key_id!r} still has {remaining} reference(s)."
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Rewrapped {rewritten} secret(s) to active key {active_key_id!r}; "
                "the source key now has zero references."
            )
        )

    def _inventory(self) -> tuple[Counter[str], int]:
        references: Counter[str] = Counter()
        invalid_count = 0
        secrets = TwoFactorAuth.objects.exclude(secret="").values_list("secret", flat=True)
        for secret in secrets.iterator(chunk_size=500):
            try:
                key_id = get_totp_secret_key_id(secret)
                references[key_id] += 1
                if key_id not in settings.TOTP_ENCRYPTION_KEYRING:
                    invalid_count += 1
                    continue
                decrypt_totp_secret(secret)
            except TOTPSecretEncryptionError:
                invalid_count += 1
        return references, invalid_count

    def _write_report(self, references: Counter[str], invalid_count: int) -> None:
        if references:
            for key_id in sorted(references):
                marker = "active" if key_id == settings.TOTP_ENCRYPTION_KEY_ID else "decrypt-only/unknown"
                self.stdout.write(f"key {key_id!r}: {references[key_id]} reference(s) [{marker}]")
        else:
            self.stdout.write("No encrypted TOTP secret references found.")
        self.stdout.write(f"invalid or undecryptable secret(s): {invalid_count}")

    @staticmethod
    def _require_valid_inventory(invalid_count: int) -> None:
        if invalid_count:
            raise CommandError(
                "Operation blocked: one or more TOTP secrets are plaintext, malformed, "
                "encrypted with an unavailable key, or cryptographically invalid."
            )

    @staticmethod
    def _validate_key_id(key_id: str) -> None:
        if not isinstance(key_id, str) or not KEY_ID_PATTERN.fullmatch(key_id):
            raise CommandError("Key id must match [A-Za-z0-9._-]{1,128}.")
