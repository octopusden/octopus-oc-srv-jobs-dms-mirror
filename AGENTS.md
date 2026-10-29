# AGENTS.md

Guidance for coding agents working in this repository.

## Commands

```bash
# install (editable is convenient for iterating)
python -m pip install -e .

# full suite - this is exactly what the Dockerfile runs
python -m unittest discover -v

# one module / one class / one test
python -m unittest oc_dms_mirror.tests.test_rest_api -v
python -m unittest oc_dms_mirror.tests.test_dms_mirror.DmsMirrorV3TestSuite -v
python -m unittest oc_dms_mirror.tests.test_dms_mirror.DmsMirrorV3TestSuite.test_register_component__ok -v

# build wheel
python setup.py bdist_wheel

# run the batch job
python -m oc_dms_mirror --config-file ./config.json

# run the webhook service (gunicorn, default bind 0.0.0.0:5400)
python -m oc_dms_mirror.rest_api

# container (CI builds against Python 3.7; the ENTRYPOINT is the batch job)
docker build --build-arg PYTHON_VERSION=3.7 .
```

**CI:** `.github/workflows/` delegates to reusable workflows in `octopusden/octopus-base`. There is no lint step and no lint config in the repo.
- `on-push.yml` deploys to Test on every push.
- `on-release.yml` deploys to Prod on a published release.

**Releases:** bump `__version` in `setup.py`. Keep code Python 3.7 compatible.

**`oc-cdtapi`:** all external clients come from the `oc-cdtapi` library (`octopus-oc-corelibs-cdtapi`), pinned in `setup.py` (`oc-cdtapi >= 3.48.0`).
- A new Postgres API endpoint belongs in `oc_cdtapi.PgAPI.PostgresAPI` first, then here.
- Raise the pin whenever this repo starts using a newer client method.

## Architecture

One class, `DmsMirror` in `oc_dms_mirror/dms_mirror.py`, is the entire engine. Everything else is a thin wrapper around it.

### Two entry points, one argument surface

- **Batch job**: `oc_dms_mirror/__main__.py` → `DmsMirror().main()` → `run()`. It fans every component in the config file across a `multiprocessing.Pool` (`--dms-processes`, default 3).
- **Webhook service**: `oc_dms_mirror/rest_api/__main__.py` builds the *same* parser via `DmsMirror().basic_args(parser)` and adds the `--ws-*` options.
  - It hands the parsed namespace to `StandaloneApplication`, a gunicorn `WSGIApplication` subclass, which stashes it on `app.args`.
  - `routes.py` then lazily builds a per-worker `DmsMirror` from those args via `setup_from_args()` + `load_config()`.

Because both entry points share `basic_args`, any new option is automatically available to both. Add it there, not in either `__main__.py`.

Routes (`rest_api/app/routes.py`):
- `POST /register-component-version-artifact`: the DMS webhook.
- `POST /get-gav`: resolve a component's GAV template.
- `GET /healthcheck`.

### The mirroring pipeline

Per artifact, `process_artifact()`:
1. Skip `repositoryType == "DOCKER"`.
2. Resolve the component's config (see below) → pick the `tgtGavTemplate` entry for the artifact's `type`.
3. Render the target GAV via `string.Template` with substitutes from `_make_gav_substitute()`.
4. If the GAV already exists in the MVN *download* repo → skip, unless `--always-enqueue`, in which case still send the registration message.
5. Otherwise `_copy_artifact()`: stream from DMS into a `tempfile`, then upload to the MVN *upload* repo (`pom=True`).
6. `_register_artifact()`: send a `register_file` message naming the new GAV and its CI type.

Missing `tgtGavTemplate` entries are the intended way to skip an artifact type. A component whose template lacks `documentation` simply never mirrors documentation.

### Config: two files, two different roles

Neither ships with the repo.

- **`--config-file`** (default `./config.json`) → `self._components`: a static per-component map of `ci_type` + `tgtGavTemplate` (+ optional `enabled: false`). Checked first by `get_component_config()`.
- **`--gav-template-config-file`** (default `./gav_template_config.json`) → `self._gav_template`: a *single* template containing `$component` / `$client` placeholders, used for components **not** in `config.json`.
  - `_generate_component_config()` looks the component up in Postgres (`pg_client.get_citypedms_by_dms_id`), finds its `clientCode` from the DMS component list, then substitutes into the template.
  - The same template drives `generate_ci_regexp()` during auto-registration.
  - A missing file is tolerated (`self._gav_template = None`).

`_generate_component_config()` round-trips the dict through `str()` + `ast.literal_eval()` to do the placeholder substitution. Watch out for this quirk when touching it.

### GAV template placeholders

Templates go through two distinct substitution passes:
- `$component` and `.$client` are plain `str.replace()` calls. The `.` is part of the match for `$client`, so a clientless component loses the whole dotted segment.
- Everything else is `string.Template`: `$n` name, `$v` version, `$p` packaging, `$c`/`$cl` classifier, `$c_hyphen` / `$c_colon` (classifier with a leading `-` or `:`, empty when there is no classifier), `$at` artifact type, `$prefix` (`--mvn-prefix`).

In JSON the second group is written escaped (`\\$v`), and `.replace("\\", "")` strips the backslashes at use time. The rendered GAV is then sanitised with `re.sub('[^\w\-\.\:_]+', "_", ...)`.

### DMS API v2 vs v3

`--dms-api-version` (default 3) picks `DmsAPI` vs `DmsAPIv3`. The versions differ in ways that ripple through the code:
- v3 does **not** return `name` / `packaging` / `classifier` in the artifact list. `_make_gav_substitute()` therefore falls back to `get_artifact_info()`, and then to parsing the filename by splitting it around the version string.
- v3 downloads through `download_component()`; v2 resolves a source GAV via `get_gav()` and pulls it from Nexus.
- `DMS_CRS_URL` and `DMS_TOKEN` apply to v2 only. They are passed by setting environment variables before constructing the client.

### Message target

`--msg-target` is `amqp` (default) or `db`. Both send the same logical `register_file` payload: AMQP through `oc_checksumsq`'s `ChecksumsQueueClient`, `db` through `PgQAPI` into the `cdt.dlartifacts.input` queue.

### Auto-registration (webhook path only)

With `--auto-register-component`, `process_component_webhook()` calls `register_component()` before mirroring.

The registered `ci_type_group_id` comes from `get_ci_type_group_id()`, first hit wins:
- A component with `componentVersion.parentComponent` joins the group of its parent's citype: `pg_client.get_citypedms_by_dms_id(parent)["ci_type_id"]`, then `pg_client.get_citypeincs_by_citype_id(...)["ci_type_group_id"]` (`dl_schema`). The parent is checked first on purpose: client DMP bundles are solutions too, and belong to the group of `dmp-bundle`.
- With no parent and `componentVersion.solution` set (always present in the payload), it goes to `--ci-type-group-solution` (default `client-solution`).
- Otherwise it falls back to the component ID: a CI type group named after itself. This includes a solution whose parent is unregistered or whose parent citype has no group (404).
- Any non-404 error propagates and fails the webhook on purpose. A fallback would be permanent, because `is_component_registered()` skips the component on every later webhook.
- Components that are already registered keep their group. Moving them is a separate DB fix.

Other payload rules:
- `componentVersion.labels`: `non-deliverable` → `is_deliverable: False`; `test-component` → skipped entirely.
- `is_standard` is `"N"` when a `clientCode` is present or `componentVersion.solution` is set.
- Only `PUBLISH_COMPONENT_VERSION` events are accepted; anything else raises.

### Secrets and clients

Every argparse default comes from `VaultAPI.load_secret("NAME__KEY")` (`oc_cdtapi`). It resolves in this order:
1. env `NAME__KEY`;
2. env `NAME_KEY`;
3. Vault (`VAULT_URL` / `VAULT_TOKEN` / `VAULT_MOUNT_POINT`), appending `_TEST` to the Vault path when `PYTHON_ENV=test`.

This is why README.md's single-underscore names (`MVN_URL`, `DMS_URL`, …) still work while the code asks for `MVN__URL`. Any CLI flag overrides all of them.

All API clients (`dms_client`, `mvn_client`, `pg_client`, `psql_mq_client`, `queue_client`) are lazy `@property` accessors. Nothing connects until first use, which matters because pool workers fork before any of them exist.

### Error handling conventions

- `_make_dms_api_call_with_retries()` wraps every DMS call. It retries `--retries-count` times (default 5) with a 30s sleep, on `ConnectionError` / `HttpAPIError` / `KeyError`. Route new DMS calls through it.
- `process_component()` returns errors as **strings**, never exception objects, and never mutates the exception.
  - The comments there are load-bearing: returning exceptions across `multiprocessing.Pool` (or extending their `args`) hangs the pool.
  - `main()` logs all collected strings, then raises the first to produce a non-zero exit.

## Tests

`oc_dms_mirror/tests/test_dms_mirror.py` mocks every external client in `DmsMirrorTestBase.setUp`. Things to know:

- **`DmsMirrorV3TestSuite` subclasses `DmsMirrorV2TestSuite`.** A test added to the v2 suite runs under v3 as well, unless it is overridden. Several are, precisely because the v3 substitution path differs.
- **Mocked DMS methods need `__name__` set** (`mock.__name__ = "get_versions"`), because `_make_dms_api_call_with_retries` reads it for its log line.
- **`self.args` is a `MagicMock`**, so an option the code reads but `setUp` doesn't set comes back as a `MagicMock`, not its default. Set every new option in `setUp`, as with `ci_type_group_solution`.
- **`pg_client` is a real `PostgresAPI` with its methods replaced by `Mock`s.** Mock every method a test reaches, for example `get_citypedms_by_dms_id`, `get_citypeincs_by_citype_id` and `post_new_component`. An unmocked one tries real HTTP.
- **Where registration tests live:** in `DmsMirrorV3TestSuite` (`test_register_component__*`, `test_get_ci_type_group_id__*`). The logic doesn't depend on the DMS version.

`tests/resources/config.json` is deliberately reused as *both* the components config and the gav-template config. Its four `tgtGavTemplate` entries exist to exercise each classifier placeholder form, and `_get_artifact_test_case()` selects the entry by placeholder.
