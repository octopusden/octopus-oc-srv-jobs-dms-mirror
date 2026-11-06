# DMS Mirroring tool for distributives
Mirrors distributives from DMS (release management system, proprietary implementation) to the MVN-compatible repository specified in the settings.
Sends a `register_file` message for every artifact it copies.

There are two entry points that share the same options:

- **Batch job**: `python -m oc_dms_mirror`, run as a nightly cronjob.
- **Webhook service**: `python -m oc_dms_mirror.rest_api`, called by DMS when a component version is published.

The webhook is the fast path. The batch job is the nightly safety net: it catches versions whose mirroring failed.

# How it works

## Batch job
1. Takes the component list from DMS, which reads it from the components registry. Archived components are not returned.
2. Logs a warning for every `config.json` component that DMS doesn't return: archived, removed or a typo in the key.
3. Skips components labelled `test-component`.
4. Processes the newest `--versions-limit` released versions of each component (default `3`). DMS returns versions newest first.
5. Mirrors every artifact of those versions, see [Mirroring an artifact](#mirroring-an-artifact).

Components are processed in parallel, `--dms-processes` at a time (default `3`).

## Webhook service
`POST /register-component-version-artifact` accepts DMS `PUBLISH_COMPONENT_VERSION` events.
With `--auto-register-component` it first registers a component that isn't in the CI type registry yet, then mirrors the artifacts of the published version.

Other routes: `POST /get-gav` returns the GAV templates of a component, `GET /healthcheck`.

## Mirroring an artifact
1. Artifacts in a `DOCKER` repository are skipped.
2. The GAV templates come from the component's `config.json` entry. A component that isn't in `config.json` gets them from its CI type registry entry and `gav_template_config.json`.
   A component that is in neither is skipped. The webhook registers it when the component publishes its next version.
3. An artifact type without a template is skipped.
4. If the target GAV already exists in the download repository, the artifact is skipped (`--always-enqueue` still sends the registration message).
5. Otherwise the artifact is downloaded from DMS, uploaded to the upload repository and registered.
   If DMS lists the artifact but can't find its file in any of its repositories (HTTP 404, or `DMS-40006` / `UnableToFindArtifactException`), only that artifact is skipped with a warning; the rest of the component goes on and the job doesn't fail.
   Client errors (4xx, except 408 and 429) are not retried.

## When DMS fails
A DMS error answered with 5xx is retried `--retries-count` times, 30 s apart. If it still fails, only the part that needed it is skipped with a warning, and the job doesn't fail:

| DMS call | Skipped |
|---|---|
| download, artifact info | the artifact |
| artifact list of a version | the version |
| version list of a component | the component |
| component list, while resolving the client of a component not in `config.json` | the artifact |

The component list at the start of the batch job is the exception: without it there is nothing to process, so the job fails.
Errors from MVN, the CI type registry or the message queue still fail the component as before.
A skipped part is picked up by the next run once DMS answers again.

The registration message goes to AMQP (`--msg-target amqp`, default) or to the PostgreSQL queue `cdt.dlartifacts.input` (`--msg-target db`).
Its CI type is `--ci-type-documentation` for `documentation`, `--ci-type-release-notes` for `notes` and `report`, and the component's `ci_type` for anything else.

# Configuration
Neither configuration file is provided by default.

## config.json
Path: `--config-file`. *Default*: `config.json` in the current directory.

The mapping for components whose CI type or GAV doesn't follow the generic template, mostly legacy ones.
It does **not** decide which components are processed; the DMS component list does.

```
  "some": {
    "ci_type": "SOMEDSTR",
    "tgtGavTemplate": {
      "notes": "\\$prefix.release_notes:some\\$c_hyphen:\\$v:\\$p",
      "distribution": "com.example.some:\\$n\\$cl:\\$v:zip"
    }
  }
```

To skip mirroring of an artifact type, leave its template out of `tgtGavTemplate`.

## gav_template_config.json
Path: `--gav-template-config-file`. *Default*: `gav_template_config.json` in the current directory. Optional.

One template for every component that isn't in `config.json`:

```
  {
    "ci_type": "$component",
    "tgtGavTemplate": {
      "notes": "$prefix.ext.release_notes:$component\\$c_hyphen:\\$v:\\$p",
      "distribution": "$prefix.dist.$client.$component:\\$n\\$c_hyphen:\\$v:\\$p"
    }
  }
```

- `$component` is replaced with the component's CI type from the registry.
- `.$client` is replaced with the DMS client code, or removed together with its dot when the component has none.

## GAV placeholders
Written escaped in JSON (`\\$v`):

- `$n` - artifact name, `$v` - version, `$p` - packaging, `$at` - artifact type
- `$prefix` - `--mvn-prefix`
- `$c_hyphen` - the classifier preceded with a hyphen
- `$c_colon` - the classifier preceded with a colon
- `$cl` (or `$c`) - the classifier without any prefix

All classifier placeholders are empty when the artifact has no classifier.

## Options
| Option | Default | Meaning |
|---|---|---|
| `--versions-limit` | `3` | Newest released versions processed per component (batch job) |
| `--dms-processes` | `3` | Components processed in parallel (batch job) |
| `--always-enqueue` | off | Send the registration message even when the artifact already exists |
| `--msg-target` | `amqp` | `amqp` or `db` |
| `--auto-register-component` | `AUTO_REGISTRATION` | Register new components from the webhook |
| `--retries-count` | `5` | Retries for failed DMS calls, 30 s apart |
| `--ci-type-release-notes` | `RELEASENOTES` | CI type for `notes` and `report` artifacts |
| `--ci-type-documentation` | `DOCS` | CI type for `documentation` artifacts |
| `--ws-bind`, `--ws-timeout`, `--ws-workers` | | Webhook service only |

## Secrets and environment variables
Every option below may be redefined via its command-line key.
Each value is read from the environment as `NAME__KEY` or `NAME_KEY` (e.g. `MVN__URL` or `MVN_URL`), otherwise from Vault (`VAULT_URL`, `VAULT_TOKEN`, `VAULT_MOUNT_POINT`).

- `AMQP_URL`, `AMQP_USER`, `AMQP_PASSWORD` - *AMQP* credentials
- `MVN_URL`, `MVN_USER`, `MVN_PASSWORD` - *MVN* credentials
- `MVN_UPLOAD_REPO`, `MVN_DOWNLOAD_REPO` - *MVN* repositories to upload to and to check for existing artifacts
- `MVN_PREFIX` - target *MVN GroupID* prefix, used as `\\$prefix` in the templates
- `DMS_URL`, `DMS_USER`, `DMS_PASSWORD` - *DMS* credentials
- `PSQL_API_URL`, `PSQL_API_USER`, `PSQL_API_PASSWORD` - CI type registry (PostgreSQL API)
- `PSQL_MQ_URL`, `PSQL_MQ_USER`, `PSQL_MQ_PASSWORD` - PostgreSQL queue, for `--msg-target db`
- `AUTO_REGISTRATION` - default for `--auto-register-component`

## Removed
Only DMS API v3 is supported. These are gone:

- options `--dms-api-version`, `--dms-crs-url`, `--dms-token`, `--max-processed-artifacts`
- environment variables `DMS_CRS_URL` and `DMS_TOKEN`
- the `enabled` key in `config.json`, and the long-deprecated `componentId` and `artifactType` keys

## Auto-registration grouping
With `--auto-register-component` the webhook registers unknown components in the delivery DB.
The *CI type group* is picked in this order:
1. **parent**: the payload has `componentVersion.parentComponent`. The component joins the group of its parent's citype: the parent's citype is looked up via `citypedms`, then its group via `citype_incs` (`dl_schema`). Client DMP bundles take this path.
2. **solution**: the payload has no `componentVersion.parentComponent` and `componentVersion.solution` is set. It goes into the group given with `--ci-type-group-solution`. *Default*: `client-solution`.
3. **own**: a group named after the component itself.

A solution is registered as non-standard (`is_standard = N`), with or without a `clientCode`.
The solution group must exist in the delivery DB before the first such registration.

When the parent is not registered, or the parent's citype has no *CI type group*, the component gets a group of its own (step 3), solution or not.
Any other API error fails the webhook.

**NOTE**: this affects **new** registrations only. Already registered components keep their group; moving them is a separate DB fix.
