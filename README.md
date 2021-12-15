# charmed-magma-lite

Deploy the bundle:
```bash
juju deploy magma-orc8r-lite
```

Deploy each component:

```bash
juju deploy postgresql-k8s
juju deploy ./magma-orc8r-controller_ubuntu-20.04-amd64.charm   orc8r-controller   --config domain=example.com   --resource magma-orc8r-controller-image=docker.io/library/orc8r_controller:latest
juju deploy ./magma-orc8r-nginx_ubuntu-20.04-amd64.charm --resource magma-orc8r-nginx-image=docker.io/library/orc8r_nginx:latest
juju relate magma-orc8r-nginx:controller orc8r-controller:controller
juju relate orc8r-controller postgresql-k8s:db
```
