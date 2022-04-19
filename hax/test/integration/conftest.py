import logging

import pytest
from hax.log import setup_logging
from hax.util import ConsulUtil


@pytest.fixture
def consul_util(mocker):
    consul = ConsulUtil()
    exc = RuntimeError('Not allowed')
    mock = mocker.patch.object
    mock(consul.kv, 'kv_get', side_effect=exc)
    mock(consul.kv, 'kv_put', side_effect=exc)
    mock(consul.kv, 'kv_put_in_transaction', side_effect=exc)
    mock(consul.kv, 'kv_delete_in_transaction', side_effect=exc)
    mock(consul.catalog, 'get_services', side_effect=exc)
    mock(consul.catalog, 'get_service_names', side_effect=exc)
    mock(consul, 'get_local_nodename', return_value='localhost')
    mock(consul, 'get_hax_hostname', return_value='localhost')
    mock(consul, 'get_hax_ip_address', return_value='192.168.0.28')
    return consul


@pytest.fixture(autouse=True)
def logging_support():
    setup_logging()
    yield ''
    logging.shutdown()
