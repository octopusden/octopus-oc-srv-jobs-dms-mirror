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
API *v2* is used by-default
Startup parameter `--dms-api-version` is to be set to `3` if *v3* is to be used. `DMS_CRS_URL` is ignored this case.
