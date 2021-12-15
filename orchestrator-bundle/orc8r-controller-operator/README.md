# magma-orchestrator-lite

## Description

This charm is for deploying magma controller which includes all of orchestrator's core services.

## Usage

You can deploy the controller from a locally built package:

```bash
juju deploy postgresql-k8s
juju deploy ./magma-orc8r-controller_ubuntu-20.04-amd64.charm \
  orc8r-controller \
  --config domain=example.com \
  --resource magma-orc8r-controller-image=docker.artifactory.magmacore.org/controller:1.6.0
juju relate orc8r-controller postgresql-k8s:db
```

## Configuration
- **domain** - Domain for self-signed certs. Use only when **use-self-signed-ssl-certs** set to **True**


## Relations

### Requires
The magma-orc8r-certifier service relies on a relation to a Database. The current setup has only 
been tested with relation to the `postgresql-k8s` charm.

## OCI Images

Default: docker.artifactory.magmacore.org/controller:latest
