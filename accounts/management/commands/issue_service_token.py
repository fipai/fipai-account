"""Issue a short-lived, tenant-bound service JWT for deployment operations."""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from accounts.jwt import issue_service_access_token


class Command(BaseCommand):
    help = "Issue a short-lived service JWT for an allowlisted internal service"

    def add_arguments(self, parser):
        parser.add_argument(
            "--service",
            required=True,
            help="Allowlisted service principal name, for example decisionops",
        )
        parser.add_argument(
            "--tenant-id",
            required=True,
            type=int,
            help="Numeric active tenant id bound to the token",
        )
        parser.add_argument(
            "--scope",
            dest="product_scopes",
            action="append",
            required=True,
            help="Product scope to grant; repeat for multiple scopes",
        )

    def handle(self, *args, **options):
        try:
            token = issue_service_access_token(
                service_name=options["service"],
                tenant_id=options["tenant_id"],
                product_scopes=options["product_scopes"],
            )
        except (TypeError, ValueError) as exc:
            raise CommandError("Unable to issue service token: invalid service, scope, or tenant") from exc

        # Deliberately emit only the one-time credential. Do not log or persist it.
        self.stdout.write(token)
