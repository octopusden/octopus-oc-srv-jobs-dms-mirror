# DMS Mirroring tool for distributives
Makes mirroring of distributives from release management system (propieritary implementation) to MVN-compatible repository specified in the settings.
Target GAVs are configured with *JSON* configuration which is **NOT** provided by default.
Sends AMQP registration message.

# Configuration

## JSON
Way to provide is `--config-file` parameter in the command line. *Default*: `config.json` in the current directory.

```
  "some": {
    "ci_type": "SOMEDSTR",
    "enabled": true,
    "tgtGavTemplate": { 
      "notes": "com.example.some\\$n\\$cl:\\$v:txt",
      "distribution": "com.example.some:\\$n\\$cl:\\$v:zip"
    }
  }
```

## DEPRECATED JSON sections
Versions before *3.10* also require `componentId` and `artifactType` which is not necessary any more.
To skip mirroring of any *DMS* artifact type one may remove the corresponding *GAV* template from `tgtGavTemplate` section.

## Classificator placeholders in JSON:

`$c_hyphen` - the classifier will precede with a hyphen
`$c_colon` - the classifier will precede with a colon
`$cl` - the classifier won't have any prefixes

## Environment variables:
All of them may be redefined via command-line keys.

- `AMQP_URL`, `AMQP_USER`, `AMQP_PASSWORD` - *AMQP* credentials
- `MVN_URL`, `MVN_USER`, `MVN_PASSWORD` - *MVN* credentials
- `DMS_URL`, `DMS_USER`, `DMS_PASSWORD` - *DMS* credentials
- `DMS_CRS_URL` - *Component Registry Service* on *DMS*-side URL. **Required for DMS API v2 and below, ignored for DMS API v3**
- `DMS_TOKEN` - *DMS* bearer token for authorization - if used. This case `DMS_USER` and `DMS_PASSWORD` is **not** mandatory.
- `MVN_PREFIX` - Target *MVN GroupID* prefix - if necessary and specified in *JSON* configuration as `\\$prefix`

## DMS API v3
API *v3* is used by-default since v.1.6
API *v2* was the default in v.1.5 and below
One may set `--dms-api-version` startup parameter to any (`2` or `3`) if necessary.

**NOTE**: if API *v3* is used then `DMS_CRS_URL` is ignored and may be omitted.

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
