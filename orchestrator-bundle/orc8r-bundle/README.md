# magma-orc8r-lite

## Overview
Orchestrator is a Magma service that provides a simple and consistent way to 
configure and monitor the wireless network securely. The metrics acquired through the platform 
allows you to see the analytics and traffic flows of the wireless users through the Magma web UI.


## Hardware requirements
- CPU: 8 vCPU's
- Memory: 32 GB
- Storage: 100 GB

## Pre-requisites
This bundle of charms requires the following:
1. Ubuntu (20.04)
2. Microk8s (v1.22.4)
3. Juju (2.9.21)

### 1. Ubuntu
- Install Ubuntu following the [official documentation](https://releases.ubuntu.com/20.04/).

### 2. Microk8s
- Install and configure Microk8s on your Ubuntu VM following the 
[official documentation](https://microk8s.io/docs/getting-started).
- Enable the following add-ons:

```bash
microk8s enable ingress dns storage
```

### 3. Juju
- Install Juju following the [official documentation](https://juju.is/docs/olm/installing-juju).
- Create a Juju controller:

```bash
juju bootstrap microk8s microk8s-localhost
```

- Create a new Juju model:

```bash
juju add-model orchestrator
```

## Usage

```bash
juju deploy magma-orc8r-lite
```

## References
- [Ubuntu](https://ubuntu.com/)
- [Microk8s](https://microk8s.io/)
- [Juju](https://juju.is/docs)
- [Magma](https://docs.magmacore.org/docs/basics/introduction.html)
- [Orchestrator](https://docs.magmacore.org/docs/orc8r/architecture_overview)
