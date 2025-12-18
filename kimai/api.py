#!/usr/bin/env python3

import urllib
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from kimai.data import (
    ActivityInfo,
    CustomerInfo,
    ProjectInfo,
    TimeEntry,
    TimeEntryFull,
    UserInfo,
)
from rest import http_request2


class KimaiError(Exception):
    pass


@dataclass
class KimaiAPI:
    access_token: str
    api_url: str

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def kimai_request(
        self, endpoint: str, data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        data["page"] = 1
        headers = {
            "Authorization": f"Bearer {self.access_token}",
        }
        all_entries = []
        while True:
            url = f"{self.api_url}{endpoint}"
            resp = http_request2(url, headers=headers, data=data)
            if isinstance(resp.json, dict):
                all_entries.append(resp.json)
            else:
                all_entries.extend(resp.json)

            total_pages = int(resp.headers.get("X-Total-Pages", 1))
            if data["page"] >= total_pages:
                break

            data["page"] += 1

        return all_entries

    def kimai_post(self, endpoint: str, data: dict[str, Any]) -> dict[str, Any]:
        """Make a POST request to the Kimai API."""
        url = f"{self.api_url}{endpoint}"
        resp = http_request2(url, method="POST", headers=self._headers(), data=data)
        if isinstance(resp.json, dict):
            return resp.json
        msg = f"Unexpected response type: {type(resp.json)}"
        raise KimaiError(msg)

    def get_visible_projects(self, billable: bool = False) -> list[dict[str, Any]]:
        endpoint = "/api/projects"
        data = {
            "visible": 1,
        }
        return self.kimai_request(endpoint, data)

    def get_visible_users(self) -> list[dict[str, Any]]:
        endpoint = "/api/users"
        data = {
            "visible": 1,
        }
        return self.kimai_request(endpoint, data)

    def get_customer(self, customer_id: int) -> CustomerInfo:
        endpoint = f"/api/customers/{customer_id}"
        custom_data = self.kimai_request(endpoint, {})
        return CustomerInfo.from_json(custom_data[0])

    def get_user(self, user_id: int) -> UserInfo:
        endpoint = f"/api/users/{user_id}"
        user_data = self.kimai_request(endpoint, {})
        return UserInfo.from_json(user_data[0])

    def get_activity(self, activity_id: int) -> ActivityInfo:
        endpoint = f"/api/activities/{activity_id}"
        activity_data = self.kimai_request(endpoint, {})
        return ActivityInfo.from_json(activity_data[0])

    def get_time_entries(
        self,
        from_date: datetime,
        to_date: datetime,
        user_id: int,
        customer_id: int,
        project_id: int,
        billable: bool = True,
    ) -> list[dict[str, Any]]:
        endpoint = "/api/timesheets"
        data = {
            "user": user_id,
            "customer": customer_id,
            "project": project_id,
            "begin": from_date.strftime("%Y-%m-%dT%H:%M:%S"),
            "end": to_date.strftime("%Y-%m-%dT%H:%M:%S"),
            "billable": int(billable),
        }
        try:
            return self.kimai_request(endpoint, data)
        except urllib.error.HTTPError as e:
            msg = f"Failed to get time entries: {data}"
            raise KimaiError(msg) from e

    def get_time_entry(self, entry_id: int) -> TimeEntryFull:
        endpoint = f"/api/timesheets/{entry_id}"
        entry_data = self.kimai_request(endpoint, {})
        return TimeEntryFull.from_json(entry_data[0])

    def get_customers(self, visible: bool = True) -> list[CustomerInfo]:
        """Get all visible customers."""
        endpoint = "/api/customers"
        data: dict[str, Any] = {}
        if visible:
            data["visible"] = 1
        customers_data = self.kimai_request(endpoint, data)
        return [CustomerInfo.from_json(c) for c in customers_data]

    def get_projects(
        self, customer_id: int | None = None, visible: bool = True
    ) -> list[ProjectInfo]:
        """Get all visible projects, optionally filtered by customer."""
        endpoint = "/api/projects"
        data: dict[str, Any] = {}
        if visible:
            data["visible"] = 1
        if customer_id is not None:
            data["customer"] = customer_id
        projects_data = self.kimai_request(endpoint, data)
        return [ProjectInfo.from_json(p) for p in projects_data]

    def get_activities(
        self, project_id: int | None = None, visible: bool = True
    ) -> list[ActivityInfo]:
        """Get all visible activities, optionally filtered by project."""
        endpoint = "/api/activities"
        data: dict[str, Any] = {}
        if visible:
            data["visible"] = 1
        if project_id is not None:
            data["project"] = project_id
        activities_data = self.kimai_request(endpoint, data)
        return [ActivityInfo.from_json(a) for a in activities_data]

    def create_customer(self, name: str, country: str, currency: str) -> CustomerInfo:
        """Create a new customer."""
        endpoint = "/api/customers"
        data = {
            "name": name,
            "country": country,
            "currency": currency,
        }
        try:
            result = self.kimai_post(endpoint, data)
            return CustomerInfo.from_json(result)
        except urllib.error.HTTPError as e:
            msg = f"Failed to create customer '{name}': {e}"
            raise KimaiError(msg) from e

    def create_project(
        self, name: str, customer_id: int, visible: bool = True
    ) -> ProjectInfo:
        """Create a new project."""
        endpoint = "/api/projects"
        data = {
            "name": name,
            "customer": customer_id,
            "visible": visible,
        }
        try:
            result = self.kimai_post(endpoint, data)
            return ProjectInfo.from_json(result)
        except urllib.error.HTTPError as e:
            msg = f"Failed to create project '{name}': {e}"
            raise KimaiError(msg) from e

    def create_activity(
        self, name: str, project_id: int | None = None, visible: bool = True
    ) -> ActivityInfo:
        """Create a new activity (global if project_id is None)."""
        endpoint = "/api/activities"
        data: dict[str, Any] = {
            "name": name,
            "visible": visible,
        }
        if project_id is not None:
            data["project"] = project_id
        try:
            result = self.kimai_post(endpoint, data)
            return ActivityInfo.from_json(result)
        except urllib.error.HTTPError as e:
            msg = f"Failed to create activity '{name}': {e}"
            raise KimaiError(msg) from e

    def create_timesheet(
        self,
        begin: datetime,
        end: datetime,
        project_id: int,
        activity_id: int,
        description: str | None = None,
        user_id: int | None = None,
        billable: bool = True,
        tags: list[str] | None = None,
    ) -> TimeEntry:
        """Create a new timesheet entry."""
        endpoint = "/api/timesheets"
        data: dict[str, Any] = {
            "begin": begin.strftime("%Y-%m-%dT%H:%M:%S"),
            "end": end.strftime("%Y-%m-%dT%H:%M:%S"),
            "project": project_id,
            "activity": activity_id,
            "billable": billable,
        }
        if description:
            data["description"] = description
        if user_id is not None:
            data["user"] = user_id
        if tags:
            data["tags"] = ",".join(tags)
        try:
            result = self.kimai_post(endpoint, data)
            return TimeEntry.from_json(result)
        except urllib.error.HTTPError as e:
            msg = f"Failed to create timesheet entry: {e}"
            raise KimaiError(msg) from e
