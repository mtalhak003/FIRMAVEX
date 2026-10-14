"""Offline descriptive negotiation; never a claim about currently selected tools."""

import json
import platform
from firmavex.backends.api import profiles

LOCAL_COMMANDS = frozenset(
    {
        "capabilities",
        "doctor",
        "backend_check",
        "backend_prepare",
        "backend_execute",
        "backend_inspect",
        "backend_reproduce",
        "backend_export",
    }
)


def describe():
    system, architecture = platform.system(), platform.machine()
    record = {
        "interface_version": 1,
        "worker_protocol_versions": [1],
        "transport": "owned_stdio_pipes",
        "network_listener": False,
        "commands": sorted(LOCAL_COMMANDS),
        "profiles": [profile.to_dict() for profile in profiles.values()],
        "host": {"system": system, "architecture": architecture},
        "support": {
            "current_runtime_qualification": "not_probed",
            "native_unified_execution": (
                "unsupported"
                if system == "Darwin"
                else "requires_matching_qualified_runtime"
            ),
            "qualified_baseline_examples": ["Windows x64", "Ubuntu x64"],
            "macos": "desktop_preview_only",
            "evidence": "https://github.com/mtalhak003/FIRMAVEX/actions/runs/38590752705",
        },
        "policy": {
            "trust": ["trusted_example", "trusted_project"],
            "untrusted_workloads": "rejected",
            "sandboxed": False,
            "remote_execution": False,
            "online_installation": "not_exposed",
            "concurrency": "one_active_job_per_session",
            "automatic_retries": False,
            "job_registry": "ephemeral; persisted engine records remain authoritative",
            "resource_limits": "backend-specific; no cross-backend aggregate quota",
            "maximum_retained_jobs": 32,
            "maximum_connection_requests": 65536,
            "maximum_worker_seconds": 86400,
        },
    }

    return json.loads(json.dumps(record, allow_nan=False))
