#!/usr/bin/env python3
"""Audit a running private runtime; never print its environment or process argv."""

import json
import subprocess
import sys


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def main():
    require(len(sys.argv) == 2, "Usage: check-soloist-container.py CONTAINER_ID")
    container = json.loads(
        subprocess.check_output(["docker", "inspect", sys.argv[1]], text=True)
    )[0]
    host = container["HostConfig"]
    require(container["Config"]["User"] == "65531:65531", "Unexpected runtime UID/GID")
    require(container["State"]["Running"], "Runtime is not running")
    require(
        not host.get("PidMode") and not host.get("Privileged") and not host.get("Init"),
        "Private PID-1 boundary missing",
    )
    require(
        host["NetworkMode"] != "host",
        "Host network exposes the unauthenticated WebSocket",
    )
    require(
        host["ReadonlyRootfs"]
        and host["CapDrop"] == ["ALL"]
        and not host.get("CapAdd"),
        "Filesystem/capability boundary missing",
    )
    require("no-new-privileges:true" in host["SecurityOpt"], "NNP missing")
    require(
        not host.get("Devices") and not host.get("DeviceRequests"),
        "Host devices forbidden",
    )
    require(
        0 < host["PidsLimit"] <= 48 and 0 < host["Memory"] <= 384 * 1024 * 1024,
        "Runtime resource bounds missing",
    )
    allowed = {"/runtime", "/run/secrets", "/config", "/state"}
    require(
        {m["Destination"] for m in container["Mounts"] if m["Type"] != "tmpfs"}
        == allowed,
        "Unexpected runtime mount",
    )
    require(
        all(
            not m["RW"]
            for m in container["Mounts"]
            if m["Destination"] in allowed - {"/state"}
        ),
        "Mutable key/config/binary mount",
    )
    ports = host.get("PortBindings") or {}
    require(
        set(ports) == {"8097/tcp"}
        and all(p["HostIp"] == "127.0.0.1" for p in ports["8097/tcp"]),
        "Unexpected API/WebSocket publication",
    )
    for item in container["Config"].get("Env") or []:
        require(
            "api_key" not in item.lower() and "api-key" not in item.lower(),
            "API key environment entry forbidden",
        )
    print(
        "PASS: running Soloist container isolation, mounts, resources and private publication"
    )


if __name__ == "__main__":
    main()
