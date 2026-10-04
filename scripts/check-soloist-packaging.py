#!/usr/bin/env python3
"""Inspect the rendered optional runtime without opening Docker's daemon."""

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def main():
    env = {
        **os.environ,
        "ZOMBIE_RELAY_ADMIN_TOKEN": "synthetic-check-token-01234567890123456789",
    }
    rendered = subprocess.check_output(
        [
            "docker",
            "compose",
            "-f",
            "compose.yaml",
            "-f",
            "compose.soloist.yaml",
            "--profile",
            "spotify",
            "--profile",
            "soloist",
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        env=env,
        text=True,
    )
    services = json.loads(rendered)["services"]
    runtime = services["soloist"]
    require(runtime["user"] == "65531:65531", "Soloist must use its dedicated UID/GID")
    require(
        "65531" not in services["gateway"]["user"].split(":"),
        "Gateway must use a different UID/GID",
    )
    require(
        not runtime.get("pid")
        and not runtime.get("init")
        and not runtime.get("privileged"),
        "Private PID-1 boundary required",
    )
    require(
        runtime["read_only"]
        and runtime["cap_drop"] == ["ALL"]
        and not runtime.get("cap_add"),
        "Runtime capability/filesystem isolation missing",
    )
    require("no-new-privileges:true" in runtime["security_opt"], "NNP missing")
    require(not runtime.get("devices"), "Host audio devices forbidden")
    require(
        runtime["ports"][0]["host_ip"] == "127.0.0.1"
        and runtime["ports"][0]["target"] == 8097,
        "Only the private bearer API may be published",
    )
    require(
        runtime["networks"]["default"]["interface_name"] == "api0",
        "Private API interface missing",
    )
    require(
        runtime["networks"]["soloist-lan"]["interface_name"] == "lan0",
        "Connect LAN attachment missing",
    )
    allowed = {"/runtime", "/run/secrets", "/config", "/state"}
    require(
        {v["target"] for v in runtime["volumes"]} == allowed, "Unexpected Soloist mount"
    )
    require(
        all(v.get("read_only") for v in runtime["volumes"] if v["target"] != "/state"),
        "Mutable binary/key/config mount",
    )
    secret = next(
        v["source"] for v in runtime["volumes"] if v["target"] == "/run/secrets"
    )
    for name, service in services.items():
        if name in {"soloist", "soloist-init"}:
            continue
        require(
            all(
                v.get("source") != secret
                and "soloist/provision" not in v.get("source", "")
                for v in service.get("volumes", [])
            ),
            f"Secret shared with {name}",
        )
    require(
        not runtime.get("environment"), "Do not put API keys in runtime environment"
    )
    print(
        "PASS: isolated Soloist profile, private API, exclusive key mounts, bounded resources"
    )


if __name__ == "__main__":
    main()
