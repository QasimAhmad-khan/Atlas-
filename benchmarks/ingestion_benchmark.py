from __future__ import annotations

import asyncio
import ctypes
import json
import os
import statistics
import time
from pathlib import Path

from atlaspipe.crawler.fetcher import FetchResult
from atlaspipe.db.repositories import InMemoryRepository
from atlaspipe.pipeline.pipeline import CrawlPipeline
from atlaspipe.schemas.page import PageRecord


class SyntheticFetcher:
    def __init__(self, starts: dict[str, float]) -> None:
        self._starts = starts

    async def fetch(self, url: str) -> FetchResult:
        index = url.rsplit("-", maxsplit=1)[-1]
        self._starts[url] = time.perf_counter()
        body = (
            "<html><head>"
            f"<title>Benchmark page {index}</title>"
            f"<meta name='description' content='Controlled fixture page {index}'>"
            "</head><body><a href='/next'>Next</a></body></html>"
        ).encode()
        return FetchResult(
            url=url,
            final_url=url,
            status=200,
            headers={"content-type": "text/html"},
            body=body,
            response_time_ms=1,
        )


class TimedRepository(InMemoryRepository):
    def __init__(self, starts: dict[str, float], latencies_ms: list[float]) -> None:
        super().__init__(jobs={}, pages={})
        self._starts = starts
        self._latencies_ms = latencies_ms

    async def save_pages(self, pages: list[PageRecord]) -> int:
        now = time.perf_counter()
        for page in pages:
            started = self._starts.get(page.url)
            if started is not None:
                self._latencies_ms.append((now - started) * 1000)
        return await super().save_pages(pages)


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = min(len(sorted_values) - 1, int(round((percent / 100) * (len(sorted_values) - 1))))
    return sorted_values[index]


class ProcessMemoryCounter(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


PSAPI = ctypes.WinDLL("psapi.dll") if os.name == "nt" else None
KERNEL32 = ctypes.WinDLL("kernel32.dll") if os.name == "nt" else None

if PSAPI is not None and KERNEL32 is not None:
    KERNEL32.GetCurrentProcess.restype = ctypes.c_void_p
    PSAPI.GetProcessMemoryInfo.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ProcessMemoryCounter),
        ctypes.c_ulong,
    ]
    PSAPI.GetProcessMemoryInfo.restype = ctypes.c_int


def current_rss_mb() -> float:
    if PSAPI is None or KERNEL32 is None:
        return 0.0
    counter = ProcessMemoryCounter()
    counter.cb = ctypes.sizeof(ProcessMemoryCounter)
    ok = PSAPI.GetProcessMemoryInfo(
        KERNEL32.GetCurrentProcess(),
        ctypes.byref(counter),
        counter.cb,
    )
    if not ok:
        return 0.0
    return float(counter.WorkingSetSize / (1024 * 1024))


async def monitor_memory(stop: asyncio.Event, samples: list[float]) -> None:
    while not stop.is_set():
        samples.append(current_rss_mb())
        await asyncio.sleep(0.05)


async def run_scale(size: int, concurrency: int) -> dict[str, float | int]:
    starts: dict[str, float] = {}
    latencies_ms: list[float] = []
    repository = TimedRepository(starts, latencies_ms)
    pipeline = CrawlPipeline(
        fetcher=SyntheticFetcher(starts),
        repository=repository,
        max_concurrency=concurrency,
        per_domain_concurrency=max(1, min(concurrency, 5)),
        requests_per_second=1_000_000,
        batch_size=500,
    )
    urls = [f"https://benchmark.example/page-{index}" for index in range(size)]
    memory_samples: list[float] = []
    stop_monitor = asyncio.Event()
    monitor = asyncio.create_task(monitor_memory(stop_monitor, memory_samples))
    started = time.perf_counter()
    try:
        result = await pipeline.run(urls)
        elapsed = time.perf_counter() - started
    finally:
        stop_monitor.set()
        await monitor

    return {
        "records": size,
        "concurrency": concurrency,
        "elapsed_seconds": round(elapsed, 6),
        "records_per_second": round(result.saved / elapsed, 2) if elapsed else 0,
        "latency_p50_ms": round(statistics.median(latencies_ms), 3) if latencies_ms else 0,
        "latency_p95_ms": round(percentile(latencies_ms, 95), 3),
        "peak_memory_mb": round(max(memory_samples), 2) if memory_samples else 0,
        "saved": result.saved,
        "failed": result.failed,
        "duplicates": result.duplicates,
    }


async def main_async() -> list[dict[str, float | int]]:
    results = []
    for size in [10_000, 50_000, 100_000]:
        for concurrency in [1, 5, 10, 25, 50]:
            results.append(await run_scale(size, concurrency))
    return results


def main() -> None:
    results = asyncio.run(main_async())
    output = Path("benchmarks/results/ingestion_benchmark.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
