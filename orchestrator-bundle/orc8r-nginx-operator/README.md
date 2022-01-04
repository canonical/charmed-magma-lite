# magma-orc8r-nginx

## Description

magma-orc8r-nginx facilitates communication the outside world and orchestrator.

## Usage

**magma-orc8r-nginx** can be deployed via Juju command line using below commands:

```bash
juju deploy ./magma-orc8r-nginx-lite_ubuntu-20.04-amd64.charm --resource magma-orc8r-nginx-image=docker.artifactory.magmacore.org/nginx:latest
```

**IMPORTANT**: For now, deploying this charm must be done with an alias as shown above.

To work correctly, **magma-orc8r-nginx** requires relationship to **magma-orc8r-controller** and 
**nginx-ingress-integratior**:

```bash
juju relate magma-orc8r-nginx-lite:controller orc8r-controller:controller
juju relate magma-orc8r-nginx-lite:ingress nginx-ingress-integrator
```

Before running any **juju deploy** commands, make sure charm has been built using:
```bash
charmcraft pack
```

## Relations

The only supported relation is:

- [magma-orc8r-certifier](https://github.com/canonical/charmed-magma/tree/main/orchestrator-bundle/orc8r-certifier-operator) - 
  magma-orc8r-certifier maintains and verifies signed client certificates and their associated
  identities.

## OCI Images

Default: docker.artifactory.magmacore.org/nginx:latest
