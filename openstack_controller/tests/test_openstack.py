# (C) Datadog, Inc. 2018
# All rights reserved
# Licensed under Simplified BSD License (see LICENSE)
import copy
import os

import mock
from unittest.mock import ANY

from datadog_checks.openstack_controller import OpenStackControllerCheck
from datadog_checks.base import AgentCheck
from datadog_checks.openstack_controller.api import AbstractApi
from . import common

INSTANCES = common.MOCK_CONFIG['instances']


def test_parse_uptime_string(aggregator):
    instances = copy.deepcopy(INSTANCES)
    instances[0]['tags'] = ['optional:tag1']
    init_config = common.MOCK_CONFIG['init_config']
    check = OpenStackControllerCheck('openstack_controller', init_config, {}, instances=instances)
    response = u' 16:53:48 up 1 day, 21:34,  3 users,  load average: 0.04, 0.14, 0.19\n'
    uptime_parsed = check._parse_uptime_string(response)
    assert uptime_parsed == [0.04, 0.14, 0.19]


@mock.patch(
    'datadog_checks.openstack_controller.OpenStackControllerCheck.get_servers_detail',
    return_value=common.MOCK_NOVA_SERVERS,
)
def test_populate_servers_cache_between_runs(servers_detail, aggregator):
    """
    Ensure the cache contains the expected VMs between check runs.
    """

    check = OpenStackControllerCheck("test", {'ssl_verify': False}, {}, instances=INSTANCES)

    # Start off with a list of servers
    check.servers_cache = copy.deepcopy(common.SERVERS_CACHE_MOCK)
    # Update the cached list of servers based on what the endpoint returns
    check.populate_servers_cache(
        {
            'testproj': {"id": '6f70656e737461636b20342065766572', "name": "testproj"},
            'blacklist_1': {"id": 'blacklist_1', "name": 'blacklist_1'},
            'blacklist_2': {"id": 'blacklist_2', "name": 'blacklist_2'},
        },
        [],
    )
    servers = check.servers_cache['servers']
    assert 'server-1' not in servers
    assert 'server_newly_added' in servers
    assert 'other-1' in servers
    assert 'other-2' in servers


@mock.patch(
    'datadog_checks.openstack_controller.OpenStackControllerCheck.get_servers_detail',
    return_value=common.MOCK_NOVA_SERVERS,
)
def test_populate_servers_cache_with_project_name_none(servers_detail, aggregator):
    """
    Ensure the cache contains the expected VMs between check runs.
    """
    check = OpenStackControllerCheck("test", {'ssl_verify': False}, {}, instances=INSTANCES)

    # Start off with a list of servers
    check.servers_cache = copy.deepcopy(common.SERVERS_CACHE_MOCK)
    # Update the cached list of servers based on what the endpoint returns
    check.populate_servers_cache(
        {
            '': {"id": '6f70656e737461636b20342065766572', "name": None},
            'blacklist_1': {"id": 'blacklist_1', "name": 'blacklist_1'},
            'blacklist_2': {"id": 'blacklist_2', "name": 'blacklist_2'},
        },
        [],
    )
    servers = check.servers_cache['servers']
    assert 'server_newly_added' not in servers
    assert 'server-1' not in servers
    assert 'other-1' in servers
    assert 'other-2' in servers


@mock.patch('datadog_checks.openstack_controller.api.ApiFactory.create',
            return_value=mock.MagicMock(AbstractApi))
def test_check(mock_api, aggregator):
    check = OpenStackControllerCheck("test", {'ssl_verify': False}, {}, instances=INSTANCES)

    check.check(INSTANCES[0])

    aggregator.assert_service_check('openstack.keystone.api.up', AgentCheck.OK)
    aggregator.assert_service_check('openstack.nova.api.up', AgentCheck.OK)
    aggregator.assert_service_check('openstack.neutron.api.up', AgentCheck.OK)
    mock_api.assert_called_with(ANY, ANY, INSTANCES[0])


@mock.patch('datadog_checks.openstack_controller.api.ApiFactory.create',
            return_value=mock.MagicMock(AbstractApi))
def test_check_with_config_file(mock_api, aggregator):
    instances = copy.deepcopy(INSTANCES)
    del instances[0]['keystone_server_url']
    instances[0]['openstack_config_file_path'] = os.path.abspath('./tests/fixtures/openstack_config.yaml')
    instances[0]['openstack_cloud_name'] = 'test_cloud'
    check = OpenStackControllerCheck("test", {'ssl_verify': False}, {}, instances=instances)

    check.check(instances[0])

    aggregator.assert_service_check('openstack.keystone.api.up', AgentCheck.OK)
    aggregator.assert_service_check('openstack.nova.api.up', AgentCheck.OK)
    aggregator.assert_service_check('openstack.neutron.api.up', AgentCheck.OK)
    mock_api.assert_called_with(ANY, ANY, instances[0])


def get_server_details_response(params, timeout=None):
    if 'marker' not in params:
        return common.MOCK_NOVA_SERVERS_PAGINATED
    return common.EMPTY_NOVA_SERVERS


@mock.patch(
    'datadog_checks.openstack_controller.OpenStackControllerCheck.get_servers_detail',
    side_effect=get_server_details_response,
)
def test_get_paginated_server(servers_detail, aggregator):
    """
    Ensure the server cache is updated while using pagination
    """

    check = OpenStackControllerCheck(
        "test", {'ssl_verify': False, 'paginated_server_limit': 1}, {}, instances=INSTANCES
    )
    check.populate_servers_cache({'testproj': {"id": "6f70656e737461636b20342065766572", "name": "testproj"}}, [])
    servers = check.servers_cache['servers']
    assert 'server-1' in servers
    assert 'other-1' not in servers
    assert 'other-2' not in servers


OS_AGGREGATES_RESPONSE = [
    {
        "availability_zone": "london",
        "created_at": "2016-12-27T23:47:32.911515",
        "deleted": False,
        "deleted_at": None,
        "hosts": ["compute"],
        "id": 1,
        "metadata": {"availability_zone": "london"},
        "name": "name",
        "updated_at": None,
        "uuid": "6ba28ba7-f29b-45cc-a30b-6e3a40c2fb14",
    }
]


def get_server_diagnostics_pre_2_48_response(server_id):
    return {
        "cpu0_time": 17300000000,
        "memory": 524288,
        "vda_errors": -1,
        "vda_read": 262144,
        "vda_read_req": 112,
        "vda_write": 5778432,
        "vda_write_req": 488,
        "vnet1_rx": 2070139,
        "vnet1_rx_drop": 0,
        "vnet1_rx_errors": 0,
        "vnet1_rx_packets": 26701,
        "vnet1_tx": 140208,
        "vnet1_tx_drop": 0,
        "vnet1_tx_errors": 0,
        "vnet1_tx_packets": 662,
        "vnet2_rx": 2070139,
        "vnet2_rx_drop": 0,
        "vnet2_rx_errors": 0,
        "vnet2_rx_packets": 26701,
        "vnet2_tx": 140208,
        "vnet2_tx_drop": 0,
        "vnet2_tx_errors": 0,
        "vnet2_tx_packets": 662,
    }


@mock.patch(
    'datadog_checks.openstack_controller.OpenStackControllerCheck.get_server_diagnostics',
    side_effect=get_server_diagnostics_pre_2_48_response,
)
@mock.patch(
    'datadog_checks.openstack_controller.OpenStackControllerCheck.get_os_aggregates',
    return_value=OS_AGGREGATES_RESPONSE,
)
def test_collect_server_metrics_pre_2_48(server_diagnostics, os_aggregates, aggregator):
    check = OpenStackControllerCheck(
        "test", {'ssl_verify': False, 'paginated_server_limit': 1}, {}, instances=INSTANCES
    )

    check.collect_server_diagnostic_metrics({})

    aggregator.assert_metric(
        'openstack.nova.server.vda_read_req',
        value=112.0,
        tags=['nova_managed_server', 'availability_zone:NA'],
        hostname='',
    )
    aggregator.assert_metric(
        'openstack.nova.server.vda_read',
        value=262144.0,
        tags=['nova_managed_server', 'availability_zone:NA'],
        hostname='',
    )
    aggregator.assert_metric(
        'openstack.nova.server.memory',
        value=524288.0,
        tags=['nova_managed_server', 'availability_zone:NA'],
        hostname='',
    )
    aggregator.assert_metric(
        'openstack.nova.server.cpu0_time',
        value=17300000000.0,
        tags=['nova_managed_server', 'availability_zone:NA'],
        hostname='',
    )
    aggregator.assert_metric(
        'openstack.nova.server.vda_errors',
        value=-1.0,
        tags=['nova_managed_server', 'availability_zone:NA'],
        hostname='',
    )
    aggregator.assert_metric(
        'openstack.nova.server.vda_write_req',
        value=488.0,
        tags=['nova_managed_server', 'availability_zone:NA'],
        hostname='',
    )
    aggregator.assert_metric(
        'openstack.nova.server.vda_write',
        value=5778432.0,
        tags=['nova_managed_server', 'availability_zone:NA'],
        hostname='',
    )
    aggregator.assert_metric(
        'openstack.nova.server.tx_drop',
        value=0.0,
        tags=['nova_managed_server', 'availability_zone:NA', 'interface:vnet1'],
        hostname='',
    )
    aggregator.assert_metric(
        'openstack.nova.server.tx',
        value=140208.0,
        tags=['nova_managed_server', 'availability_zone:NA', 'interface:vnet1'],
        hostname='',
    )
    aggregator.assert_metric(
        'openstack.nova.server.rx_drop',
        value=0.0,
        tags=['nova_managed_server', 'availability_zone:NA', 'interface:vnet1'],
        hostname='',
    )
    aggregator.assert_metric(
        'openstack.nova.server.rx',
        value=2070139.0,
        tags=['nova_managed_server', 'availability_zone:NA', 'interface:vnet1'],
        hostname='',
    )
    aggregator.assert_metric(
        'openstack.nova.server.tx_packets',
        value=662.0,
        tags=['nova_managed_server', 'availability_zone:NA', 'interface:vnet1'],
        hostname='',
    )
    aggregator.assert_metric(
        'openstack.nova.server.tx_errors',
        value=0.0,
        tags=['nova_managed_server', 'availability_zone:NA', 'interface:vnet1'],
        hostname='',
    )
    aggregator.assert_metric(
        'openstack.nova.server.rx_packets',
        value=26701.0,
        tags=['nova_managed_server', 'availability_zone:NA', 'interface:vnet1'],
        hostname='',
    )
    aggregator.assert_metric(
        'openstack.nova.server.rx_errors',
        value=0.0,
        tags=['nova_managed_server', 'availability_zone:NA', 'interface:vnet1'],
        hostname='',
    )
    aggregator.assert_metric(
        'openstack.nova.server.tx_drop',
        value=0.0,
        tags=['nova_managed_server', 'availability_zone:NA', 'interface:vnet2'],
        hostname='',
    )
    aggregator.assert_metric(
        'openstack.nova.server.tx',
        value=140208.0,
        tags=['nova_managed_server', 'availability_zone:NA', 'interface:vnet2'],
        hostname='',
    )
    aggregator.assert_metric(
        'openstack.nova.server.rx_drop',
        value=0.0,
        tags=['nova_managed_server', 'availability_zone:NA', 'interface:vnet2'],
        hostname='',
    )
    aggregator.assert_metric(
        'openstack.nova.server.rx',
        value=2070139.0,
        tags=['nova_managed_server', 'availability_zone:NA', 'interface:vnet2'],
        hostname='',
    )
    aggregator.assert_metric(
        'openstack.nova.server.tx_packets',
        value=662.0,
        tags=['nova_managed_server', 'availability_zone:NA', 'interface:vnet2'],
        hostname='',
    )
    aggregator.assert_metric(
        'openstack.nova.server.tx_errors',
        value=0.0,
        tags=['nova_managed_server', 'availability_zone:NA', 'interface:vnet2'],
        hostname='',
    )
    aggregator.assert_metric(
        'openstack.nova.server.rx_packets',
        value=26701.0,
        tags=['nova_managed_server', 'availability_zone:NA', 'interface:vnet2'],
        hostname='',
    )
    aggregator.assert_metric(
        'openstack.nova.server.rx_errors',
        value=0.0,
        tags=['nova_managed_server', 'availability_zone:NA', 'interface:vnet2'],
        hostname='',
    )

    aggregator.assert_all_metrics_covered()


def test_get_keystone_url_from_openstack_config():
    instances = copy.deepcopy(INSTANCES)
    instances[0]['keystone_server_url'] = None
    instances[0]['openstack_config_file_path'] = os.path.abspath('./tests/fixtures/openstack_config.yaml')
    instances[0]['openstack_cloud_name'] = 'test_cloud'
    check = OpenStackControllerCheck(
        "test", {'ssl_verify': False, 'paginated_server_limit': 1}, {}, instances=instances
    )
    keystone_server_url = check._get_keystone_server_url(instances[0])
    assert keystone_server_url == 'http://xxx.xxx.xxx.xxx:5000/v2.0/'


def test_get_keystone_url_from_datadog_config():
    check = OpenStackControllerCheck(
        "test", {'ssl_verify': False, 'paginated_server_limit': 1}, {}, instances=INSTANCES
    )
    keystone_server_url = check._get_keystone_server_url(INSTANCES[0])
    assert keystone_server_url == 'http://10.0.2.15:5000'
