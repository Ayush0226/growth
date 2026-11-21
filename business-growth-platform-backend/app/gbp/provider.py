"""Google-only HTTP boundary. Paths are validated before attaching credentials."""

import re
from typing import Any

import httpx


SCOPE = "https://www.googleapis.com/auth/business.manage"
ACCOUNT = re.compile(r"^accounts/[A-Za-z0-9_-]+$")
LOCATION = re.compile(r"^accounts/[A-Za-z0-9_-]+/locations/[A-Za-z0-9_-]+$")
REVIEW = re.compile(r"^accounts/[A-Za-z0-9_-]+/locations/[A-Za-z0-9_-]+/reviews/[A-Za-z0-9_-]+$")


class GoogleError(Exception):
    def __init__(self, status: int, *, uncertain: bool = False):
        self.status, self.uncertain = status, uncertain
        super().__init__("Google delivery is uncertain" if uncertain else "Google request failed")


def resource(value: str, kind: str) -> str:
    pattern = {"account": ACCOUNT, "location": LOCATION, "review": REVIEW}[kind]
    if not pattern.fullmatch(value):
        raise ValueError(f"Invalid Google {kind} resource")
    return value


class GoogleClient:
    def __init__(self, token: str, http: httpx.AsyncClient):
        self.token, self.http = token, http

    async def call(self, method: str, host: str, path: str, **kwargs) -> dict[str, Any]:
        if host not in {"mybusinessaccountmanagement.googleapis.com", "mybusinessbusinessinformation.googleapis.com",
                        "mybusiness.googleapis.com", "businessprofileperformance.googleapis.com",
                        "mybusinessnotifications.googleapis.com"}:
            raise ValueError("Unapproved Google API host")
        writing = method not in {"GET", "HEAD"}
        try:
            response = await self.http.request(method, f"https://{host}/{path}",
                                               headers={"Authorization": f"Bearer {self.token}"}, **kwargs)
        except httpx.HTTPError:
            raise GoogleError(502, uncertain=writing) from None
        if response.status_code >= 400:
            raise GoogleError(response.status_code, uncertain=writing and
                              (response.status_code in {408, 429} or response.status_code >= 500))
        if response.status_code == 204 or not response.content:
            return {}
        try:
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except ValueError:
            raise GoogleError(502, uncertain=writing) from None

    async def accounts(self, page_token: str = ""):
        return await self.call("GET", "mybusinessaccountmanagement.googleapis.com", "v1/accounts",
                               params={"pageSize": 20, "pageToken": page_token})

    async def locations(self, account: str, page_token: str = ""):
        return await self.call("GET", "mybusinessbusinessinformation.googleapis.com",
                               f"v1/{resource(account, 'account')}/locations",
                               params={"readMask": "name,title,storefrontAddress,websiteUri,phoneNumbers,metadata",
                                       "pageSize": 100, "pageToken": page_token})

    async def reviews(self, location: str, page_token: str = ""):
        return await self.call("GET", "mybusiness.googleapis.com",
                               f"v4/{resource(location, 'location')}/reviews",
                               params={"pageSize": 50, "orderBy": "updateTime desc", "pageToken": page_token})

    async def review(self, name: str):
        return await self.call("GET", "mybusiness.googleapis.com", f"v4/{resource(name, 'review')}")

    async def reply(self, name: str, text: str):
        return await self.call("PUT", "mybusiness.googleapis.com", f"v4/{resource(name, 'review')}/reply",
                               json={"comment": text})

    async def delete_reply(self, name: str):
        return await self.call("DELETE", "mybusiness.googleapis.com", f"v4/{resource(name, 'review')}/reply")

    async def publish(self, location: str, payload: dict):
        return await self.call("POST", "mybusiness.googleapis.com",
                               f"v4/{resource(location, 'location')}/localPosts", json=payload)

    async def notifications(self, account: str):
        # Read only: never replace GBP AutoMaster's account-level topic implicitly.
        return await self.call("GET", "mybusinessnotifications.googleapis.com",
                               f"v1/{resource(account, 'account')}/notificationSetting")
