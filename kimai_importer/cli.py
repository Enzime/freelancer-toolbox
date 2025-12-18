#!/usr/bin/env python3
"""CLI for importing time entries to Kimai."""

import argparse
import json
import os
import sys

from kimai.api import KimaiAPI

from . import HarvestKimaiImporter


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Import time entries to Kimai (reads from stdin)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Input format
    parser.add_argument(
        "--format",
        required=True,
        choices=("harvest-json",),
        help="Input format (harvest-json: raw JSON from harvest-exporter --format raw-json)",
    )

    # Kimai credentials
    kimai_url = os.environ.get("KIMAI_API_URL")
    parser.add_argument(
        "--kimai-api-url",
        default=kimai_url,
        required=kimai_url is None,
        help="Kimai API URL (env: KIMAI_API_URL)",
    )

    kimai_token = os.environ.get("KIMAI_API_KEY")
    parser.add_argument(
        "--kimai-api-key",
        default=kimai_token,
        required=kimai_token is None,
        help="Kimai API key (env: KIMAI_API_KEY)",
    )

    # Import options
    parser.add_argument(
        "--country",
        default="DE",
        help="Default country code for new customers",
    )
    parser.add_argument(
        "--currency",
        default="EUR",
        help="Default currency for new customers",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate import without making changes",
    )

    return parser.parse_args()


def main() -> None:
    """Main entry point for the CLI."""
    args = parse_args()

    # Read entries from stdin
    print("Reading entries from stdin...", file=sys.stderr)
    try:
        entries = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON input: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Loaded {len(entries)} entries", file=sys.stderr)

    if not entries:
        print("No entries to import", file=sys.stderr)
        sys.exit(0)

    # Initialize Kimai API
    print("Connecting to Kimai...", file=sys.stderr)
    kimai_api = KimaiAPI(
        access_token=args.kimai_api_key,
        api_url=args.kimai_api_url,
    )

    # Create importer
    importer = HarvestKimaiImporter(
        kimai_api=kimai_api,
        default_country=args.country,
        default_currency=args.currency,
        dry_run=args.dry_run,
    )

    # Run import
    if args.dry_run:
        print("\n*** DRY RUN - no changes will be made ***\n", file=sys.stderr)

    print("Importing entries...", file=sys.stderr)
    stats = importer.import_entries(entries)

    # Print results
    print("\n=== Import Summary ===", file=sys.stderr)
    print(f"Entries processed: {stats.entries_processed}", file=sys.stderr)
    print(f"Entries created:   {stats.entries_created}", file=sys.stderr)
    print(f"Entries skipped:   {stats.entries_skipped}", file=sys.stderr)
    print(f"Customers created: {stats.customers_created}", file=sys.stderr)
    print(f"Projects created:  {stats.projects_created}", file=sys.stderr)
    print(f"Activities created: {stats.activities_created}", file=sys.stderr)

    if stats.errors:
        print(f"\nErrors ({len(stats.errors)}):", file=sys.stderr)
        for error in stats.errors:
            print(f"  - {error}", file=sys.stderr)
        sys.exit(1)

    print("\nImport completed successfully!", file=sys.stderr)


if __name__ == "__main__":
    main()
