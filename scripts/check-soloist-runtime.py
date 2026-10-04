#!/usr/bin/env python3
"""Exercise production provisioning/isolation with dummy material, never an account."""

import hashlib
import io
import json
import os
import secrets
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    env = {
        **os.environ,
        "ZOMBIE_RELAY_ADMIN_TOKEN": "synthetic-relay-token-01234567890123456789",
    }
    config = json.loads(
        subprocess.check_output(
            [
                "docker",
                "compose",
                "-f",
                "compose.yaml",
                "-f",
                "compose.soloist.yaml",
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
    )
    project = "zb006-lab-" + secrets.token_hex(4)
    token = secrets.token_hex(32)
    with tempfile.TemporaryDirectory(prefix=project) as temporary:
        folder = Path(temporary)
        archive = folder / "soloist.tar.gz"
        # A dummy process accepts the launcher's arguments but never emits WS or PCM.
        executable = b"#!/bin/sh\nexec sleep 3600\n"
        with tarfile.open(archive, "w:gz") as target:
            entry = tarfile.TarInfo("soloist")
            entry.size, entry.mode = len(executable), 0o555
            target.addfile(entry, io.BytesIO(executable))
        key = folder / "key"
        key.write_text("synthetic-key-only\n")
        key.chmod(0o600)
        worker = folder / "worker.json"
        worker.write_text(
            json.dumps(
                {
                    "mode": "spotify",
                    "listen": "127.0.0.1:8097",
                    "token": token,
                    "stateDir": "/state",
                }
            )
        )
        initializer = config["services"]["soloist-init"]
        runtime = config["services"]["soloist"]
        for service in (initializer, runtime):
            service.pop("profiles", None)
            service.pop("build", None)
            service["restart"] = "no"
        initializer["environment"]["ZOMBIE_SOLOIST_ARCHIVE_SHA256"] = hashlib.sha256(
            archive.read_bytes()
        ).hexdigest()
        inputs = {
            "/provision/soloist.tar.gz": archive,
            "/provision/key": key,
            "/provision/worker.json": worker,
        }
        for mount in initializer["volumes"]:
            if mount["target"] in inputs:
                mount["source"] = str(inputs[mount["target"]])
        # This disposable bridge proves the API boundary; it does not prove LAN discovery.
        runtime["networks"] = {"default": {"interface_name": "api0"}}
        runtime["ports"] = [{"target": 8097, "host_ip": "127.0.0.1", "protocol": "tcp"}]
        runtime["ulimits"] = {"core": 0}
        compose_file = folder / "compose.json"
        compose_file.write_text(
            json.dumps(
                {
                    "services": {"soloist-init": initializer, "soloist": runtime},
                    "volumes": {
                        v: {} for v in config["volumes"] if v.startswith("soloist-")
                    },
                }
            )
        )
        compose = ["docker", "compose", "-p", project, "-f", str(compose_file)]
        try:
            started = subprocess.run(compose + ["up", "-d"], stdout=subprocess.DEVNULL)
            if started.returncode:
                # The initializer contains only this script's dummy material.
                subprocess.run(
                    compose + ["logs", "--no-log-prefix", "soloist-init"], check=True
                )
                raise SystemExit("Dummy runtime provisioning failed")
            container = subprocess.check_output(
                compose + ["ps", "-q", "soloist"], text=True
            ).strip()
            subprocess.run(
                [
                    "python3",
                    str(ROOT / "scripts/check-soloist-container.py"),
                    container,
                ],
                check=True,
            )
            port = subprocess.check_output(
                compose + ["port", "soloist", "8097"], text=True
            ).strip()

            def request(path, authenticated=True, method="GET"):
                headers = {"Authorization": "Bearer " + token} if authenticated else {}
                call = urllib.request.Request(
                    "http://" + port + path, headers=headers, method=method
                )
                try:
                    with urllib.request.urlopen(call, timeout=5) as response:
                        return response.status, response.read(65536)
                except urllib.error.HTTPError as error:
                    return error.code, error.read(65536)

            deadline = time.monotonic() + 5
            while True:
                try:
                    assert request("/health", False)[0] == 401
                    break
                except urllib.error.URLError:
                    if time.monotonic() >= deadline:
                        raise SystemExit("Private runtime API did not start")
                    time.sleep(0.1)
            assert request("/health")[0] == 503
            assert request("/activate", method="POST")[0] == 204
            status, body = request("/health")
            assert (
                status == 200
                and not json.loads(body)["ready"]
                and not json.loads(body)["audioReady"]
            )
            assert request("/audio")[0] == 503
            print(
                "PASS: production provisioning/activation, private authenticated API and absent-output rejection using dummy material; no LAN/account/device acceptance"
            )
        finally:
            subprocess.run(
                compose + ["down", "-v"], check=True, stdout=subprocess.DEVNULL
            )


if __name__ == "__main__":
    main()
