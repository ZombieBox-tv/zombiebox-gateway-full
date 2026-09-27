#!/usr/bin/env python3
"""Build and run an isolated synthetic-only PulseAudio/FFmpeg QA fixture."""

import array
import io
import json
import math
import secrets
import subprocess
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "gateway-core/wrappers/soloist-audio"
BASE_IMAGE = "zombie-box-tv/gateway:0.1.0-dev.126-qa"
BASE_IMAGE_ID = (
    "sha256:3e71dc2bd06a064b2c0adbd7e55be4096700b2d9fd383af59019e0b9d079f9e3"
)
CAPTURE_LIMIT_BYTES = 1_048_576


def docker(*args, timeout=30):
    try:
        result = subprocess.run(
            ["docker", *args],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"Docker {args[0]} exceeded its {timeout}s limit") from error
    if result.returncode:
        details = "\n".join(result.stdout.rstrip().splitlines()[-30:])
        raise RuntimeError(
            f"Docker {args[0]} failed with status {result.returncode}:\n{details}"
        )
    return result.stdout.strip()


def inspect_json(*args):
    return json.loads(docker(*args))[0]


def docker_bytes(*args, timeout=10):
    try:
        result = subprocess.run(
            ["docker", *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"Docker {args[0]} exceeded its {timeout}s limit") from error
    if result.returncode:
        raise RuntimeError(f"Docker {args[0]} failed with status {result.returncode}")
    return result.stdout


def verify_signal(data):
    with wave.open(io.BytesIO(data), "rb") as recording:
        channels = recording.getnchannels()
        rate = recording.getframerate()
        width = recording.getsampwidth()
        frames_count = recording.getnframes()
        frames = recording.readframes(frames_count)

    assert channels == 2, f"expected stereo PCM, got {channels} channel(s)"
    assert rate == 44100, f"expected 44100Hz PCM, got {rate}Hz"
    assert width == 2, f"expected 16-bit samples, got {width * 8}-bit PCM"
    assert int(rate * 3) <= frames_count <= int(rate * 4.5), (
        f"capture duration was outside 3-4.5s: {frames_count / rate:.3f}s"
    )
    assert len(frames) == frames_count * channels * width

    samples = array.array("h")
    samples.frombytes(frames)
    if sys.byteorder != "little":
        samples.byteswap()

    peaks = [0, 0]
    square_sums = [0, 0]
    crossing_frames = []
    previous_left = samples[0]
    for index in range(0, len(samples), channels):
        left, right = samples[index], samples[index + 1]
        peaks[0] = max(peaks[0], abs(left))
        peaks[1] = max(peaks[1], abs(right))
        square_sums[0] += left * left
        square_sums[1] += right * right
        if previous_left <= 0 < left:
            crossing_frames.append(index // channels)
        previous_left = left

    duration = frames_count / rate
    rms = [math.sqrt(total / frames_count) for total in square_sums]
    assert len(crossing_frames) >= 1000, (
        f"expected a sustained tone, saw {len(crossing_frames)} positive crossings"
    )
    frequency = (
        (len(crossing_frames) - 1) * rate / (crossing_frames[-1] - crossing_frames[0])
    )
    assert all(level > 1000 for level in rms), "captured PCM was silent"
    assert all(peak > 1500 for peak in peaks), "captured PCM peak was too quiet"
    assert 400 <= frequency <= 480, f"synthetic tone estimate was {frequency:.1f}Hz"
    return duration, rms, peaks, frequency


def verify_isolation(container):
    inspected = inspect_json("container", "inspect", container)
    config = inspected["HostConfig"]
    assert config["NetworkMode"] == "none", "container network was not disabled"
    assert not config.get("Devices"), "container received a host device"
    assert not config.get("DeviceRequests"), "container received a device request"
    assert not config.get("Binds"), "container received a host bind"
    assert not config.get("Mounts"), "container received a host mount"
    assert set((config.get("Tmpfs") or {}).keys()) == {"/tmp"}, (
        "container writable storage was not limited to /tmp"
    )
    assert config["ReadonlyRootfs"] is True, "container root was writable"
    assert "ALL" in config["CapDrop"], "container retained Linux capabilities"
    assert "no-new-privileges:true" in config["SecurityOpt"], (
        "container did not disable privilege escalation"
    )
    assert config["Memory"] == 256 * 1024 * 1024, "container memory limit changed"
    assert config["NanoCpus"] == 500_000_000, "container CPU limit changed"
    assert config["PidsLimit"] == 64, "container PID limit changed"
    assert inspected["Config"]["User"] == "65532:65532", "container was not non-root"
    assert inspected["HostConfig"]["RestartPolicy"]["Name"] in ("", "no"), (
        "container has a restart policy"
    )
    mounts = inspected.get("Mounts", [])
    assert all(
        mount["Type"] == "tmpfs" and mount["Destination"] == "/tmp" for mount in mounts
    ), "container exposed a mount other than its private /tmp"


def quiet_docker(*args, timeout=10):
    try:
        return subprocess.run(
            ["docker", *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def cleanup(container, image):
    quiet_docker("stop", "--time=2", container, timeout=5)
    quiet_docker("rm", "--force", container, timeout=10)
    quiet_docker("image", "rm", "--force", image, timeout=10)
    containers = quiet_docker("ps", "--all", "--format", "{{.Names}}", timeout=10)
    images = quiet_docker(
        "image", "ls", "--quiet", "--filter", f"reference={image}", timeout=10
    )
    if (
        containers is None
        or images is None
        or containers.returncode
        or images.returncode
    ):
        return False
    return container not in containers.stdout.splitlines() and not images.stdout.strip()


def run_fixture():
    base = inspect_json("image", "inspect", BASE_IMAGE)
    if base["Id"] != BASE_IMAGE_ID:
        raise SystemExit(
            f"Full QA base image ID mismatch: expected {BASE_IMAGE_ID}, got {base['Id']}"
        )
    print(f"Using pinned local Full QA image {BASE_IMAGE}")

    suffix = secrets.token_hex(6)
    image = f"zombiebox-qa/soloist-audio:{suffix}"
    container = f"zombiebox-soloist-audio-{suffix}"
    try:
        docker(
            "build",
            "--pull=false",
            "--build-arg",
            f"BASE_IMAGE={BASE_IMAGE}",
            "--tag",
            image,
            str(WRAPPER),
            timeout=180,
        )
        docker(
            "run",
            "--detach",
            "--name",
            container,
            "--network",
            "none",
            "--memory=256m",
            "--cpus=0.5",
            "--pids-limit=64",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,noexec,size=16777216,mode=1777",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            image,
            timeout=10,
        )
        deadline = time.monotonic() + 20
        while True:
            state = inspect_json("container", "inspect", container)["State"]
            if not state["Running"]:
                raise RuntimeError(
                    f"synthetic audio container exited early with {state['ExitCode']}"
                )
            marker = subprocess.run(
                ["docker", "exec", container, "test", "-f", "/tmp/capture-ready"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=5,
            )
            if marker.returncode == 0:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    "synthetic audio capture did not become ready within 20s"
                )
            time.sleep(0.2)

        verify_isolation(container)
        print(
            "PASS: Docker inspection confirms network isolation, no host audio devices or binds, and bounded resources"
        )

        output = docker("logs", container)
        expected = (
            "PASS: private PulseAudio has one null sink and only its monitor source",
            "PASS: no host sound device is available and Full FFmpeg has PulseAudio input/output",
            "PASS: captured only the synthetic 440Hz tone from soloist_qa_sink.monitor as bounded PCM WAV",
        )
        if any(line not in output.splitlines() for line in expected):
            raise RuntimeError(
                "synthetic audio entrypoint did not report all expected checks"
            )

        capture = docker_bytes("exec", container, "cat", "/tmp/capture.wav", timeout=5)
        if len(capture) > CAPTURE_LIMIT_BYTES:
            raise RuntimeError("synthetic PCM capture exceeded its size bound")
        duration, rms, peaks, frequency = verify_signal(capture)

        docker("exec", container, "touch", "/tmp/release", timeout=5)
        exit_code = int(docker("wait", container, timeout=10))
        if exit_code:
            raise RuntimeError(
                f"isolated synthetic audio container exited with {exit_code}"
            )
        state = inspect_json("container", "inspect", container)["State"]
        if state["Running"] or state["Status"] != "exited" or state["ExitCode"] != 0:
            raise RuntimeError("synthetic audio container did not exit cleanly")

        print(
            "PASS: synthetic PCM is stereo/44100Hz/16-bit, "
            f"{duration:.3f}s, channel RMS={rms[0]:.0f}/{rms[1]:.0f}, "
            f"peaks={peaks[0]}/{peaks[1]}, tone={frequency:.1f}Hz"
        )
    finally:
        if not cleanup(container, image):
            print("FAIL: Docker cleanup could not be confirmed", file=sys.stderr)
            raise SystemExit(1)
    print(
        "PASS: temporary QA container and image were removed; no process was left running"
    )


if __name__ == "__main__":
    run_fixture()
