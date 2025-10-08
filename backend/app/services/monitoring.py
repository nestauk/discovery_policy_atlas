"""
Resource monitoring utility for tracking CPU, RAM, and async task usage.

Provides lightweight monitoring for analysis and synthesis services.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


logger = logging.getLogger(__name__)


@dataclass
class ResourceSnapshot:
    """A snapshot of resource usage at a point in time."""

    label: str
    timestamp: str
    cpu_percent: float
    memory_mb: float
    threads: int
    active_tasks: int
    elapsed_seconds: float = 0.0

    def __str__(self) -> str:
        return (
            f"{self.label}: "
            f"CPU={self.cpu_percent:.1f}% "
            f"RAM={self.memory_mb:.1f}MB "
            f"Threads={self.threads} "
            f"Tasks={self.active_tasks} "
            f"Elapsed={self.elapsed_seconds:.1f}s"
        )


@dataclass
class ResourceMonitor:
    """
    Lightweight resource monitor for tracking service performance.

    Usage:
        monitor = ResourceMonitor("AnalysisService")
        monitor.start()

        monitor.log_snapshot("Before parsing")
        # ... do work ...
        monitor.log_snapshot("After parsing")

        summary = monitor.get_summary()
    """

    service_name: str
    start_time: Optional[float] = None
    snapshots: List[ResourceSnapshot] = field(default_factory=list)
    metrics: Dict[str, any] = field(default_factory=dict)

    def start(self) -> None:
        """Start monitoring."""
        self.start_time = time.time()
        self.snapshots = []
        self.metrics = {}
        if not PSUTIL_AVAILABLE:
            logger.warning(
                f"[{self.service_name}] psutil not available - resource monitoring limited"
            )

    def snapshot(self, label: str) -> ResourceSnapshot:
        """
        Take a snapshot of current resource usage.

        Args:
            label: Descriptive label for this snapshot

        Returns:
            ResourceSnapshot with current metrics
        """
        if not PSUTIL_AVAILABLE:
            return ResourceSnapshot(
                label=label,
                timestamp=datetime.now().isoformat(),
                cpu_percent=0.0,
                memory_mb=0.0,
                threads=0,
                active_tasks=len(asyncio.all_tasks()),
                elapsed_seconds=time.time() - (self.start_time or time.time()),
            )

        try:
            process = psutil.Process()

            snapshot = ResourceSnapshot(
                label=label,
                timestamp=datetime.now().isoformat(),
                cpu_percent=process.cpu_percent(interval=0.1),
                memory_mb=process.memory_info().rss / (1024 * 1024),
                threads=process.num_threads(),
                active_tasks=len(asyncio.all_tasks()),
                elapsed_seconds=time.time() - (self.start_time or time.time()),
            )

            self.snapshots.append(snapshot)
            return snapshot

        except Exception as e:
            logger.warning(f"Failed to capture resource snapshot: {e}")
            return ResourceSnapshot(
                label=label,
                timestamp=datetime.now().isoformat(),
                cpu_percent=0.0,
                memory_mb=0.0,
                threads=0,
                active_tasks=0,
                elapsed_seconds=time.time() - (self.start_time or time.time()),
            )

    def log_snapshot(self, label: str) -> ResourceSnapshot:
        """
        Take a snapshot and log it.

        Args:
            label: Descriptive label for this snapshot

        Returns:
            ResourceSnapshot
        """
        snapshot = self.snapshot(label)
        logger.info(f"[{self.service_name}] {snapshot}")
        return snapshot

    def record_metric(self, key: str, value: any) -> None:
        """
        Record a custom metric.

        Args:
            key: Metric name
            value: Metric value
        """
        self.metrics[key] = value

    def get_summary(self) -> Dict[str, any]:
        """
        Get a summary of all monitoring data.

        Returns:
            Dictionary with summary statistics
        """
        if not self.snapshots:
            return {
                "service_name": self.service_name,
                "snapshots_count": 0,
                "custom_metrics": self.metrics,
            }

        cpu_values = [s.cpu_percent for s in self.snapshots]
        memory_values = [s.memory_mb for s in self.snapshots]

        total_time = self.snapshots[-1].elapsed_seconds if self.snapshots else 0

        return {
            "service_name": self.service_name,
            "total_time_seconds": total_time,
            "snapshots_count": len(self.snapshots),
            "cpu": {
                "min": min(cpu_values) if cpu_values else 0,
                "max": max(cpu_values) if cpu_values else 0,
                "avg": sum(cpu_values) / len(cpu_values) if cpu_values else 0,
            },
            "memory": {
                "min_mb": min(memory_values) if memory_values else 0,
                "max_mb": max(memory_values) if memory_values else 0,
                "avg_mb": sum(memory_values) / len(memory_values)
                if memory_values
                else 0,
            },
            "max_active_tasks": max(
                (s.active_tasks for s in self.snapshots), default=0
            ),
            "custom_metrics": self.metrics,
            "snapshots": [
                {
                    "label": s.label,
                    "timestamp": s.timestamp,
                    "cpu_percent": s.cpu_percent,
                    "memory_mb": s.memory_mb,
                    "active_tasks": s.active_tasks,
                    "elapsed_seconds": s.elapsed_seconds,
                }
                for s in self.snapshots
            ],
        }

    def log_summary(self) -> None:
        """Log a summary of all monitoring data."""
        summary = self.get_summary()

        logger.info(
            f"[{self.service_name}] SUMMARY: "
            f"Time={summary['total_time_seconds']:.1f}s "
            f"CPU(avg={summary['cpu']['avg']:.1f}%, max={summary['cpu']['max']:.1f}%) "
            f"RAM(avg={summary['memory']['avg_mb']:.1f}MB, max={summary['memory']['max_mb']:.1f}MB) "
            f"MaxTasks={summary['max_active_tasks']}"
        )

        if self.metrics:
            logger.info(f"[{self.service_name}] Custom metrics: {self.metrics}")


class StageTimer:
    """
    Context manager for timing individual stages with resource monitoring.

    Usage:
        monitor = ResourceMonitor("MyService")
        monitor.start()

        with StageTimer(monitor, "parsing"):
            # ... do parsing work ...
            pass
    """

    def __init__(self, monitor: ResourceMonitor, stage_name: str):
        self.monitor = monitor
        self.stage_name = stage_name
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        self.monitor.log_snapshot(f"START {self.stage_name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        self.monitor.record_metric(f"{self.stage_name}_duration_seconds", duration)
        self.monitor.log_snapshot(f"END {self.stage_name} ({duration:.1f}s)")
        return False


async def monitor_async_task(
    coro, monitor: ResourceMonitor, task_name: str, timeout: Optional[float] = None
):
    """
    Monitor an async task with optional timeout.

    Args:
        coro: Coroutine to execute
        monitor: ResourceMonitor instance
        task_name: Name of the task for logging
        timeout: Optional timeout in seconds

    Returns:
        Result of the coroutine

    Raises:
        asyncio.TimeoutError: If timeout is exceeded
    """
    start_time = time.time()
    monitor.log_snapshot(f"START {task_name}")

    try:
        if timeout:
            result = await asyncio.wait_for(coro, timeout=timeout)
        else:
            result = await coro

        duration = time.time() - start_time
        monitor.record_metric(f"{task_name}_duration_seconds", duration)
        monitor.log_snapshot(f"END {task_name} ({duration:.1f}s)")

        return result

    except asyncio.TimeoutError:
        duration = time.time() - start_time
        logger.error(
            f"[{monitor.service_name}] {task_name} TIMEOUT after {duration:.1f}s"
        )
        monitor.record_metric(f"{task_name}_timeout", True)
        raise

    except Exception as e:
        duration = time.time() - start_time
        logger.error(
            f"[{monitor.service_name}] {task_name} FAILED after {duration:.1f}s: {e}"
        )
        monitor.record_metric(f"{task_name}_error", str(e))
        raise
