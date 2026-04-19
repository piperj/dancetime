import requests


BASE_URL = "https://ndcapremier.com"


class NDCAClient:
    def __init__(self, session: requests.Session | None = None, timeout: int = 30):
        self._session = session or requests.Session()
        self._timeout = timeout

    def _get(self, endpoint: str, params: dict | None = None) -> dict | None:
        try:
            resp = self._session.get(
                f"{BASE_URL}{endpoint}",
                params=params,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError):
            return None
        if data.get("Status") != 1:
            return None
        return data.get("Result")

    def fetch_competition_info(self, cyi: int) -> dict | None:
        try:
            resp = self._session.get(
                f"{BASE_URL}/feed/compyears/",
                params={"cyi": cyi},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError):
            return None
        if data.get("Status") != 1:
            return None
        events = data.get("Events", [])
        return events[0] if events else None

    def fetch_calendar(self) -> list | None:
        try:
            resp = self._session.get(
                f"{BASE_URL}/feed/compyears/",
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError):
            return None
        if data.get("Status") != 1:
            return None
        return data.get("Events", [])

    def fetch_competitor_list(self, cyi: int, feed_type: str = "results") -> list:
        result = self._get(f"/feed/{feed_type}/", {"cyi": cyi})
        if not isinstance(result, list):
            return []
        return result

    def fetch_competitor_results(self, cyi: int, competitor_id: str, competitor_type: str) -> dict | None:
        return self._get("/feed/results/", {"cyi": cyi, "id": competitor_id, "type": competitor_type})

    def fetch_competitor_heatlists(self, cyi: int, competitor_id: str, competitor_type: str) -> dict | None:
        return self._get("/feed/heatlists/", {"cyi": cyi, "id": competitor_id, "type": competitor_type})

