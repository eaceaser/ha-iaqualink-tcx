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

- Ruff check and formatting pass.
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
- Official HACS action was invoked locally. It exits before validation with
  **“No GitHub token found”**. Authenticated remote repository validation is pending;
  it must inspect the published branch, and these changes have not been pushed.
  `.github/workflows/validate.yml` provides that check using the workflow's read-only
  token, with comments disabled. Local layout includes one integration, English
  translations, version/issue metadata, `hacs.json`, and original brand assets.
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
3. **Release candidate**: final entire-tree review and any follow-up findings are
   recorded below after completion.

Remaining verification limits: no real credentials, live WS delta confirmation,
physical measurement freshness, hardware readings, or actual hardware/app coexistence
was tested. Cloud state arrival does not establish per-field physical sample age.
The upstream TCX implementation still carries protocol uncertainty; changing the
pin requires repeating boundary and stock-image tests, not merely updating metadata.
