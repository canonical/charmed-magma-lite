#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from typing import List

from charms.nginx_ingress_integrator.v0.ingress import IngressRequires

from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from lightkube import Client
from lightkube.models.core_v1 import SecretVolumeSource, Volume, VolumeMount
from lightkube.resources.apps_v1 import StatefulSet
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import Layer

logger = logging.getLogger(__name__)


class MagmaOrc8rNginxCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self._container_name = self._service_name = "magma-orc8r-nginx"
        self._namespace = self.model.name
        self._container = self.unit.get_container(self._container_name)
        self.framework.observe(
            self.on.magma_orc8r_nginx_pebble_ready, self._on_magma_orc8r_nginx_pebble_ready
        )
        self.framework.observe(
            self.on.controller_relation_changed, self._on_controller_relation_changed
        )
        self.service_patcher = KubernetesServicePatch(
            self,
            [
                ("open", 7444, 8444, 31694),
                ("health", 80, 80, 32035),
                ("clientcert", 7443, 8443, 30130),
                ("api", 9443, 9443, 30794),
            ],
            "LoadBalancer",
        )
        self.ingress = IngressRequires(
            self,
            {
                "service-hostname": self._external_hostname,
                "service-name": self.app.name,
                "service-port": 9443,
            },
        )

    @property
    def _external_hostname(self):
        return f"orc8r-controller.{self._get_domain_name}"

    def _on_magma_orc8r_nginx_pebble_ready(self, event):
        if not self._relations_ready:
            event.defer()
            return
        self._configure_pebble_layer(event)

    def _on_controller_relation_changed(self, event):
        """Mounts certificates required by the nms-magmalte."""
        if not self._orc8r_certs_mounted:
            self.unit.status = MaintenanceStatus("Mounting NMS certificates...")
            self._mount_controller_certs()

    def _mount_controller_certs(self) -> None:
        """Patch the StatefulSet to include controller certs secret mount."""
        self.unit.status = MaintenanceStatus(
            "Mounting additional volumes required by the magma-orc8r-nginx container..."
        )
        client = Client()
        stateful_set = client.get(StatefulSet, name=self.app.name, namespace=self._namespace)
        stateful_set.spec.template.spec.volumes.extend(self._magma_orc8r_nginx_volumes)  # type: ignore[attr-defined]  # noqa: E501
        stateful_set.spec.template.spec.containers[1].volumeMounts.extend(  # type: ignore[attr-defined]  # noqa: E501
            self._magma_orc8r_nginx_volume_mounts
        )
        client.patch(StatefulSet, name=self.app.name, obj=stateful_set, namespace=self._namespace)
        logger.info("Additional K8s resources for magma-orc8r-nginx container applied!")

    def _configure_pebble_layer(self, event):
        self.unit.status = MaintenanceStatus(
            f"Configuring pebble layer for {self._service_name}..."
        )
        pebble_layer = self._pebble_layer
        if self._container.can_connect():
            plan = self._container.get_plan()
            if plan.services != pebble_layer.services:
                self._generate_nginx_config()
                self._container.add_layer(self._container_name, pebble_layer, combine=True)
                self._container.restart(self._service_name)
                logger.info(f"Restarted container {self._service_name}")
                self.unit.status = ActiveStatus()
        else:
            self.unit.status = WaitingStatus(f"Waiting for {self._container} to be ready...")
            event.defer()
            return

    def _generate_nginx_config(self):
        """Generates nginx config to /etc/nginx/nginx.conf."""
        logger.info("Generating nginx config file...")
        process = self._container.exec(
            command=["/usr/local/bin/generate_nginx_configs.py"],
            environment={
                "PROXY_BACKENDS": "orc8r-controller",
                "CONTROLLER_HOSTNAME": self._external_hostname,
                "RESOLVER": "kube-dns.kube-system.svc.cluster.local valid=10s",
                "SERVICE_REGISTRY_MODE": "yaml",
                "TEST_MODE": "1",
                "SSL_CERTIFICATE": "/var/opt/magma/certs/controller.crt",
                "SSL_CERTIFICATE_KEY": "/var/opt/magma/certs/controller.key",
                "SSL_CLIENT_CERTIFICATE": "/var/opt/magma/certs/certifier.pem",
            },
        )
        stdout, _ = process.wait_output()
        logger.info(stdout)

    @property
    def _pebble_layer(self) -> Layer:
        return Layer(
            {
                "summary": f"{self._service_name} pebble layer",
                "services": {
                    self._service_name: {
                        "override": "replace",
                        "startup": "enabled",
                        "command": "nginx",
                        "environment": {},
                    }
                },
            }
        )

    @property
    def _magma_orc8r_nginx_volumes(self) -> List[Volume]:
        """Returns the additional volumes required by the magma-orc8r-nginx."""
        return [
            Volume(
                name="certs",
                secret=SecretVolumeSource(secretName="orc8r-certs"),
            ),
        ]

    @property
    def _magma_orc8r_nginx_volume_mounts(self) -> List[VolumeMount]:
        """Returns the additional volume mounts for the magma-orc8r-nginx container."""
        return [
            VolumeMount(
                mountPath="/var/opt/magma/certs",
                name="certs",
            ),
        ]

    @property
    def _relations_ready(self) -> bool:
        """Checks whether required relations are ready."""
        if not self.model.get_relation("controller"):
            msg = f"Waiting for relations: {'controller'}"
            self.unit.status = BlockedStatus(msg)
            return False
        if not self._get_domain_name:
            self.unit.status = WaitingStatus("Waiting for controller relation to be ready...")
            return False
        return True

    @property
    def _orc8r_certs_mounted(self) -> bool:
        """Check to see if the NMS certs have already been mounted."""
        client = Client()
        statefulset = client.get(StatefulSet, name=self.app.name, namespace=self._namespace)
        return all(
            volume_mount in statefulset.spec.template.spec.containers[1].volumeMounts  # type: ignore[attr-defined]  # noqa: E501
            for volume_mount in self._magma_orc8r_nginx_volume_mounts
        )

    @property
    def _get_domain_name(self):
        """Gets domain name for the data bucket sent by controller relation."""
        controller_relation = self.model.get_relation("controller")
        units = controller_relation.units
        logger.info(f"controller_relation: {controller_relation}")
        logger.info(f"Controller relation data: {controller_relation.data}")
        try:
            return controller_relation.data[next(iter(units))]["domain"]
        except KeyError:
            return None
        except StopIteration:
            return None


if __name__ == "__main__":
    main(MagmaOrc8rNginxCharm)
