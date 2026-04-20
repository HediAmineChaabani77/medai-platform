import asyncio
import logging

import httpx

log = logging.getLogger(__name__)


class ConnectivityProbe:
    """Probes external reachability at a fixed interval. Last state cached in-memory."""

    def __init__(self, settings, client: httpx.AsyncClient | None = None):
        self.url = settings.connectivity_probe_url
        self.interval = settings.connectivity_probe_interval
        self._client = client
        self._online = False
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def is_online(self) -> bool:
        return self._online

    async def _probe_once(self) -> bool:
        client = self._client or httpx.AsyncClient(timeout=3.0)
        try:
            r = await client.head(self.url)
            return r.status_code < 500
        except Exception:
            return False
        finally:
            if self._client is None:
                await client.aclose()

    async def _loop(self):
        while not self._stop.is_set():
            self._online = await self._probe_once()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                pass

    async def start(self):
        self._online = await self._probe_once()
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        self._stop.set()
        if self._task:
            await self._task
