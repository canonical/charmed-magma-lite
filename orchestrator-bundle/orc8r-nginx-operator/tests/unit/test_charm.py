# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, PropertyMock, patch

from ops.model import BlockedStatus
from ops.testing import Harness

from charm import MagmaOrc8rNginxCharm


class TestCharm(unittest.TestCase):
    @patch("charm.KubernetesServicePatch", lambda x, y, z: None)
    def setUp(self):
        self.harness = Harness(MagmaOrc8rNginxCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_given_charm_when_pebble_ready_event_emitted_and_no_relations_established_then_charm_goes_to_blocked_state(  # noqa: E501
        self,
    ):
        event = Mock()
        self.harness.charm.on.magma_orc8r_nginx_pebble_ready.emit(event)
        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for relations: controller"),
        )

    def test_given_charm_when_pebble_ready_event_emitted_and_all_relations_established_then_configure_pebble_layer_is_called(  # noqa: E501
        self,
    ):
        event = Mock()
        with patch.object(MagmaOrc8rNginxCharm, "_configure_pebble_layer", event) as mock:
            relation_id = self.harness.add_relation("controller", "magma-orc8r-controller")
            self.harness.add_relation_unit(relation_id, "magma-orc8r-controller/0")
            with patch(
                "charm.MagmaOrc8rNginxCharm._get_domain_name", new_callable=PropertyMock
            ) as domain_name:
                domain_name.return_value = "test.domain.com"
                self.harness.charm.on.magma_orc8r_nginx_pebble_ready.emit(event)
        mock.assert_called_once()
