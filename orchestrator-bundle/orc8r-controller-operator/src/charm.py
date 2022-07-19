#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import base64
import logging

import ops.lib
from lightkube import Client, codecs
from lightkube.core.exceptions import ApiError
from lightkube.models.core_v1 import SecretVolumeSource, Volume, VolumeMount
from lightkube.resources.apps_v1 import StatefulSet
from lightkube.resources.core_v1 import Secret as SecretRes
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import Layer
from pgconnstr import ConnectionString  # type: ignore[import]

from client_relations import ClientRelations
from self_signed_certs_creator import (
    CertificateSigningRequestCreator,
    SelfSignedCertsCreator,
)

logger = logging.getLogger(__name__)
pgsql = ops.lib.use("pgsql", 1, "postgresql-charmers@lists.launchpad.net")


class MagmaOrc8rControllerCharm(CharmBase):

    DB_NAME = "magma_dev"

    def __init__(self, *args):
        """Creates a new instance of this object for each event."""
        super().__init__(*args)
        self._container_name = self._service_name = "magma-orc8r-controller"
        self._container = self.unit.get_container(self._container_name)
        self._namespace = self.model.name
        self.client_relations = ClientRelations(self, "client_relations")
        self._db = pgsql.PostgreSQLClient(self, "db")
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(
            self.on.magma_orc8r_controller_pebble_ready,
            self._on_magma_orc8r_controller_pebble_ready,
        )
        self.framework.observe(
            self._db.on.database_relation_joined, self._on_database_relation_joined
        )
        self.framework.observe(self.on.remove, self._on_remove)

    def _on_install(self, event):
        """Runs each time the charm is installed."""
        if self._container.can_connect():
            self._create_magma_orc8r_secrets()
            self._mount_volumes()
        else:
            self.unit.status = WaitingStatus("Waiting for container to be ready...")
            event.defer()
            return

    def _on_remove(self, event):
        self.unit.status = MaintenanceStatus("Removing Magma Orc8r secrets...")
        self._delete_secrets()

    def _on_magma_orc8r_controller_pebble_ready(self, event):
        if not self._check_db_relation_has_been_established():
            self.unit.status = BlockedStatus("Waiting for database relation to be established...")
            event.defer()
            return
        self._configure_magma_orc8r_controller()

    def _create_magma_orc8r_secrets(self):
        self.unit.status = MaintenanceStatus("Creating Magma Orc8r secrets...")
        self._generate_self_signed_ssl_certs()
        self._create_secrets()

    def _delete_secrets(self) -> None:
        """Delete Kubernetes secrets created by the create_secrets method"""
        client = Client()
        for secret in self._secrets:
            client.delete(SecretRes, name=secret, namespace=self._namespace)
        logger.info("Deleted Kubernetes secrets!")

    def _generate_self_signed_ssl_certs(self):
        logger.info("Creating self-signed certificates...")
        self._generate_admin_operator_cert()
        self._generate_controller_cert()
        self._generate_bootstrapper_cert()
        self._generate_vpn_ca_cert()

    def _generate_admin_operator_cert(self):
        # Generate Certifier certificate to sign AdminOperator certificate
        certifier_cert = SelfSignedCertsCreator([f"certifier.{self.model.config['domain']}"], [])
        self._container.push("/tmp/certs/certifier.key", certifier_cert.private_key)  # type: ignore[arg-type]  # noqa: E501
        self._container.push("/tmp/certs/certifier.pem", certifier_cert.cert)  # type: ignore[arg-type]  # noqa: E501

        # Generate AdminOperator private key to create CSR
        admin_operator_private_key = SelfSignedCertsCreator(["admin_operator"], [])
        self._container.push(
            "/tmp/certs/admin_operator.key.pem", admin_operator_private_key.private_key  # type: ignore[arg-type]  # noqa: E501
        )
        # Generate AdminOperator CSR (Certificate Signing Request)
        admin_operator_csr = CertificateSigningRequestCreator(
            [f"certifier.{self.model.config['domain']}"],
            signing_key=admin_operator_private_key.private_key,
        )
        self._container.push("/tmp/certs/admin_operator.csr", admin_operator_csr.csr)  # type: ignore[arg-type]  # noqa: E501
        # Generate AdminOperator certificate
        admin_operator_cert = SelfSignedCertsCreator(
            ["admin_operator"],
            csr=admin_operator_csr.csr,
            signing_cert=certifier_cert.cert,
            signing_key=certifier_cert.private_key,
        )
        self._container.push("/tmp/certs/admin_operator.pem", admin_operator_cert.cert)  # type: ignore[arg-type]  # noqa: E501

    def _generate_bootstrapper_cert(self):
        bootstrapper_cert = SelfSignedCertsCreator(
            [f"bootstrapper.{self.model.config['domain']}"], []
        )
        self._container.push("/tmp/certs/bootstrapper.key", bootstrapper_cert.private_key)  # type: ignore[arg-type]  # noqa: E501

    def _generate_controller_cert(self):
        # Generate rootCA certificate to sign AdminOperator certificate
        rootca_cert = SelfSignedCertsCreator([f"rootca.{self.model.config['domain']}"], [])
        self._container.push("/tmp/certs/rootCA.key", rootca_cert.private_key)  # type: ignore[arg-type]  # noqa: E501
        self._container.push("/tmp/certs/rootCA.pem", rootca_cert.cert)  # type: ignore[arg-type]

        # Generate Controller private key to create CSR
        controller_private_key = SelfSignedCertsCreator([f"*.{self.model.config['domain']}"], [])
        self._container.push("/tmp/certs/controller.key", controller_private_key.private_key)  # type: ignore[arg-type]  # noqa: E501
        # Generate Controller CSR (Certificate Signing Request)
        controller_csr = CertificateSigningRequestCreator(
            [f"*.{self.model.config['domain']}"], signing_key=controller_private_key.private_key
        )
        self._container.push("/tmp/certs/controller.csr", controller_csr.csr)  # type: ignore[arg-type]  # noqa: E501
        # Generate Controller certificate
        controller_cert = SelfSignedCertsCreator(
            [f"*.{self.model.config['domain']}", f"*.nms.{self.model.config['domain']}"],
            csr=controller_csr.csr,
            signing_cert=rootca_cert.cert,
            signing_key=rootca_cert.private_key,
        )
        self._container.push("/tmp/certs/controller.crt", controller_cert.cert)  # type: ignore[arg-type]  # noqa: E501

    def _generate_vpn_ca_cert(self):
        vpn_ca_cert = SelfSignedCertsCreator([f"vpn.{self.model.config['domain']}"], [])
        self._container.push("/tmp/certs/vpn_ca.key", vpn_ca_cert.private_key)  # type: ignore[arg-type]  # noqa: E501
        self._container.push("/tmp/certs/vpn_ca.crt", vpn_ca_cert.cert)  # type: ignore[arg-type]  # noqa: E501

    def _mount_volumes(self) -> None:
        """Patch the StatefulSet to include certs secret mount."""
        self.unit.status = MaintenanceStatus(
            "Mounting additional volumes required by the magma-controller container..."
        )
        client = Client()
        stateful_set = client.get(StatefulSet, name=self.app.name, namespace=self._namespace)
        stateful_set.spec.template.spec.volumes.extend(self._volumes)  # type: ignore[attr-defined]  # noqa: E501
        stateful_set.spec.template.spec.containers[1].volumeMounts.extend(  # type: ignore[attr-defined]  # noqa: E501
            self._volume_mounts
        )
        client.patch(StatefulSet, name=self.app.name, obj=stateful_set, namespace=self._namespace)
        logger.info("Additional K8s resources for magma-controller container applied!")

    @property
    def _volumes(self) -> list:
        """Returns a list of volumes required by the magma-controller container."""
        return [
            Volume(
                name="certs",
                secret=SecretVolumeSource(secretName="orc8r-certs"),
            ),
            Volume(
                name="supervisor",
                secret=SecretVolumeSource(secretName="supervisor-conf"),
            ),
        ]

    @property
    def _volume_mounts(self) -> list:
        """Returns a list of volume mounts required by the magma-controller container."""
        return [
            VolumeMount(
                mountPath="/var/opt/magma/certs",
                name="certs",
                readOnly=True,
            ),
            VolumeMount(
                mountPath="/etc/supervisor/conf.d",
                name="supervisor",
                readOnly=False,
            ),
        ]

    def _on_database_relation_joined(self, event):
        """Event handler for database relation change.
        - Sets the event.database field on the database joined event.
        - Required because setting the database name is only possible
          from inside the event handler per https://github.com/canonical/ops-lib-pgsql/issues/2
        - Sets our database parameters based on what was provided
          in the relation event.
        """
        db_connection_string = event.master
        if self.unit.is_leader() and db_connection_string is not None:
            event.database = self.DB_NAME
        elif event.database != self.DB_NAME or db_connection_string is None:
            event.defer()
            return

    def _configure_magma_orc8r_controller(self):
        """Adds layer to pebble config if the proposed config is different from the current one."""
        self.unit.status = MaintenanceStatus("Configuring pod")
        plan = self._container.get_plan()
        layer = self._pebble_layer
        if plan.services != layer.services:
            self._container.add_layer(self._container_name, layer, combine=True)
            self._container.restart(self._service_name)
            logger.info(f"Restarted container {self._service_name}")
            self.unit.status = ActiveStatus()

    def _check_db_relation_has_been_established(self):
        """Validates that database relation is ready (that there is a relation and that credentials
        have been passed)."""
        if not self._get_db_connection_string:
            self.unit.status = WaitingStatus("Waiting for db relation to be ready...")
            return False
        return True

    @property
    def _pebble_layer(self) -> Layer:
        """Returns pebble layer for the charm."""
        return Layer(
            {
                "summary": f"{self._service_name} layer",
                "description": f"pebble config layer for {self._service_name}",
                "services": {
                    self._service_name: {
                        "override": "replace",
                        "summary": self._service_name,
                        "startup": "enabled",
                        "command": "/usr/bin/supervisord",
                        "environment": {
                            "DATABASE_SOURCE": f"dbname={self._get_db_connection_string.dbname} "
                            f"user={self._get_db_connection_string.user} "
                            f"password={self._get_db_connection_string.password} "
                            f"host={self._get_db_connection_string.host} "
                            f"sslmode=disable",
                            "SQL_DRIVER": "postgres",
                            "SQL_DIALECT": "psql",
                            "SERVICE_HOSTNAME": "localhost",
                            "VERSION_TAG": "LOCAL-DEV",
                            "HELM_VERSION_TAG": "LOCAL-DEV",
                            "SERVICE_REGISTRY_MODE": "yaml",
                            "TEST_MODE": "1",
                        },
                    },
                },
            },
        )

    @property
    def _get_db_connection_string(self):
        """Returns DB connection string provided by the DB relation."""
        try:
            db_relation = self.model.get_relation("db")
            return ConnectionString(db_relation.data[db_relation.app]["master"])  # type: ignore[index, union-attr]  # noqa: E501
        except (AttributeError, KeyError):
            return None

    def _create_secrets(self) -> bool:
        """Creates Secrets which are provided by the magma-orc8r-controller."""
        client = Client()
        for secret_name, secret_data in self._secrets.items():
            context = {
                "app_name": self.app.name,
                "namespace": self._namespace,
                "secret_name": secret_name,
                "secret_data": secret_data,
            }
            with open("src/templates/secret.yaml.j2") as secret_manifest:
                secret = codecs.load_all_yaml(secret_manifest, context=context)[0]
                try:
                    client.create(secret)
                except ApiError as e:
                    logger.info("Failed to create Secret: %s.", str(secret.to_dict()))
                    raise e
        return True

    @property
    def _secrets(self) -> dict:
        """Return a list of secrets to be provided by the magma-controller."""
        nms_certs_data = {
            "controller.crt": self._encode_in_base64(
                open("/tmp/certs/controller.crt", "rb").read()
            ),
            "controller.key": self._encode_in_base64(
                open("/tmp/certs/controller.key", "rb").read()
            ),
            "admin_operator.key.pem": self._encode_in_base64(
                open("/tmp/certs/admin_operator.key.pem", "rb").read()
            ),
            "admin_operator.pem": self._encode_in_base64(
                open("/tmp/certs/admin_operator.pem", "rb").read()
            ),
        }
        orc8r_certs_data = {
            "admin_operator.pem": self._encode_in_base64(
                open("/tmp/certs/admin_operator.pem", "rb").read()
            ),
            "controller.crt": self._encode_in_base64(
                open("/tmp/certs/controller.crt", "rb").read()
            ),
            "controller.key": self._encode_in_base64(
                open("/tmp/certs/controller.key", "rb").read()
            ),
            "bootstrapper.key": self._encode_in_base64(
                open("/tmp/certs/bootstrapper.key", "rb").read()
            ),
            "certifier.key": self._encode_in_base64(open("/tmp/certs/certifier.key", "rb").read()),
            "certifier.pem": self._encode_in_base64(open("/tmp/certs/certifier.pem", "rb").read()),
            "vpn_ca.key": self._encode_in_base64(open("/tmp/certs/vpn_ca.key", "rb").read()),
            "vpn_ca.crt": self._encode_in_base64(open("/tmp/certs/vpn_ca.crt", "rb").read()),
            "rootCA.key": self._encode_in_base64(open("/tmp/certs/rootCA.key", "rb").read()),
            "rootCA.pem": self._encode_in_base64(open("/tmp/certs/rootCA.pem", "rb").read()),
        }
        supervisor_data = {
            "supervisord.conf": self._encode_in_base64(open("src/supervisord.conf", "rb").read())
        }
        return {
            "nms-certs": nms_certs_data,
            "orc8r-certs": orc8r_certs_data,
            "supervisor-conf": supervisor_data,
        }

    @staticmethod
    def _encode_in_base64(byte_string: bytes):
        """Encodes given byte string in Base64"""
        return base64.b64encode(byte_string).decode("utf-8")


if __name__ == "__main__":
    main(MagmaOrc8rControllerCharm)
