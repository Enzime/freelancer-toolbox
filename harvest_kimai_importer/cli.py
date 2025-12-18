#!/usr/bin/env python3
"""CLI for importing time entries from Harvest to Kimai."""

import argparse
import calendar
import json
import os
import sys
import urllib.error
from datetime import date, datetime, timedelta

from harvest import get_time_entries
from kimai.api import KimaiAPI

from . import HarvestKimaiImporter


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Import time entries from Harvest to Kimai",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Harvest credentials
    harvest_account = os.environ.get("HARVEST_ACCOUNT_ID")
    parser.add_argument(
        "--harvest-account-id",
        default=harvest_account,
        required=harvest_account is None,
        help="Harvest account ID (env: HARVEST_ACCOUNT_ID)",
    )

    harvest_token = os.environ.get("HARVEST_BEARER_TOKEN")
    parser.add_argument(
        "--harvest-bearer-token",
        default=harvest_token,
        required=harvest_token is None,
        help="Harvest bearer token (env: HARVEST_BEARER_TOKEN)",
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

    # Date range options
    parser.add_argument(
        "--start",
        type=int,
        help="Start date as YYYYMMDD (e.g., 20240101)",
    )
    parser.add_argument(
        "--end",
        type=int,
        help="End date as YYYYMMDD (e.g., 20240131)",
    )
    parser.add_argument(
        "--months",
        type=int,
        nargs="+",
        choices=range(1, 13),
        metavar="MONTH",
        help="Months to import (1-12), conflicts with --start/--end",
    )
    parser.add_argument(
        "--year",
        type=int,
        help="Year for --months option (defaults to current year)",
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
    parser.add_argument(
        "--input-file",
        type=str,
        help="Read Harvest entries from JSON file instead of API",
    )

    args = parser.parse_args()

    # Validate date range arguments
    if args.months and (args.start or args.end):
        parser.error("--months conflicts with --start and --end")

    if (args.start and not args.end) or (args.end and not args.start):
        parser.error("Both --start and --end must be provided together")

    # Calculate date range
    today = datetime.today()
    if args.months:
        year = args.year if args.year else today.year
        months = sorted(args.months)
        args.start = get_month_range(year, months[0])[0]
        args.end = get_month_range(year, months[-1])[1]
    elif not args.start and not args.end:
        # Default to previous month
        start_of_month = today.replace(day=1)
        end_of_previous_month = start_of_month - timedelta(days=1)
        args.start = int(end_of_previous_month.strftime("%Y%m01"))
        args.end = int(end_of_previous_month.strftime("%Y%m%d"))

    return args


def get_month_range(year: int, month: int) -> tuple[int, int]:
    """Get start and end dates for a given month and year."""
    _, last_day = calendar.monthrange(year, month)
    start = int(date(year, month, 1).strftime("%Y%m%d"))
    end = int(date(year, month, last_day).strftime("%Y%m%d"))
    return start, end


def main() -> None:
    """Main entry point for the CLI."""
    args = parse_args()

    # Get Harvest entries
    if args.input_file:
        print(f"Reading entries from {args.input_file}...")
        with open(args.input_file) as f:
            entries = json.load(f)
        print(f"Loaded {len(entries)} entries from file")
    else:
        print(f"Fetching entries from Harvest ({args.start} to {args.end})...")
        try:
            entries = get_time_entries(
                args.harvest_account_id,
                args.harvest_bearer_token,
                args.start,
                args.end,
            )
        except urllib.error.URLError as e:
            print(f"Failed to fetch entries from Harvest: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"Fetched {len(entries)} entries from Harvest")

    if not entries:
        print("No entries to import")
        sys.exit(0)

    # Initialize Kimai API
    print("Connecting to Kimai...")
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
        print("\n*** DRY RUN - no changes will be made ***\n")

    print("Importing entries...")
    stats = importer.import_entries(entries)

    # Print results
    print("\n=== Import Summary ===")
    print(f"Entries processed: {stats.entries_processed}")
    print(f"Entries created:   {stats.entries_created}")
    print(f"Entries skipped:   {stats.entries_skipped}")
    print(f"Customers created: {stats.customers_created}")
    print(f"Projects created:  {stats.projects_created}")
    print(f"Activities created: {stats.activities_created}")

    if stats.errors:
        print(f"\nErrors ({len(stats.errors)}):")
        for error in stats.errors:
            print(f"  - {error}")
        sys.exit(1)

    print("\nImport completed successfully!")


if __name__ == "__main__":
    main()
