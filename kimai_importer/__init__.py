#!/usr/bin/env python3
"""Import time entries from Harvest to Kimai."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from kimai.api import KimaiAPI, KimaiError
from kimai.data import ActivityInfo, CustomerInfo, ProjectInfo


@dataclass
class ImportStats:
    """Statistics for the import operation."""

    entries_processed: int = 0
    entries_created: int = 0
    entries_skipped: int = 0
    customers_created: int = 0
    projects_created: int = 0
    activities_created: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class HarvestKimaiImporter:
    """Import time entries from Harvest to Kimai."""

    kimai_api: KimaiAPI
    default_country: str = "DE"
    default_currency: str = "EUR"
    dry_run: bool = False

    # Caches for mapping Harvest names to Kimai IDs
    _customer_cache: dict[str, CustomerInfo] = field(default_factory=dict)
    _project_cache: dict[str, ProjectInfo] = field(default_factory=dict)
    _activity_cache: dict[str, ActivityInfo] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize caches from Kimai."""
        self._load_existing_entities()

    def _load_existing_entities(self) -> None:
        """Load existing customers, projects, and activities from Kimai."""
        # Load customers
        for customer in self.kimai_api.get_customers():
            self._customer_cache[customer.name.lower()] = customer

        # Load projects
        for project in self.kimai_api.get_projects():
            # Key includes customer to handle same project name in different customers
            key = f"{project.customer}:{project.name.lower()}"
            self._project_cache[key] = project

        # Load activities (global and project-specific)
        for activity in self.kimai_api.get_activities():
            # Key includes project to handle same activity name in different projects
            project_key = activity.project if activity.project else "global"
            key = f"{project_key}:{activity.name.lower()}"
            self._activity_cache[key] = activity

    def get_or_create_customer(
        self, name: str, stats: ImportStats
    ) -> CustomerInfo:
        """Get existing customer or create a new one."""
        key = name.lower()
        if key in self._customer_cache:
            return self._customer_cache[key]

        if self.dry_run:
            # Return a fake customer for dry run
            fake = CustomerInfo(
                id=-1,
                name=name,
                number="",
                comment=None,
                visible=True,
                billable=True,
                company=None,
                vatId=None,
                contact=None,
                address=None,
                country=self.default_country,
                currency=self.default_currency,
                phone=None,
                fax=None,
                mobile=None,
                email=None,
                homepage=None,
                timezone="Europe/Berlin",
                metaFields=[],
                teams=[],
                budget=0.0,
                timeBudget=0.0,
                budgetType=None,
                color="#000000",
            )
            self._customer_cache[key] = fake
            stats.customers_created += 1
            return fake

        customer = self.kimai_api.create_customer(
            name=name,
            country=self.default_country,
            currency=self.default_currency,
        )
        self._customer_cache[key] = customer
        stats.customers_created += 1
        return customer

    def get_or_create_project(
        self, name: str, customer_id: int, stats: ImportStats
    ) -> ProjectInfo:
        """Get existing project or create a new one."""
        key = f"{customer_id}:{name.lower()}"
        if key in self._project_cache:
            return self._project_cache[key]

        if self.dry_run:
            # Return a fake project for dry run
            fake = ProjectInfo(
                id=-1,
                name=name,
                customer=customer_id,
                parentTitle="",
                start="",
                end=None,
                comment=None,
                visible=True,
                billable=True,
                metaFields=[],
                teams=[],
                globalActivities=True,
                number="",
                color="#000000",
            )
            self._project_cache[key] = fake
            stats.projects_created += 1
            return fake

        project = self.kimai_api.create_project(
            name=name,
            customer_id=customer_id,
        )
        self._project_cache[key] = project
        stats.projects_created += 1
        return project

    def get_or_create_activity(
        self, name: str, project_id: int | None, stats: ImportStats
    ) -> ActivityInfo:
        """Get existing activity or create a new one."""
        project_key = project_id if project_id else "global"
        key = f"{project_key}:{name.lower()}"
        if key in self._activity_cache:
            return self._activity_cache[key]

        # Also check for global activity with same name
        global_key = f"global:{name.lower()}"
        if global_key in self._activity_cache:
            return self._activity_cache[global_key]

        if self.dry_run:
            # Return a fake activity for dry run
            fake = ActivityInfo(
                id=-1,
                name=name,
                project=project_id,
                parentTitle=None,
                comment=None,
                visible=True,
                billable=True,
                metaFields=[],
                teams=[],
                number="",
                budget=0.0,
                timeBudget=0.0,
                budgetType=None,
                color="#000000",
            )
            self._activity_cache[key] = fake
            stats.activities_created += 1
            return fake

        activity = self.kimai_api.create_activity(
            name=name,
            project_id=project_id,
        )
        self._activity_cache[key] = activity
        stats.activities_created += 1
        return activity

    def import_entry(
        self, entry: dict[str, Any], stats: ImportStats
    ) -> bool:
        """Import a single Harvest time entry to Kimai.

        Returns True if entry was created, False if skipped.
        """
        stats.entries_processed += 1

        # Extract Harvest data
        client_name = entry["client"]["name"]
        project_name = entry["project"]["name"]
        task_name = entry["task"]["name"]
        notes = entry.get("notes", "") or ""
        hours = float(entry["hours"])
        spent_date = entry["spent_date"]

        # Skip entries with 0 hours
        if hours == 0:
            stats.entries_skipped += 1
            return False

        try:
            # Get or create customer (maps to Harvest client)
            customer = self.get_or_create_customer(client_name, stats)

            # Get or create project
            project = self.get_or_create_project(
                project_name, customer.id, stats
            )

            # Get or create activity (maps to Harvest task)
            activity = self.get_or_create_activity(task_name, project.id, stats)

            # Parse date and calculate begin/end times
            # Harvest provides spent_date but not specific times,
            # so we use 9:00 as start time
            date = datetime.strptime(spent_date, "%Y-%m-%d")
            begin = date.replace(hour=9, minute=0, second=0)
            end = begin + timedelta(hours=hours)

            # Build description from notes and Harvest metadata
            description_parts = []
            if notes:
                description_parts.append(notes)
            description_parts.append(f"[Harvest ID: {entry['id']}]")
            description = "\n".join(description_parts)

            if not self.dry_run:
                self.kimai_api.create_timesheet(
                    begin=begin,
                    end=end,
                    project_id=project.id,
                    activity_id=activity.id,
                    description=description,
                    billable=entry.get("billable", True),
                )

            stats.entries_created += 1
            return True

        except KimaiError as e:
            stats.errors.append(f"Entry {entry['id']}: {e}")
            return False

    def import_entries(
        self, entries: list[dict[str, Any]]
    ) -> ImportStats:
        """Import multiple Harvest time entries to Kimai."""
        stats = ImportStats()

        for entry in entries:
            self.import_entry(entry, stats)

        return stats
