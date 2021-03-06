# Copyright 2016 Hewlett Packard Enterprise Development LP
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import mock
from oslo_config import cfg
import oslo_messaging

from neutron.api.rpc.callbacks import events
from neutron.api.rpc.callbacks import resources
from neutron.api.rpc.handlers import resources_rpc
from neutron.extensions import portbindings
from neutron import manager
from neutron.objects import trunk as trunk_obj
from neutron.services.trunk import constants
from neutron.services.trunk import drivers
from neutron.services.trunk import plugin as trunk_plugin
from neutron.services.trunk.rpc import constants as rpc_consts
from neutron.services.trunk.rpc import server
from neutron.tests import base
from neutron.tests.unit.plugins.ml2 import test_plugin


class TrunkSkeletonTest(test_plugin.Ml2PluginV2TestCase):
    def setUp(self):
        super(TrunkSkeletonTest, self).setUp()
        self.drivers_patch = mock.patch.object(drivers, 'register').start()
        self.compat_patch = mock.patch.object(
            trunk_plugin.TrunkPlugin, 'check_compatibility').start()
        self.trunk_plugin = trunk_plugin.TrunkPlugin()
        self.trunk_plugin.add_segmentation_type('vlan', lambda x: True)
        self.core_plugin = manager.NeutronManager.get_plugin()

    def _create_test_trunk(self, port, subports=None):
        subports = subports if subports else []
        trunk = {'port_id': port['port']['id'],
                 'tenant_id': 'test_tenant',
                 'sub_ports': subports
                 }
        response = (
            self.trunk_plugin.create_trunk(self.context, {'trunk': trunk}))
        return response

    @mock.patch("neutron.api.rpc.callbacks.resource_manager."
                "ResourceCallbacksManager.register")
    @mock.patch("neutron.common.rpc.get_server")
    def test___init__(self, mocked_get_server, mocked_registered):
        test_obj = server.TrunkSkeleton()
        mocked_registered.assert_called_with(server.trunk_by_port_provider,
                                             resources.TRUNK)
        trunk_target = oslo_messaging.Target(topic=rpc_consts.TRUNK_BASE_TOPIC,
                                             server=cfg.CONF.host,
                                             fanout=False)
        mocked_get_server.assert_called_with(trunk_target, [test_obj])

    def test_update_subport_bindings(self):
        with self.port() as _parent_port:
            parent_port = _parent_port
        trunk = self._create_test_trunk(parent_port)
        port_data = {portbindings.HOST_ID: 'trunk_host_id'}
        self.core_plugin.update_port(
            self.context, parent_port['port']['id'], {'port': port_data})
        subports = []
        for vid in range(0, 3):
            with self.port() as new_port:
                obj = trunk_obj.SubPort(
                    context=self.context,
                    trunk_id=trunk['id'],
                    port_id=new_port['port']['id'],
                    segmentation_type='vlan',
                    segmentation_id=vid)
                subports.append(obj)

        test_obj = server.TrunkSkeleton()
        test_obj._trunk_plugin = self.trunk_plugin
        test_obj._core_plugin = self.core_plugin
        updated_subports = test_obj.update_subport_bindings(self.context,
                                                            subports=subports)
        self.assertIn(trunk['id'], updated_subports)
        for port in updated_subports[trunk['id']]:
            self.assertEqual('trunk_host_id', port[portbindings.HOST_ID])

    @mock.patch('neutron.api.rpc.callbacks.producer.registry.provide')
    def test_update_trunk_status(self, _):
        with self.port() as _parent_port:
            parent_port = _parent_port
        trunk = self._create_test_trunk(parent_port)
        trunk_id = trunk['id']

        test_obj = server.TrunkSkeleton()
        test_obj._trunk_plugin = self.trunk_plugin
        self.assertEqual(constants.PENDING_STATUS, trunk['status'])
        test_obj.update_trunk_status(self.context,
                                     trunk_id,
                                     constants.ACTIVE_STATUS)
        updated_trunk = self.trunk_plugin.get_trunk(self.context, trunk_id)
        self.assertEqual(constants.ACTIVE_STATUS, updated_trunk['status'])


class TrunkStubTest(base.BaseTestCase):
    def setUp(self):
        super(TrunkStubTest, self).setUp()
        self.test_obj = server.TrunkStub()

    def test___init__(self):
        self.assertIsInstance(self.test_obj._resource_rpc,
                              resources_rpc.ResourcesPushRpcApi)

    @mock.patch("neutron.api.rpc.handlers.resources_rpc.ResourcesPushRpcApi."
                "push")
    def test_trunk_created(self, mocked_push):
        m_context = mock.Mock()
        m_trunk = mock.Mock()
        self.test_obj.trunk_created(m_context, m_trunk)
        mocked_push.assert_called_with(m_context, [m_trunk], events.CREATED)

    @mock.patch("neutron.api.rpc.handlers.resources_rpc.ResourcesPushRpcApi."
                "push")
    def test_trunk_deleted(self, mocked_push):
        m_context = mock.Mock()
        m_trunk = mock.Mock()
        self.test_obj.trunk_deleted(m_context, m_trunk)
        mocked_push.assert_called_with(m_context, [m_trunk], events.DELETED)

    @mock.patch("neutron.api.rpc.handlers.resources_rpc.ResourcesPushRpcApi."
                "push")
    def test_subports_added(self, mocked_push):
        m_context = mock.Mock()
        m_subports = mock.Mock()
        self.test_obj.subports_added(m_context, m_subports)
        mocked_push.assert_called_with(m_context, m_subports, events.CREATED)

    @mock.patch("neutron.api.rpc.handlers.resources_rpc.ResourcesPushRpcApi."
                "push")
    def test_subports_deleted(self, mocked_push):
        m_context = mock.Mock()
        m_subports = mock.Mock()
        self.test_obj.subports_deleted(m_context, m_subports)
        mocked_push.assert_called_with(m_context, m_subports, events.DELETED)
