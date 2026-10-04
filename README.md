# zombiebox-gateway-full

Linux/Fedora Compose packaging and private runtime configuration.

This is an independent repository in the Zombie Box workspace.
[Source and milestones](https://github.com/ZombieBox-tv/zombiebox-gateway-full) are hosted on GitHub.
Development checkpoints are not stable releases or physical compatibility claims.

Depends on the exact gateway-core commit in `dependencies.lock.json`.

The source-only `v0.1.3-dev.0` checkpoint pins a locally built Spotify image
with go-librespot v0.10.2. It is an unreleased QA candidate; the published
installer channel remains on the frozen dev.52 release. Spotify Premium audio
and the other current playback regressions still need physical validation.

## How the system works

```text
Internet services / your media servers / M3U + XMLTV
              │ modern HTTPS and provider protocols
              ▼
Full on Linux: Go gateway ── SQLite + bounded artwork/media caches
              │       ├─ provider adapters: Plex, Jellyfin, Stremio, IPTV
              │       ├─ private workers: YouTube, Spotify, AirPlay, Rebrowser
              │       └─ media tools: FFmpeg, MediaMTX, optional Threadfin
              │ HTTP/1.1 + semantic JSON; local media URLs and long polling
              ▼
Zombie Client APK on the TV ── native UI, D-pad and hardware player
              ▲
              │ paired Zombie Cast phone: remote, media and screen sharing
```

`zombiebox-gateway-core` supplies the **same Go application** to Full and Edge.
`zombiebox-protocol` defines its client-facing wire contract. Full packages the
core and each standalone tool in its own digest-pinned image; Compose connects the
workers on a private network. The YouTube worker adapts YouTube.js; Spotify wraps
go-librespot; AirPlay wraps UxPlay; Rebrowser runs a private browser worker.
FFmpeg and MediaMTX handle conversion and the authenticated Cast relay. Optional
Threadfin manages IPTV upstreams; a plain M3U works without it. The Android APKs
do not ship or execute these services, and upstream reference clones are build
inputs, not copies of the running software. The gateway fetches and sizes artwork,
resolves streams and keeps provider credentials; the TV receives semantic items
and playable LAN media. SQLite stores pairings, settings and progress. The central
workspace's ADR 0020 records the feature and process boundaries.

## Installation

Choose one route. The **published Docker release** is the simplest installation;
the **private dev63 bundle** at `gateway-full/.local/builds/dev63-full` is the
newer, local first-test candidate. They contain different gateway binaries. A
source tag such as `v0.1.0-dev.54` does not imply downloadable Docker assets.
See the [Full release page](https://github.com/ZombieBox-tv/zombiebox-gateway-full/releases)
for actual published packages.

### 1. Install on a Linux host

Full release packages contain a `compose.yaml` that runs a one-shot initialization
container before the gateway/workers. It creates private configuration and named
volumes, preserves existing credentials, and supplies diagnostic fixtures. No host
Go, Python, Node, FFmpeg or upstream checkout is needed. Heavy services remain optional
Compose profiles; their account readiness is independent of process startup.

Install the current **published, installable** Full release with one command:

Run this in a new or otherwise empty directory where you want to keep
`compose.yaml`. For example, `mkdir zombiebox-full && cd zombiebox-full` first.

```sh
curl -fsSL https://raw.githubusercontent.com/ZombieBox-tv/zombiebox-gateway-full/main/install-docker.sh | sh
```

The installer reads `install-channel.txt` from `main`; maintainers advance that
pointer only after a release has complete public Docker assets. It currently
selects dev.52, the newest published Full package, rather than the newest
source-only checkpoint. Each installation verifies the release's checksums,
publication gate, version and pinned image digests. For a deliberate rollback,
run the same URL with `| sh -s -- --version v0.1.0-dev.52`. Do not substitute a
source tag into the raw GitHub URL: dev.54 returns 404 because no installer was
published for that tag.

The installer downloads the release's checksummed `compose.yaml`, static
`seccomp.json`, license, notices and lock; then runs `docker compose pull` and
`docker compose up -d`. Its nine GHCR images use immutable digests verified through
anonymous registry requests. Eight retain their dev.46 identities; Spotify uses a
new licensed dev.52 image. The release source index pins the unchanged dev.46
source archives and includes a new Spotify archive with every linked Go module.
By default, all checked release files, including `compose.yaml`, remain directly
in the directory where you ran the command. The installer refuses to overwrite
files already there. Docker Engine and Compose v2 are the only host runtime
requirements; no host Go, Python, Node or FFmpeg is needed. Keep these files:
`compose.yaml` records the exact image digests. From the same directory, run:

```sh
docker compose ps --all
docker compose exec gateway cat /config/operator.code
```

If a later install channel selects a different release, use a new directory for
that release; the installer will not replace an earlier pinned bundle in place.

The `docker compose exec` command reads the private six-digit operator code
from inside the gateway container. Running `cat /config/operator.code` directly
in the host terminal will fail because that path is not on the host. The code
lives in the persistent `gateway` named volume at
`/config/operator.code`; a normal container restart or `docker compose down`
followed by `up -d` keeps it. Only deleting the data volume (`down -v`)
discards it. This is ZombieBox's local pairing/admin code, not a provider API
key or a temporary Google/Spotify code. The dev.52 gateway also prints that
code at startup, so the installer's `logs gateway` hint works, but includes
unrelated log output. Do not post the code, gateway startup logs or
`providers.json` in issues.

To install elsewhere, pass a directory explicitly:

```sh
curl -fsSL https://raw.githubusercontent.com/ZombieBox-tv/zombiebox-gateway-full/main/install-docker.sh | sh -s -- --directory ./zombiebox-full
```

If you prefer the previous hidden location, pass `--user-data` instead. That
selects `${XDG_DATA_HOME:-$HOME/.local/share}/zombiebox/full/releases/<version>`;
the installer prints the resolved path. Existing hidden installations are not
moved or deleted by the new default. Docker named volumes hold the gateway's
private configuration separately from the downloaded Compose files.

```sh
curl -fsSL https://raw.githubusercontent.com/ZombieBox-tv/zombiebox-gateway-full/main/install-docker.sh | sh -s -- --user-data
```

### 2. Connect and add your credentials

Install Zombie Client on the TV and open **Settings → Connect gateway**. Select
the discovered Linux host or enter `http://HOST_LAN_IP:8090`; then enter the
operator code above. Discovery uses UDP 8098 and can fail on isolated Wi-Fi;
manual URL remains available. Pairing stores a scoped device token on the client.

In **Settings → Providers**, enter only the services you use. Each save asks for
the same operator code; the app does not retain provider credentials. Use your M3U
URL under IPTV (and optional XMLTV URL), Plex server URL plus token, Jellyfin URL
plus token/user ID, or a Stremio endpoint/catalog. These values persist in the
gateway's private SQLite database. The client receives only enabled/ready status.
An M3U does **not** need Threadfin. You can start with IPTV alone and add other
accounts later.

| Service | Credential or address, and where it comes from |
| --- | --- |
| IPTV | Your provider's HTTP(S) M3U playlist URL, plus an optional XMLTV guide URL. A public playlist needs no account token; direct M3U needs no Threadfin. |
| Plex | **Current manual connector:** one reachable Plex Media Server URL and an `X-Plex-Token` authorized for that server. [Plex's XML/token guide](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/) describes a temporary token suitable for a short test, not a durable account-linking setup. |
| Jellyfin | Your server URL, an API key from its **Admin Dashboard → API Keys**, and the intended user's ID from **Admin Dashboard → Users**. The gateway requires all three; see [Jellyfin user administration](https://jellyfin.org/docs/general/server/users/adding-managing-users/). ZombieBox does not issue these. |
| Stremio | An add-on endpoint/catalog you choose, normally its [`manifest.json` URL](https://stremio.github.io/stremio-addon-guide/step1). There is no universal Stremio key; a private add-on URL may itself carry a secret. |
| YouTube catalog / TV Code | No personal API key for anonymous browsing or receiver pairing. Full creates the internal worker tokens automatically. TV Code is separate from Google account authorization. |
| Spotify Connect | Enable its optional profile. The current source candidate defaults new installations to local Spotify Connect discovery: select Zombie Box from the device picker in a signed-in Spotify app on the same LAN. The device-authorization URL/code remains a selectable fallback; the published dev.52 package uses that older code flow. Do not enter a Spotify password or developer key in Client settings. |
| AirPlay / Cast / Rebrowser | No Apple/Cast developer key. Enable the required profile; Full generates internal worker tokens and an AirPlay receiver PIN. Pair Zombie Cast through TV consent. |
| YouTube subscriptions/playlists (private candidate only) | The operator creates a **TVs and Limited Input devices** OAuth client in [Google Cloud](https://developers.google.com/youtube/v3/guides/auth/devices) with YouTube Data API enabled, then sets its client ID and optional secret on the gateway. The viewer approves the Client's displayed URL/code. Published dev.52 does not include this feature. |

Put IPTV/Plex/Jellyfin/Stremio values in Client **Settings → Providers** after
pairing. The gateway saves them in private SQLite, never in the APK. Only use
the server file below if you want that provider managed centrally; its entry
overrides the Client form. Backups of the gateway database and volumes contain
secrets.

**Plex shared libraries:** If another person shares remote servers with your
Plex account, the current gateway does not sign in to that account, discover its
available servers or refresh their server-specific tokens. The URL/token form
can reach one shared server only if you already have a valid connection URL and
token for it; it does not accept your Plex username/password. A durable flow
requires Plex account linking, server discovery and token renewal on the gateway.
This remains an M4 integration gap; do not assume that entering a token copied
from Plex Web will keep remote libraries connected indefinitely.

The initialization container creates `/config/providers.json` in the private
`gateway` volume. Its entries for the packaged YouTube, Spotify, AirPlay and
Rebrowser workers are **server-managed** and cannot be changed in Client Settings.
In the source-built dev.71 candidate, configure IPTV, Plex, Jellyfin or Stremio
from a terminal without editing JSON by running the offline initializer's guided
command with a real terminal. The published dev.52 initializer does not contain
this command; use Client Settings there until a new bundle is released. The
guided command hides URLs
and tokens that may contain credentials; secrets never appear in command-line
arguments, logs or the Client APK:

```sh
docker compose run --rm --no-deps --entrypoint node initialize /configure-provider.mjs iptv
# Replace iptv with plex, jellyfin or stremio as needed.
docker compose restart gateway
```

For Stremio, enter the addon's base URL and the catalog ID from its manifest;
the optional media type narrows that catalog. For an M3U file rather than a URL,
import a local file into the private media
volume, then choose option 2 and enter `channels.m3u` at the prompt:

```sh
docker compose run -T --rm --no-deps --entrypoint sh initialize -c 'umask 077; cat > /seed/media/channels.m3u' < ./channels.m3u
docker compose run --rm --no-deps --entrypoint node initialize /configure-provider.mjs iptv
docker compose restart gateway
```

The guided command validates HTTP(S) addresses and regular imported files up to
8 MiB,
preserves unrelated worker entries, and replaces `providers.json` atomically with
mode `0600`. A provider explicitly listed in this file becomes server-managed;
remove that entry to use Client Settings again. `docker compose down` preserves
SQLite and credentials; **`down -v` deletes the named volumes**.

### 3. Enable optional receivers

The default stack starts the gateway, discovery, relay and YouTube catalog. Enable
only the extra services you intend to use:

```sh
docker compose --profile youtube-receiver up -d
docker compose --profile spotify up -d
docker compose --profile airplay up -d
docker compose --profile rebrowser up -d
docker compose ps --all
```

In the current source candidate, a new Spotify installation advertises a local
Connect receiver after its optional profile starts. Choose it from a signed-in
Spotify app on the same LAN. An existing installation keeps its selected
credential mode and stored account state during upgrade. The published dev.52
package instead uses a device-authorization URL/code shown in Client **Services**;
it is not a token typed into the APK. AirPlay advertises a receiver and uses a private PIN stored in its worker
volume. In Client dev.50 with an updated Full gateway/worker, open the AirPlay
section and choose **Show AirPlay PIN**. Enter that four-digit receiver PIN on
the iPhone or iPad; the six-digit gateway operator code is unrelated. The
currently published dev.52 Docker image predates this Client route. Until an
updated image is installed, an administrator can reveal only the PIN locally
from the trusted host, in the directory containing the Compose file:

```sh
docker compose --profile airplay exec -T airplay sh -c 'sed -n '\''s/.*"pin"[[:space:]]*:[[:space:]]*"\([0-9][0-9][0-9][0-9]\)".*/\1/p'\'' /config/worker.json'
```

Keep the PIN private. If the fallback command prints nothing, check that the AirPlay
profile is running and its worker configuration was initialized. YouTube TV
Code/DIAL controls the TV receiver; it is separate from a
YouTube account sign-in. A packaged process being up does not prove an account is
ready or that a physical sender/player works.

The current source candidate runs the Spotify worker on the host network so
its built-in `_spotify-connect._tcp` advertisement and TCP 3679 pairing listener
can reach the LAN. Its bearer-protected worker API remains bound to Docker's
host-gateway address on TCP 8092, not the physical LAN. Use only the new
source-built worker with this Compose mode; the published dev.52 worker and
bundle remain unchanged. A Spotify Connect receiver is separate from a
Chromecast target. On a trusted LAN, mDNS UDP 5353 and pairing TCP 3679 must
reach the phone. Host registration and a private API bind passed a local probe.
In the private September 24 QA installation, the phone discovered Zombie Box
in Spotify, but audio and track metadata did not play correctly and some songs
skipped. Connect playback remains unverified until a phone/TV retest passes.

The private candidate bundle offers two modes without deleting saved account
credentials. To select the alternative device-authorization code flow, stop the
Spotify service and run its offline configuration helper, then start it again:

```sh
docker compose --profile spotify stop spotify
docker compose run --rm --no-deps --entrypoint node initialize /configure-spotify-mode.mjs device_auth
docker compose --profile spotify up -d spotify
```

Use `zeroconf` in the helper command to return to local Connect pairing. On a
host with several networks, pass one to four host LAN interface names to limit
the built-in mDNS advertisement, for example:

```sh
docker compose --profile spotify stop spotify
docker compose run --rm --no-deps --entrypoint node initialize /configure-spotify-mode.mjs zeroconf wlp1s0
docker compose --profile spotify up -d spotify
```

The interface must exist on the Docker host when the worker starts; the
network-disabled initializer can validate its name but cannot inspect the host
network. Omitting interface names preserves any previous allowlist. Pass
`--all-interfaces` after `zeroconf` to clear it and advertise on every available
interface. This selector narrows announcements; it does not itself repair a
firewall, Wi-Fi client isolation or a failed phone pairing. A
device-authorization code appears only when that mode has no usable stored
account credentials; switching modes never erases credentials to force a new
code. The current candidate Client labels account readiness separately from
worker availability. Published dev.52 bundles do not contain this helper.

AirPlay/RAOP advertisements start only after the optional AirPlay profile runs;
YouTube DIAL announces only while the Client has activated the receiver. On a
host with multiple networks, set the one IPv4 address that the phone can reach
before starting the receiver, using the offline initializer in the directory
containing this Compose file:

```sh
docker compose --profile youtube-receiver stop youtube-receiver
docker compose run --rm --no-deps --entrypoint node initialize /configure-youtube-dial.mjs 192.168.1.36
docker compose --profile youtube-receiver up -d youtube-receiver
```

Replace the example address with the host's actual trusted LAN address. The
helper validates the address, preserves the receiver token and other settings,
and writes the private config atomically; the worker must restart to use it.
The September 24 private QA used the host Wi-Fi address and the user's phone
then found Zombie Box through DIAL and played a video on the selected Vizio.
That physical result does not validate other LAN topologies or receiver
persistence after a gateway restart. If a TV
and phone occupy different local subnets, use a gateway HTTP address reachable
from both before generating a Cast pairing QR. Gateway health from the TV alone
does not prove the phone can use the address encoded in that QR.

Discovery uses UDP **8098** on the host, independent of the gateway's Docker
published HTTP **8090**. On Fedora's shared-Ethernet `nm-shared` firewall zone,
HTTP may work while UDP discovery is rejected. Check the zone assigned to the TV
interface, then allow UDP 8098 only on that trusted interface. For a temporary
`nm-shared` trial, run `sudo firewall-cmd --zone=nm-shared --add-port=8098/udp`;
repeat with `--permanent` and reload only after verifying that this is the right
zone for the intended TV network. Receiver discovery and media ports have their
own firewall/network requirements; opening 8098 does not make AirPlay, Spotify
or YouTube DIAL ready.

The **current source checkout and private dev63 bundle** also support read-only
YouTube account browsing. This is not in the published dev.52 images. Create a Google OAuth client
of type **TVs and Limited Input devices** in a Google Cloud project with the
YouTube Data API enabled. Set its client ID, and its client secret if issued, in
the private Compose environment file: `.local/gateway/compose.env` for a source
install, or `.env` beside `compose.yaml` for a future downloaded release that
includes this feature. For a downloaded bundle, from its installation directory:

```sh
printf '\nZOMBIE_YOUTUBE_OAUTH_CLIENT_ID=%s\n' 'YOUR_TV_OAUTH_CLIENT_ID' >> .env
chmod 600 .env
docker compose up -d gateway
```

In Client, open **YouTube → YouTube account → Connect account**. On another
device open the displayed verification URL, enter the code, and return to
**Check authorization** after the specified interval. Subscriptions and Playlists
then open through the existing YouTube browse worker. **Disconnect account** asks
for the current operator code. The Gateway stores access/refresh tokens in
private SQLite; the TV APK stores neither Google tokens nor the client secret.
TV Code does not authorize account browsing. A project-supplied OAuth client ID
in a later release could remove this one-time operator step; for now the operator
must provide one.

The published dev.52 images are frozen. New Go/Client changes in this checkout
are **not** present in that release until a later release rebuilds/publishes them.
The local source Compose image is tagged `0.1.0-dev.60` and includes the account
flow; its host smoke checks do not prove real Google authorization or TV behavior.

For the **existing private offline bundle**, enter its actual directory on the
Fedora development host and prepare a dedicated `full-test` runtime:

```sh
cd /home/diego/zombie-tv-project/gateway-full/.local/builds/dev63-full
sha256sum --check SHA256SUMS
bash install.sh --prepare-only
cat "${XDG_DATA_HOME:-$HOME/.local/share}/zombiebox/full-test/.local/gateway/config/operator.code"
bash install.sh --profile youtube
```

The first `--prepare-only` creates one private six-digit code at the displayed
`full-test/.local/gateway/config/operator.code` path and records the same value
as `ZOMBIE_PAIRING_CODE` in `full-test/.local/gateway/compose.env`. Repeating
preparation, restarting containers or reinstalling with the same runtime keeps
it. If those two files disagree, setup fails rather than rotating the code.
Enter the code in Client **Settings → Connect gateway**, then again when saving
provider credentials. To set server-managed providers directly, edit
`full-test/.local/gateway/config/providers.json` under the same runtime and keep
the generated worker entries/tokens. Rerun `bash install.sh --profile youtube`
to apply changes. For YouTube account browsing, set
`ZOMBIE_YOUTUBE_OAUTH_CLIENT_ID` and optional
`ZOMBIE_YOUTUBE_OAUTH_CLIENT_SECRET` in that private `compose.env` before
starting. They do not belong in `providers.json` or the APK. The operator code,
`compose.env`, `providers.json`, SQLite database and backups must remain private.

The offline bundle loads its own frozen image archive; it does not pull or
compile. Host Python3 is used only by this private
offline installer, not by the public Docker-only release installer. Source
checkouts instead keep the same private code under the `full` runtime.

The public dev.52 release starts gateway, discovery, MediaMTX and YouTube through
its completed initializer. The private source/offline Compose graph starts
gateway, discovery and MediaMTX; `--profile youtube` adds the catalog worker.
Optional receivers/browser can be added with:

```sh
docker compose --profile airplay --profile youtube-receiver --profile rebrowser up -d
```

The old dev.46 Spotify image remains under dependency-license review because it
links `xlab/vorbis-go` without an explicit license. The dev.52 Spotify image replaces
that binding with reviewed MIT Ogg/Vorbis modules and ships corresponding sources.
The published dev.52 Compose bundle still pins that licensed image by digest.
The current source Compose candidate instead builds a new licensed worker from
the pinned upstream source and binds its API privately before host-network
advertising. It has a distinct local image tag and no published identity. The
default installation does not start Spotify; enable its profile to begin pairing.
See [release policy](docs/release-policy.md).

Threadfin is optional; direct IPTV M3U works without it. Configure IPTV/Plex/Jellyfin/
Stremio in Client Settings. Existing worker configuration is preserved in named
volumes. `docker compose down` retains state; `down -v` deletes it. Stop overlapping
older installations before starting this one on the same LAN ports. Physical device
acceptance and real-account verification remain separate.

Maintainers build the initializer with `make bootstrap-image`, then generate a new
bundle using `scripts/compose-bundle.py --version vX.Y.Z --bootstrap-image IMAGE
--output NEW_DIRECTORY`. Without `--images`, it exports frozen local images; with
`--images reviewed-images.json`, every service (including initializer and relay)
must use an explicit registry digest. These Python/build commands are maintainer
operations, not installation steps. Output directories are never overwritten.

Each release freezes its own dependency set. Review the current stable upstream
versions when preparing a new functional release, verify compatibility, then pin
exact versions/commits and digests. Existing releases never follow `latest`; retain
their images and corresponding sources. Libraries stay libraries; standalone tools
remain services. See [release policy](docs/release-policy.md).

### Optional manual/source installation (maintainers and developers)


Requirements: Linux, Docker Engine with Compose v2, Python3, Git and FFmpeg with
libx264/libx265 for synthetic diagnostics. Source dependencies use the exact core
pin. In the existing workspace the sibling checkout is found automatically;
standalone cloning restores the pinned public core using `make deps`.

```sh
git clone https://github.com/ZombieBox-tv/zombiebox-gateway-full.git
cd zombiebox-gateway-full
make deps
bash install.sh
```

The installer prepares private configuration, builds the core image, starts core,
relay and LAN discovery, and waits for health. Credentials/SQLite/media survive
reinstallation. The Client lists discovered gateways; configure accounts/M3U in
Client Settings or the private `config/providers.json` under the printed runtime.
Use `--prepare-only` to generate/review configuration without starting services.

Default runtime: `${XDG_DATA_HOME:-$HOME/.local/share}/zombiebox/full`. To reuse the
central workspace's current runtime, run from that workspace:

```sh
ZOMBIE_RUNTIME_ROOT="$PWD" bash gateway-full/install.sh
```

Optional workers are explicit to fit small hosts:

```sh
bash install.sh --profile youtube --profile spotify
```

Supported profiles: `youtube`, `youtube-pot`, `youtube-receiver`, `spotify`, `airplay`, `threadfin`,
`rebrowser`. In this source candidate, `--profile youtube-pot` also starts the
base YouTube worker and routes video resolution through the optional, private
PO token resolver. The current published bundle does not include that profile;
its 360p route and image identities remain frozen. Spotify/AirPlay/Threadfin source builds require their locked references
(`make -C ../gateway-core references`); the published dev.52 installer retains
its frozen licensed Spotify GHCR digest. Enabling a worker does not supply
accounts or certify receiver compatibility. Existing provider URLs/tokens are kept.

Only discovery and receivers that need LAN multicast use host networking. Core and
ordinary workers retain their private Compose network and resource limits. Permit
TCP8090, TCP8554 (authenticated Cast publishing) and UDP8098 on the trusted LAN in your firewall; the installer does not
change the firewall. Broadcast can be blocked by Wi-Fi isolation; manual URL works
as fallback. RTSP defaults to the LAN bind so a paired phone can publish; set
`ZOMBIE_RTSP_BIND_IP` in the private Compose env file to restrict it separately.
Relay control/HLS ports stay inside Compose and are not published to the LAN.

### Legacy script-driven local bundle (optional manual path)

For a private evaluation, preserve all service images already built on the maintainer's
machine, including optional workers and MediaMTX:

```sh
python3 scripts/local-bundle.py --output /absolute/new/full-bundle
cd /absolute/new/full-bundle
bash install.sh --prepare-only
bash install.sh --profile youtube
bash control.sh status
bash control.sh stop
```

The generator exports a deduplicated `images.tar`, image identities/platforms,
source-free Compose, configuration helpers and diagnostic assets with SHA256SUMS.
Installation verifies files and restores missing images from that archive. It neither
builds nor pulls. Compose uses exact local SHA256 image IDs and `pull_policy: never`;
these IDs are distinguished from registry manifest digests. All nine services are
locked, with gateway/discovery sharing an image. Keep the **entire bundle**, including
the image archive, for reinstalls. Moving a development tag does not affect it.

Each external tool remains in its own service (UxPlay inside `airplay`, go-librespot
inside `spotify`, Threadfin, MediaMTX and the Node workers). First-party wrappers,
Dockerfiles and dependency locks are tracked; upstream clones stay ignored local
build inputs. No upstream source is vendored into this repository.

Local bundles default to project `zombie-full-test` and runtime
`${XDG_DATA_HOME:-$HOME/.local/share}/zombiebox/full-test`. Their LAN ports overlap an
existing normal installation; explicitly stop that installation before starting the
candidate. Existing configuration is not copied. Set `ZOMBIE_COMPOSE_PROJECT` and
`ZOMBIE_RUNTIME_ROOT` consistently on install/control commands to choose alternatives.
Use `control.sh down` to remove this project's containers/network without deleting
persistent state. Logs may contain provider-specific information; review before sharing.

This provides repeatable offline deployment of the saved Linux architecture, not a
promise of bit-for-bit source rebuilds or completed physical validation. No external
registry is required for that offline installation; provider content still needs
network access. The public GHCR installation above uses the separate frozen release.
The author's device test manual is intentionally kept outside this repository.

Registry distribution will use one image per service, pinned as `image@sha256:...`;
old manifests/layers must remain retained. A digest pins identity but does not ensure
that a registry retains the content. See [Compose image references](https://docs.docker.com/reference/compose-file/services/#image)
and [Docker image export](https://docs.docker.com/reference/cli/docker/image/save/).

### Legacy script-driven release builder (optional manual path)

The maintainer runs `scripts/release-bundle.py --images images.json --output DIR`
with actual reviewed `ghcr.io/...@sha256:...` references for every first-party
service. The generated bundle contains Compose, configuration helpers, relay/browser
configuration, diagnostic media and checksums. It has no source build dependency.
After downloading and verifying the published bundle, run the same `bash install.sh`.
It pulls pinned images and starts configured services; no Go, source clones or
FFmpeg encoder is required on the user's Linux host.

Compose is the complete installation path; a bare `docker run`
command omits relay/discovery/worker configuration and is not equivalent.

```sh
make deps-check  # uses ../gateway-core or ZOMBIE_CORE_DIR
make setup      # private defaults, preserves existing credentials
make check      # all Compose profiles
make build      # gateway image
make up
make down
```

`make deps` can restore `.deps/gateway-core` after its remote is configured.
Standalone runtime defaults to this repo's `.local`; the central workspace passes
`ZOMBIE_RUNTIME_ROOT` to preserve its existing runtime. Secrets stay in private
config files, never Git. Heavy workers remain opt-in. `make sources` exports the
locked Spotify/UxPlay/Threadfin sources for their named build context. Use Compose
profiles `youtube`, `youtube-receiver`, `spotify`, `airplay`, `threadfin`, `rebrowser`
when deliberately building/starting those services. Source code belongs to core.

On the 8 GB Fedora host, keep conversion/browser concurrency bounded and probe
hardware acceleration. Container health is not proof of account readiness or A/V.

## Development rules

Run `make format` and `make format-check`. Formatters are pinned and downloaded
on first use. See [AGENTS.md](AGENTS.md), [history provenance](docs/history.md),
[component work](docs/PLANNING.md) and [local milestone registry](docs/milestones.json).
The central workspace owns product-wide ADRs, the original specification, the UI
reference, M0–M11 exit gates and the complete development/validation gap audit.
Physical devices over USB/ADB are the default; automated checks do not establish
legacy runtime or end-to-end account/media compatibility.

Dev.10 packages the core's local audio-track selection and text-subtitle endpoints.
Only the gateway image advances to `0.1.0-dev.10`; unchanged service images retain
their `dev.9` pins. These features require local media and FFmpeg. Remote tracks,
automatic language choice and bitmap burn-in remain pending.

Dev.11 advances the gateway and YouTube images for hierarchical provider browsing
and progressive remote adaptation/adaptive mux. `make remote-smoke` runs synthetic
HTTP A/V fixtures inside the packaged FFmpeg image with no external network.
`make tracks-smoke` retains the authenticated HTTP local-track regression gate.
Building an image does not replace a running container; existing services must be
recreated explicitly to consume the new image.

Dev.12 packages selected-client media reception and Cast encoder budgets in the
gateway image. YouTube remains dev.11; unchanged worker images keep their pins.
Settings → Receive Spotify / AirPlay arms the paired foreground client. It does
not provide credentials or turn process health into account/playback readiness.

Dev.13: Packages the dev.13 shared retry/live-TS core; remote smoke includes live TS conversion.

## dev.14 increment

Packages dev.14 manifest adaptation; synthetic packaged FFmpeg coverage includes HLS TS/fMP4 and DASH template/static-list A/V conversion.
The four requested block-1 changes are implemented; physical acceptance and broader product gates remain open.

Dev.16: Packages shared dev.16 gateway, YouTube, Spotify, AirPlay and browser workers. Unchanged receiver/Threadfin images retain prior pins.

## License

First-party code: [GPL-3.0-only](LICENSE). See [NOTICE](NOTICE) for third-party scope.

Dev.18 retains processed artwork across restarts in `/data/artwork` in the existing persistent state volume.
The shared cache defaults to 64 MiB/24 hours; `-artwork-cache-mb 0` disables disk
persistence. Source URLs/credentials/original images are not stored in cache files.

Dev.19: Packages dev.19 shared media, EPG, diagnostics and SQLite migration core; unchanged workers retain their existing image pins.

Dev.20: Packages shared dev.20 handoff and low-bandwidth conversion. Unchanged worker image pins are retained.

Dev.21: Packages shared dev.21 network/search/state maintenance; unchanged optional workers retain their image pins.

## dev.22 increment

Packages the shared dev.22 receiver-coordination core; optional workers retain their version pins.
No product or physical acceptance gate closes.

## dev.23 increment

LAN HTTP defaults and a constrained host-network discovery sidecar; make up prepares and builds the pinned core.
No product or physical acceptance gate closes.


## dev.24 increment

Packages the shared companion core in dev.24 and includes the QR encoder license. Existing running services are not automatically replaced.
Full visual/capture policy, extended Remote, HEVC/4K and other product gates remain open; physical acceptance stays deferred.

## dev.25 increment

One-command source/release installation, preserved private runtime, digest-only source-free bundle preparation and extended fixtures. Real hosted image digests/publication remain pending.

## dev.27 increment

Pins the shared evidence-gated 1080p Cast negotiation core. The Compose build target is dev.27; no new image was built or deployed in this checkpoint, preserving the reclaimed disk space. Active services remain unchanged. Physical and distribution gates remain open.

## dev.29 increment

Pins the shared audio-only Cast core. Source image target advances to dev.29; no image rebuild or active-service replacement is claimed.
Product milestones and physical acceptance remain open.

## dev.30 increment

Pins the shared phone-media core. Source image target advances to dev.30; active services are not replaced and no new image is claimed.
Product milestones and deferred physical gates remain open.

## dev.31 increment

Pins the shared native-inventory validation/export core. Source image target is dev.31; active dev.22 services are unchanged and no new image is claimed.
Product milestone and physical/public distribution gates remain open.

## dev.32 increment

Pins the shared legacy phone-file container increment for Full. Source image target is dev.32; active services are not replaced. Candidate build evidence is recorded in the workspace checkpoint.
Product milestones, physical validation and public distribution remain open.

## dev.34 increment

Consumes dev.34 core pairing and remote-text implementation; packaging strategy is unchanged. Public image digests, complete redistribution inventory and deployment remain separate gates.

## dev.35 increment

Packages the shared dev.35 queue/adaptation/listening core and epoch-aware YouTube receiver. Hosted source and dependency remotes are configured; public images and full binary source inventory remain separate.


## dev.37 increment

[Immutable image inventory](docs/image-source-inventory.md) identifies Alpine package/source revisions before distribution. It does not claim complete corresponding sources. The gateway has a bounded writable temporary filesystem for text subtitle conversion; active deployments are not changed by this source checkpoint.

## dev.40 reception and diagnostics increment

Consumes the same endpoint-diagnostic core. No image deployment or new runtime validation; complete source/notices and immutable image delivery remain open. Product milestones remain open.

[Shared endpoint diagnostic contract](https://github.com/ZombieBox-tv/zombiebox-gateway-core/blob/v0.1.0-dev.40/docs/endpoint-diagnostics.md).

## dev.41 guide and audio selection increment

Pins the shared capability-aware audio-selection core. No image build, active deployment or new binary publication in this checkpoint. Product and physical gates remain open.

Dev.42: pin the shared preferred-audio planner. No new binary image or worker distribution; complete Full image/source delivery remains open.

## dev.43 navigation and functional media increment

Dev.43: gateway image includes the shared software pipeline diagnostic. Immutable image inventory reads copied Go binary hashes, linked modules and build identities without execution. Complete OS/worker corresponding sources and GHCR bundle delivery remain open.

The new source-built gateway can run `-diagnose-media` in an isolated container to
check its local FFmpeg pipeline. This is opt-in and does not connect to any provider
or certify a TV decoder. See the core's `docs/media-diagnostic.md`. Existing running
containers are not upgraded by building a new image.

## Optional Soloist evaluation

The unreleased ZB-006 Full amd64 candidate has an isolated, opt-in Soloist fallback.
See [runtime provisioning and gates](docs/soloist-runtime.md). Its image never
includes Spotify's binary or a key. Docker execution, LAN discovery, real-account
relay and audible TV playback are separate required checks; no public release
or physical compatibility is claimed by this source checkpoint.
