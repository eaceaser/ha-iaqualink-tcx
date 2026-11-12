# Validation and review record

Final validation uses mocked vendor transport with Python socket connections blocked.
Public package/Git/image downloads were allowed. No account credentials, real cloud data,
live equipment operations, production changes, repository push, or release publishing
were used. During development, one expanded smoke run missed its config-flow client
mock and attempted cloud authentication with synthetic fixture credentials. It
returned invalid-auth; no real account or equipment request was involved. The mock
was corrected and socket guards were added to prevent recurrence. The local kickoff
remains outside this repository.

## Reproduce

Run `scripts/validate_stock_ha.sh` from a Docker-enabled host. It mounts only this
repository read-only into a disposable **stock** HA container. It installs the
manifest dependency and development tools with HA's package constraints, then runs
lint, formatting, focused tests, and `scripts/stock_ha_smoke.py`. No custom HA image
is built. The smoke script boots HA base functionality and exercises real config
flows, entry/platform setup and entity registration; only vendor transport is mocked.
The pytest helpers contain only synthetic account/controller data. Import HA before
HTTPX: HA 2026.11 aliases it to HTTPX2 during initialization.

Image tested: `ghcr.io/home-assistant/home-assistant:2026.11.0`, digest
`sha256:c6c1ca9931036bf3a2c4cc088d8db25dfea3b33935a5ecc83c40349462e2f69e`.
Python: 3.14.10. Exact dependency commit:
`565b93d019077007a88bca57f5b2a253332be929`; package metadata:
`iaqualink 0.8.0a1.dev8+g565b93d01`.

A separate direct `python -m pip install` of that Git requirement with
`/usr/src/homeassistant/homeassistant/package_constraints.txt` succeeded in the
stock image, including Git checkout, isolated hatchling/hatch-vcs wheel build,
Python compatibility, and shared HTTPX dependencies. No prebuilt wheel fallback
was necessary. Its built-in integration pins `iaqualink==0.7.0`; simultaneous use
is unsupported and documented, not treated as package isolation by domain.

## Results

- Ruff check and formatting pass; **49 focused tests pass** locally and in the
  fresh stock HA image.
- Focused pytest suite covers TCX filtering, controller selection, duplicate helper,
  reauth, auth/setup errors, client closure, real upstream WS bootstrap/subscription
  reuse through mocked transport, disconnect/REST cache rejection/recovery, close
  during active refresh, zero/invalid values, service/offline statuses, late equipment,
  partial fields, light type/effect changes, null synthetic settings, unit validation,
  redacted logging/diagnostics, and no control platforms or getter-triggered writes.
- Stock-HA smoke: actual config-flow creation, duplicate rejection, reauth/reload,
  integration/platform load, initial 13 registered entities, late entity addition,
  unload/reload and HA-stop cleanup. Mock transport records only auth POST,
  discovery/shadow GET and Authorization subscribe frames. No command services.
- Official hassfest image passes: **1 integration, 0 invalid integrations**.
  Image digest:
  `sha256:da6522993280166fe072704989a2b4c33e639e8ceb69c8ab6ad7ec5045c1a1e3`.
- Official pinned HACS manifest schemas and actual brand validator pass against
  local files, with networking disabled. Reproduce with:

  ```sh
  docker run --rm --network none --entrypoint python -e PYTHONPATH=/hacs \
    -v "$PWD:/github/workspace:ro" \
    ghcr.io/hacs/action@sha256:187499a09c5d41f9f0d42ff80d203ed87b974c028290140913b61e005fb0aab2 \
    /github/workspace/scripts/hacs_local_check.py
  ```

- The full official HACS action was invoked locally. It exits before validation with
  **“No GitHub token found”**. Authenticated remote repository validation is pending;
  it must inspect the published branch, and these changes have not been pushed.
  `.github/workflows/validate.yml` provides that check using the workflow's read-only
  token through the action image’s actual `INPUT_GITHUB_TOKEN` variable and pins
  `REPOSITORY_REF` to the checked-out GitHub SHA. The container does not post comments.
  Local layout includes one integration, English translations, version/issue metadata,
  `hacs.json`, and original brand assets inside the integration directory.
  HACS image digest:
  `sha256:187499a09c5d41f9f0d42ff80d203ed87b974c028290140913b61e005fb0aab2`.

The normal HA warning about an unofficial custom integration is expected. Local
pytest emits an HA/aiohttp deprecation warning; it originates in HA's HTTP application
class. This is neither live-controller verification nor a HACS catalog approval.

## Required independent milestone reviews

All gates use **two independent `gpt-6.1-sol` reviewers with high reasoning**, fresh
contexts, and read-only instructions. One focuses on quality/current HA practices;
one on efficiency/read-only reachability. Reviewers inspect the exact pinned
upstream source and perform offline checks. No reviewer is authorized to access
live equipment or modify files.

1. **Acquisition foundation**, initial worktree subsequently recorded in `ce0053d`:
   both reviewers found HTTPX URL logging escaped upstream privacy suppression;
   the efficiency reviewer also reproduced an in-flight refresh reopening a client
   after close. Fixed with context-scoped transport privacy filters and a serialized
   refresh/close lock. Both reviewers rechecked fixes and independently passed
   the 13 foundation tests. No remaining findings at this gate.
2. **Read-only entities**, `ce0053d` plus reviewed follow-up fixes: reproduced nullable
   synthetic pump values retaining stale readings, a missing locked-color dependency,
   late light metadata failing to discover effects, and invalid unit flags defaulting
   to Fahrenheit. Fixed via current-source public device views, selected-color
   dependencies, dynamic light metadata and explicit valid-unit observation. Both
   reviewers rechecked the resulting tree and passed all 40 tests. No remaining
   findings. Later stock smoke updated setup/unload to HA 2026.11's `None` return
   and `async_unload_platforms_or_raise` convention; the final gate reviews this too.
3. **Release candidate**, `fbd9223` plus reviewed follow-up fixes: both reviewers
   reproduced a reconnect delta promoting cached controller status without current
   session status/service-mode fields. Added explicit current-session status and
   valid service-mode gating, with reconnect and malformed-mode regressions. The
   quality reviewer also found the pinned HACS validator requires brand assets
   inside the integration directory; moved original assets there. The quality
   reviewer additionally reproduced a disabled solar sensor retaining its prior
   value; added valid current-session solar-enable gating and regressions. Both
   reviewers rechecked all runtime fixes and independently passed 49 tests with no
   remaining findings. The local HACS schema/brand subset also passes; full remote
   HACS validation remains pending as described above.

Remaining verification limits: no real credentials, live WS delta confirmation,
physical measurement freshness, hardware readings, or actual hardware/app coexistence
was tested. Cloud state arrival does not establish per-field physical sample age.
The upstream TCX implementation still carries protocol uncertainty; changing the
pin requires repeating boundary and stock-image tests, not merely updating metadata.

## Quiet-stream telemetry fix — 2026-11-11

Follow-up to the first live installation: unchanged equipment produced a connected
but quiet stream, and the original 120-second state-frame age guard incorrectly
made all equipment unavailable. The fix separates session availability from recent
state traffic. Existing upstream 30-second protocol pings detect transport failure;
a quiet initialized connection retains only readings observed during that session.
The diagnostic state changes from `stale` to `quiet` after 120 seconds. Controller
status, service mode, per-reading field observation and disconnect guards remain.

While a session has state, the upstream public freshness policy suppresses idle
REST fallback, preserving stream readings instead of overwriting them with a cached
shadow. Both independent `gpt-6.1-sol` high-reasoning reviewers reproduced a P2 race:
a bootstrap REST response could complete after the first WS state and replace it.
The public transport boundary now discards such a response before upstream parses
it; one bounded public refresh restores status from the WS cache. Both reviewers
rechecked this fix, independently passed all 55 tests and Ruff, and reported no
remaining findings. Review scope was the complete follow-up runtime/test diff
against `efb494f`, including the new heartbeat test.

Final local and stock HA 2026.11.0 checks: **55 tests passed**, Ruff lint/format
passed, and actual HA config-flow/platform setup, late discovery, unload, reload
and shutdown smoke checks passed. The dependency and stock image pin are unchanged.
New regressions cover a 24-hour quiet interval without REST requests or new
subscriptions, offline/service-mode pushes, delayed REST/WS overlap, bounded retry,
and actual HTTPX-WS/wsproto ping/pong handling over an in-memory transport, including
missing-pong closure and recovery. Tests use synthetic data and blocked sockets.
The standard custom-integration warning and HA/aiohttp deprecation remain expected.

No running HA changes, controller operations or live account requests were made for
this fix. A cloud transport heartbeat cannot independently detect a controller or
subscription that silently stops reporting while the cloud continues answering
pings. Physical sample age and that vendor-side failure mode remain unverified;
the integration continues to rely on reported controller status for that link.
