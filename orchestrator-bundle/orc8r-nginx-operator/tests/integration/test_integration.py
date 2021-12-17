#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest  # type: ignore[import]  # noqa: F401

logger = logging.getLogger(__name__)
METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
CONTROLLER_METADATA = yaml.safe_load(
    Path("../orc8r-controller-operator/metadata.yaml").read_text()
)
NGINX_APPLICATION_NAME = "orc8r-nginx"
NGINX_IMAGE_NAME = "magma-orc8r-nginx-lite-image"
CONTROLLER_APPLICATION_NAME = "orc8r-controller"
CONTROLLER_IMAGE_NAME = "magma-orc8r-controller-image"


class TestOrc8rNginx:
    @pytest.fixture(scope="module")
    async def setup(self, ops_test):
        await asyncio.gather(
            self._deploy_postgresql(ops_test), self._deploy_orc8r_controller(ops_test)
        )

    @pytest.mark.abort_on_fail
    async def test_build_and_deploy(self, ops_test, setup):
        charm = await ops_test.build_charm(".")
        resources = {
            NGINX_IMAGE_NAME: METADATA["resources"][NGINX_IMAGE_NAME]["upstream-source"],
        }
        await ops_test.model.deploy(
            charm, resources=resources, application_name=NGINX_APPLICATION_NAME, trust=True
        )
        await ops_test.model.add_relation(
            relation1=NGINX_APPLICATION_NAME, relation2="orc8r-controller:controller"
        )
        await ops_test.model.wait_for_idle(
            apps=[NGINX_APPLICATION_NAME], status="active", timeout=1000
        )

    @staticmethod
    async def _deploy_postgresql(ops_test):
        await ops_test.model.deploy("postgresql-k8s", application_name="postgresql-k8s")
        await ops_test.model.wait_for_idle(apps=["postgresql-k8s"], status="active", timeout=1000)

    @staticmethod
    async def _deploy_orc8r_controller(ops_test):
        charm = await ops_test.build_charm("../orc8r-controller-operator/")
        resources = {
            CONTROLLER_IMAGE_NAME: CONTROLLER_METADATA["resources"][CONTROLLER_IMAGE_NAME][
                "upstream-source"
            ],
        }
        await ops_test.model.deploy(
            charm,
            resources=resources,
            application_name=CONTROLLER_APPLICATION_NAME,
            config={"domain": "example.com"},
            trust=True,
        )
        await ops_test.model.add_relation(
            relation1=CONTROLLER_APPLICATION_NAME, relation2="postgresql-k8s:db"
        )
        await ops_test.model.wait_for_idle(
            apps=[CONTROLLER_APPLICATION_NAME], status="active", timeout=1000
        )
