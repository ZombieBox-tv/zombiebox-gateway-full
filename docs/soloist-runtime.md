# ZB-006: optional Soloist runtime evaluation

This is an unreleased Full amd64 candidate. Its source, unit tests and rendered
Compose boundary can be checked independently of Docker execution. Passing those
checks does not certify the runtime image, a Spotify account, or a TV. See the
central ZB-006 handoff for the dated execution results. Keep the current QA
candidate's other providers, volumes, signing identity and installed APK intact.

## Runtime contract

`compose.soloist.yaml` is an opt-in override of the current Full Compose file.
It selects new gateway/Spotify image identities and adds an independently
isolated runtime. It does not change existing image identities or publish images.
The runtime image contains GPL worker code, Debian libraries, PipeWire and
WirePlumber; **no Soloist binary or API key is in its build context/layers**.
A user obtains the binary from Spotify and supplies their own key. The offline
handoff must exclude the user's archive, key, session and runtime volumes.

The no-network initializer validates the supplied archive's frozen SHA256,
extracts it into a dedicated binary volume, and copies the key into an exclusive
secret volume as UID/GID 65531, mode 0400. Neither Gateway nor the ordinary Spotify
worker mounts these volumes. The initializer has only CHOWN/DAC_OVERRIDE; the
long-lived runtime drops every capability and runs as PID 1, UID/GID 65531 with
NNP, seccomp, a read-only root and bounded tmpfs/state/process/memory/CPU budgets.
Gateway's UID and GID must both differ from 65531.

The launcher validates this process boundary before any key read. It verifies the
mounted executable digest and restrictive secret ownership; only the child
launcher reads the key and passes the documented `--api-key` argument. Raw child
stdout/stderr and core dumps are disabled. The key remains visible to processes
inside that runtime and to host observers permitted to inspect container process
arguments; this boundary protects the other application containers and clients,
not an administrator or an untrusted host. Do not use `docker top`, `/proc/*/cmdline`
exports, command tracing, or state-volume exports as diagnostics.

WebSocket `127.0.0.1:8096` is unpublished in the container network namespace. The
bearer-only semantic API binds exclusively to Docker's `api0` bridge interface;
only host loopback port 8097 is published. A separate LAN attachment (`lan0`)
supports Connect discovery without sharing the host network. No host audio,
PipeWire/Pulse socket, D-Bus socket, Docker socket, `/proc`, or audio device is
mounted. PipeWire exposes one private null sink; its hardware discovery policies
are disabled. Capture explicitly targets `zombiebox_soloist` with monitor mode.

The ordinary Spotify worker attempts go-librespot first. Before any produced
primary audio, daemon failure, an observed audio-key refusal, or ten seconds of
active playback without output can activate Soloist once. Idle/pairing and paused
states do not trigger that timeout. The primary process is stopped before
activation. Once a backend produces audio, it is pinned for the worker lifetime;
restart the Spotify worker to retry go-librespot. An unavailable fallback does
not stop Gateway or other providers. Startup/pairing and PCM readiness are separate.

At least 100 ms of advancing non-silent s16le stereo 44100 Hz PCM is required.
Silence, EOF, capture failure, disconnect/logout and expired one-second evidence
cannot establish readiness. A muted/silent track may conservatively remain
unready; use an audible non-silent test interval. The bounded subscriber queue
has no replay or disk storage; a slow consumer is disconnected. Controls and
metadata use the existing bounded WebSocket adapter and session/authentication
fences. Provider status authorizes a typed PCM source only for the exact contract;
Gateway additionally requires fresh advancing `audio-track-pcm-stream` device
probe evidence. Explicit playback modes cannot bypass that gate. go-librespot
continues to expose encoded MP3.

## Maintainer gates before physical evaluation

```sh
make -C ../gateway-core soloist-check
make soloist-host-check
make -C ../gateway-core soloist-synthetic-check
make soloist-runtime-check
```

The last command builds the glibc image and runs a generated-tone check through
the production private PipeWire sink, monitor and PCM reader. It uses neither a
Spotify binary/key nor a physical device. Do not proceed until it passes. Retain
image IDs, `runtime-packages.txt`, dependency source/notice receipts and the
matching first-party commits with the private handoff. Build with the new image
identities; never replace an older candidate as a workaround.

## Docker-only runtime provisioning

The operator needs Docker Engine, Compose with `interface_name`/`gw_priority`
support (2.36+), the candidate images, an official user-supplied Soloist archive,
a private mode-0600 key file and the existing Full Spotify worker configuration.
No host Go, Python, Node, FFmpeg or audio daemon is needed for execution. The
Python scripts above are maintainer checks, not end-user runtime dependencies.

Place the official archive at `.local/soloist/provision/soloist.tar.gz` and the
key file at `.local/soloist/provision/key` under the selected installation's
`ZOMBIE_RUNTIME_ROOT`, not under a hardcoded source checkout.

The Docker installer's placement contract is:

| Selection | Compose installation directory |
| --- | --- |
| Default | Directory where `install-docker.sh` is invoked |
| `--directory PATH` | The explicitly selected directory |
| `--user-data` | `${XDG_DATA_HOME:-$HOME/.local/share}/zombiebox/full/releases/<version>` |

For this private source-Compose evaluation, use the selected QA installation
directory as `ZOMBIE_RUNTIME_ROOT`. Provisioning input then resides at
`<installation>/.local/soloist/provision/key` in either placement mode. Keep the
same runtime root and Compose project on every initialization, start and control
command; a different project selects different named volumes. Existing key,
configuration and account state must not be moved automatically.

```sh
cd /path/to/the/selected/qa-compose-directory
export ZOMBIE_RUNTIME_ROOT="$(pwd -P)"
```

The published standalone installer uses named configuration volumes and does not
yet distribute this unreleased Soloist override. Its `--user-data` flag selects
installation placement; it is not an argument to `docker compose`. Do not apply
the source override to an older standalone bundle assuming its worker config
mounts are compatible. `install.sh` is the separate source-development helper,
with its own runtime-root defaults; it is not the public `install-docker.sh`.

The default
archive hash freezes the already recorded private 1.3.8.82 trial
(`76e344ff47b571d9974ac7b85d0ab301ef01f2574d7ccbef01d4953635769a5b`).
For a newer officially obtained archive, independently verify and record its
version/expiry/hash, then explicitly set `ZOMBIE_SOLOIST_ARCHIVE_SHA256` before
initialization. Runtime never downloads `latest`, mutates an old image, shares a
key, or republishes Spotify's binary. Expired Soloist builds fail closed; updating
this user-provided binary is manual for this evaluation candidate.

Select a wired LAN interface and an unused address pool outside DHCP before
creating the Docker LAN attachment. Set the following values for that host;
do not reuse example addresses or let Docker allocate from the active DHCP pool:

```sh
docker network create -d macvlan \
  --subnet "$LAN_SUBNET" --gateway "$LAN_GATEWAY" \
  --ip-range "$UNUSED_LAN_POOL" -o parent="$WIRED_INTERFACE" \
  zombiebox-soloist-lan
```

Wi-Fi/macvlan behavior is unverified. Discovery must be checked on the chosen
network; a successful HTTP response cannot prove that the phone sees Connect.

For a maintainer rebuild, refresh the pinned build contexts with `make sources`
before `build` (the prior local context may contain an older go-librespot).
For the frozen offline candidate, load the images and omit the build step.
After the host gates pass, initialize and start only the selected services:
Run these commands from the selected QA directory containing the source
`compose.yaml` and `compose.soloist.yaml`, with the same `ZOMBIE_RUNTIME_ROOT`
exported above. For a maintainer rebuild, also set `ZOMBIE_CORE_DIR` and
`ZOMBIE_FULL_DIR` to the actual source checkouts; source locations do not select
where credentials or QA data live.

```sh
docker compose --env-file "$ZOMBIE_RUNTIME_ROOT/.local/gateway/compose.env" \
  -f compose.yaml -f compose.soloist.yaml --profile spotify --profile soloist \
  build gateway spotify soloist
docker compose --env-file "$ZOMBIE_RUNTIME_ROOT/.local/gateway/compose.env" \
  -f compose.yaml -f compose.soloist.yaml --profile spotify --profile soloist \
  up -d soloist-init soloist spotify gateway
```

For an offline bundle, load its frozen images and omit `build`. Do not rerun the
initializer while the runtime is active. Preserve `soloist-state` to retain the
Connect session; key rotation or binary updates require stopping Soloist,
reinitializing explicitly and restarting it. Never remove existing volumes.

Before real-content playback, obtain the runtime's ID with Compose `ps -q soloist`
and run `scripts/check-soloist-container.py CONTAINER_ID`. Read bounded readiness
without putting a bearer or API key in command arguments:

```sh
docker compose --env-file "$ZOMBIE_RUNTIME_ROOT/.local/gateway/compose.env" \
  -f compose.yaml -f compose.soloist.yaml --profile spotify --profile soloist \
  exec -T spotify zombie-worker -config /config/worker.json -healthcheck
```

The command prints only backend, account readiness, actual audio readiness and
whether authorization is required. Never inspect the Soloist process command
line. No raw audio should be saved, cached or exported.

Physical steps and evidence sheets remain outside Git in the central
`ZombieBox-First-Test/ZB-006-Soloist.md` handoff. API availability, authentication,
actual PCM, Gateway relay and audible TV output are five separate results.

## October 4 execution record

Core source: `9c4c1f7`. The private `.2-qa` images were built and retained:

| Image | Local immutable image ID |
| --- | --- |
| `zombie-box-tv/gateway:0.1.0-zb006.2-qa` | `sha256:4a80122b00e892591835eba76a9ea190319f9c786c9a3dc6300fca1e241c269d` |
| `zombie-box-tv/spotify:0.1.3-zb006.2-qa` | `sha256:e222f3309f73aa184e248e0ecc4fc8e9829e04b3c4221eb86ee603c0e7e5c3b1` |
| `zombie-box-tv/soloist-runtime:0.1.0-zb006.2-qa` | `sha256:1d3048ecbcda303a51bb8b50996ac83d59db5634154fa57771322b80827b7ee9` |

Passed: `soloist-check` (vet, race tests including HTTP/WebSocket, three executable
builds), rendered isolation/config checks, production private generated-tone
sink/capture, and disposable production provisioning/activation/container audit
with dummy key/binary. The latter rejects unauthenticated requests and refuses
audio without actual PCM. Its bridge is a lab network, not Connect LAN evidence.
The user-supplied Soloist `1.3.8.82` ran `--version` inside the glibc image, without
a key/account; its build reports 2026-09-26. This does not prove authentication.
Full shell checks, 12 bootstrap tests and 43 Python tests also passed.

`make check` in Core passed every package except five existing YouTube server
tests; all five failures reproduced on the preceding `2eb464b` source. The full
suite is therefore not green. No code was changed to mask that result.
Connect discovery, real-account PCM/relay and audible selected-device playback
remain unexecuted. This is a private evaluation candidate, not a public release
or completed corresponding-source distribution. No existing service was deployed.
