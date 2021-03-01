import mock

from managed_nagios_plugin._compat import text_type
from nagios_plugin_utils import STATUS_UNKNOWN

from tests.fakes import FakeLogger
import tests.links.check_snmp_aggregate as check_snmp_aggregate


@mock.patch('tests.links.check_snmp_aggregate.'
            'logging_utils')
@mock.patch('tests.links.check_snmp_aggregate.'
            'check_thresholds_and_exit')
@mock.patch('tests.links.check_snmp_aggregate.'
            'generate_check_identifier')
@mock.patch('tests.links.check_snmp_aggregate.'
            'generate_perfdata')
@mock.patch('tests.links.check_snmp_aggregate.'
            'get_host_address')
@mock.patch('tests.links.check_snmp_aggregate.'
            'get_instance_addresses')
@mock.patch('tests.links.check_snmp_aggregate.'
            'calculate_mean')
@mock.patch('tests.links.check_snmp_aggregate.'
            'store_value_and_calculate_rate')
@mock.patch('tests.links.check_snmp_aggregate.'
            'get_node_rate_storage_path')
@mock.patch('tests.links.check_snmp_aggregate.'
            'get_floats_from_result')
@mock.patch('tests.links.check_snmp_aggregate.'
            'run_check')
@mock.patch('tests.links.check_snmp_aggregate.'
            'validate_and_structure_thresholds')
@mock.patch('tests.links.check_snmp_aggregate.sys.exit')
@mock.patch('tests.links.check_snmp_aggregate.print')
def test_rate(mock_print, exit, thresholds, run_check,
              get_multi_float, get_node_rate_path, calculate_rate,
              calculate_mean, get_instance_addresses, get_host_address,
              generate_perfdata, generate_check_id,
              check_thresholds_and_exit, logging_utils):
    logger = FakeLogger()
    logging_utils.Logger.return_value = logger

    run_check_results = 'checkresult', 'checkresult2'
    run_check.side_effect = run_check_results

    returned_thresholds = 'thresholds'
    thresholds.return_value = returned_thresholds

    instance_rate_storage_path = 'instancestoragepath'
    get_node_rate_path.return_value = instance_rate_storage_path

    float_values = 1.5, 2.0
    get_multi_float.return_value = float_values

    mean = 1.75
    calculate_mean.return_value = mean
    old_calculate_mean = calculate_mean.APPROACHES['arithmetic_mean']
    check_snmp_aggregate.APPROACHES['arithmetic_mean'] = calculate_mean

    rate_result = 1.75
    calculate_rate.return_value = rate_result

    instance_addresses = '192.0.2.5', '192.0.2.6'
    get_instance_addresses.return_value = instance_addresses

    host_addresses = ['addr1', 'addr2']
    get_host_address.side_effect = host_addresses

    perfdata = 'performance_data'
    generate_perfdata.return_value = perfdata

    check_identifier = 'check_id'
    generate_check_id.return_value = check_identifier

    node = 'therealhost'
    oids = 'somefakeoid,other'
    target_type = 'thetypeoftarget'

    check_snmp_aggregate.main(
        ['--rate',
         '--node', node, '--oids', oids,
         '--approach', 'arithmetic_mean',
         '--unknown', 'ignore',
         '--target-type', target_type]
    )

    for instance_address in instance_addresses:
        expected = mock.call(instance_address, logger)
        assert expected in get_host_address.call_args_list

    for host_address in host_addresses:
        expected = mock.call(
            check_snmp_aggregate.__file__,
            target_type,
            host_address,
            oids,
            logger,
            ignore_unknown=True,
        )
        assert expected in run_check.call_args_list

    for result in run_check_results:
        expected = mock.call(result)
        assert expected in get_multi_float.call_args_list

    # Two repetitions of float values because of two nodes
    calculate_mean.assert_called_once_with(list(float_values + float_values))

    get_node_rate_path.assert_called_once_with(node, check_identifier)

    calculate_rate.assert_called_once_with(
        logger, mean, instance_rate_storage_path
    )

    check_thresholds_and_exit.assert_called_once_with(
        rate_result, returned_thresholds, perfdata, True,
    )

    check_snmp_aggregate.APPROACHES['arithmetic_mean'] = old_calculate_mean


@mock.patch('tests.links.check_snmp_aggregate.'
            'logging_utils')
@mock.patch('tests.links.check_snmp_aggregate.'
            'check_thresholds_and_exit')
@mock.patch('tests.links.check_snmp_aggregate.'
            'generate_check_identifier')
@mock.patch('tests.links.check_snmp_aggregate.'
            'generate_perfdata')
@mock.patch('tests.links.check_snmp_aggregate.'
            'get_host_address')
@mock.patch('tests.links.check_snmp_aggregate.'
            'get_instance_addresses')
@mock.patch('tests.links.check_snmp_aggregate.'
            'calculate_mean')
@mock.patch('tests.links.check_snmp_aggregate.'
            'get_floats_from_result')
@mock.patch('tests.links.check_snmp_aggregate.'
            'run_check')
@mock.patch('tests.links.check_snmp_aggregate.'
            'validate_and_structure_thresholds')
@mock.patch('tests.links.check_snmp_aggregate.sys.exit')
@mock.patch('tests.links.check_snmp_aggregate.print')
def test_non_rate(mock_print, exit, thresholds, run_check,
                  get_multi_float,
                  calculate_mean, get_instance_addresses, get_host_address,
                  generate_perfdata, generate_check_id,
                  check_thresholds_and_exit, logging_utils):
    logger = FakeLogger()
    logging_utils.Logger.return_value = logger

    run_check_results = 'checkresult', 'checkresult2'
    run_check.side_effect = run_check_results

    returned_thresholds = 'thresholds'
    thresholds.return_value = returned_thresholds

    float_values = 1.5, 2.0
    get_multi_float.return_value = float_values

    mean = 1.75
    calculate_mean.return_value = mean
    old_calculate_mean = calculate_mean.APPROACHES['arithmetic_mean']
    check_snmp_aggregate.APPROACHES['arithmetic_mean'] = calculate_mean

    instance_addresses = '192.0.2.5', '192.0.2.6'
    get_instance_addresses.return_value = instance_addresses

    host_addresses = ['addr1', 'addr2']
    get_host_address.side_effect = host_addresses

    perfdata = 'performance_data'
    generate_perfdata.return_value = perfdata

    check_identifier = 'check_id'
    generate_check_id.return_value = check_identifier

    node = 'therealhost'
    oids = 'somefakeoid,other'
    target_type = 'thetypeoftarget'

    check_snmp_aggregate.main(
        ['--node', node, '--oids', oids,
         '--approach', 'arithmetic_mean',
         '--unknown', 'ignore',
         '--target-type', target_type]
    )

    for instance_address in instance_addresses:
        expected = mock.call(instance_address, logger)
        assert expected in get_host_address.call_args_list

    for host_address in host_addresses:
        expected = mock.call(
            check_snmp_aggregate.__file__,
            target_type,
            host_address,
            oids,
            logger,
            ignore_unknown=True,
        )
        assert expected in run_check.call_args_list

    for result in run_check_results:
        expected = mock.call(result)
        assert expected in get_multi_float.call_args_list

    # Two repetitions of float values because of two nodes
    calculate_mean.assert_called_once_with(list(float_values + float_values))

    check_thresholds_and_exit.assert_called_once_with(
        mean, returned_thresholds, perfdata, False,
    )

    check_snmp_aggregate.APPROACHES['arithmetic_mean'] = old_calculate_mean


@mock.patch('tests.links.check_snmp_aggregate.'
            'logging_utils')
@mock.patch('tests.links.check_snmp_aggregate.'
            'check_thresholds_and_exit')
@mock.patch('tests.links.check_snmp_aggregate.'
            'generate_check_identifier')
@mock.patch('tests.links.check_snmp_aggregate.'
            'generate_perfdata')
@mock.patch('tests.links.check_snmp_aggregate.'
            'get_host_address')
@mock.patch('tests.links.check_snmp_aggregate.'
            'get_instance_addresses')
@mock.patch('tests.links.check_snmp_aggregate.'
            'calculate_mean')
@mock.patch('tests.links.check_snmp_aggregate.'
            'get_floats_from_result')
@mock.patch('tests.links.check_snmp_aggregate.'
            'run_check')
@mock.patch('tests.links.check_snmp_aggregate.'
            'validate_and_structure_thresholds')
@mock.patch('tests.links.check_snmp_aggregate.sys.exit')
@mock.patch('tests.links.check_snmp_aggregate.print')
def test_no_thresholds(mock_print, exit, thresholds, run_check,
                       get_multi_float,
                       calculate_mean, get_instance_addresses,
                       get_host_address, generate_perfdata, generate_check_id,
                       check_thresholds_and_exit, logging_utils):
    logger = FakeLogger()
    logging_utils.Logger.return_value = logger

    returned_thresholds = 'thresholds'
    thresholds.return_value = returned_thresholds

    float_values = 1.5, 2.0
    get_multi_float.return_value = float_values

    mean = 1.75
    calculate_mean.return_value = mean
    old_calculate_mean = calculate_mean.APPROACHES['arithmetic_mean']
    check_snmp_aggregate.APPROACHES['arithmetic_mean'] = calculate_mean

    instance_addresses = '192.0.2.5', '192.0.2.6'
    get_instance_addresses.return_value = instance_addresses

    perfdata = 'performance_data'
    generate_perfdata.return_value = perfdata

    node = 'therealhost'
    oids = 'somefakeoid,other'
    target_type = 'thetypeoftarget'

    check_snmp_aggregate.main(
        ['--node', node, '--oids', oids,
         '--approach', 'arithmetic_mean',
         '--unknown', 'ignore',
         '--target-type', target_type]
    )

    check_thresholds_and_exit.assert_called_once_with(
        mean, returned_thresholds, perfdata, False,
    )

    thresholds.assert_called_once_with("", "", "", "", logger)

    check_snmp_aggregate.APPROACHES['arithmetic_mean'] = old_calculate_mean


@mock.patch('tests.links.check_snmp_aggregate.'
            'logging_utils')
@mock.patch('tests.links.check_snmp_aggregate.'
            'check_thresholds_and_exit')
@mock.patch('tests.links.check_snmp_aggregate.'
            'generate_check_identifier')
@mock.patch('tests.links.check_snmp_aggregate.'
            'generate_perfdata')
@mock.patch('tests.links.check_snmp_aggregate.'
            'get_host_address')
@mock.patch('tests.links.check_snmp_aggregate.'
            'get_instance_addresses')
@mock.patch('tests.links.check_snmp_aggregate.'
            'calculate_mean')
@mock.patch('tests.links.check_snmp_aggregate.'
            'get_floats_from_result')
@mock.patch('tests.links.check_snmp_aggregate.'
            'run_check')
@mock.patch('tests.links.check_snmp_aggregate.'
            'validate_and_structure_thresholds')
@mock.patch('tests.links.check_snmp_aggregate.sys.exit')
@mock.patch('tests.links.check_snmp_aggregate.print')
def test_thresholds(mock_print, exit, thresholds, run_check,
                    get_multi_float,
                    calculate_mean, get_instance_addresses,
                    get_host_address, generate_perfdata, generate_check_id,
                    check_thresholds_and_exit, logging_utils):
    logger = FakeLogger()
    logging_utils.Logger.return_value = logger

    returned_thresholds = 'thresholds'
    thresholds.return_value = returned_thresholds

    float_values = 1.5, 2.0
    get_multi_float.return_value = float_values

    mean = 1.75
    calculate_mean.return_value = mean
    old_calculate_mean = calculate_mean.APPROACHES['arithmetic_mean']
    check_snmp_aggregate.APPROACHES['arithmetic_mean'] = calculate_mean

    instance_addresses = '192.0.2.5', '192.0.2.6'
    get_instance_addresses.return_value = instance_addresses

    perfdata = 'performance_data'
    generate_perfdata.return_value = perfdata

    low_warn = 2
    low_crit = 1
    high_warn = 3
    high_crit = 4

    node = 'therealhost'
    oids = 'somefakeoid,other'
    target_type = 'thetypeoftarget'

    check_snmp_aggregate.main(
        ['--node', node, '--oids', oids,
         '--approach', 'arithmetic_mean',
         '--unknown', 'ignore',
         '--target-type', target_type,
         '--low-warning', text_type(low_warn),
         '--low-critical', text_type(low_crit),
         '--high-warning', text_type(high_warn),
         '--high-critical', text_type(high_crit)]
    )

    check_thresholds_and_exit.assert_called_once_with(
        mean, returned_thresholds, perfdata, False,
    )

    thresholds.assert_called_once_with(
        low_warn, low_crit, high_warn, high_crit, logger,
    )

    check_snmp_aggregate.APPROACHES['arithmetic_mean'] = old_calculate_mean


def test_generate_perfdata():
    expected = ' check_id=value'
    check_id = 'check_id'
    value = 'value'

    result = check_snmp_aggregate.generate_perfdata(check_id, value)

    assert result == expected


def test_generate_check_id():
    expected = 'approach(oids)'
    approach = 'approach'
    oids = 'oids'

    result = check_snmp_aggregate.generate_check_identifier(approach, oids)

    assert result == expected


@mock.patch('tests.links.check_snmp_aggregate.'
            'logging_utils')
@mock.patch('tests.links.check_snmp_aggregate.'
            'check_thresholds_and_exit')
@mock.patch('tests.links.check_snmp_aggregate.'
            'generate_check_identifier')
@mock.patch('tests.links.check_snmp_aggregate.'
            'generate_perfdata')
@mock.patch('tests.links.check_snmp_aggregate.'
            'get_host_address')
@mock.patch('tests.links.check_snmp_aggregate.'
            'get_instance_addresses')
@mock.patch('tests.links.check_snmp_aggregate.'
            'calculate_mean')
@mock.patch('tests.links.check_snmp_aggregate.'
            'get_floats_from_result')
@mock.patch('tests.links.check_snmp_aggregate.'
            'run_check')
@mock.patch('tests.links.check_snmp_aggregate.'
            'validate_and_structure_thresholds')
@mock.patch('tests.links.check_snmp_aggregate.sys.exit')
@mock.patch('tests.links.check_snmp_aggregate.print')
def test_no_result(mock_print, exit, thresholds, run_check,
                   get_multi_float,
                   calculate_mean, get_instance_addresses, get_host_address,
                   generate_perfdata, generate_check_id,
                   check_thresholds_and_exit, logging_utils):
    logger = FakeLogger()
    logging_utils.Logger.return_value = logger

    run_check_results = None, None
    run_check.side_effect = run_check_results

    returned_thresholds = 'thresholds'
    thresholds.return_value = returned_thresholds

    float_values = 1.5, 2.0
    get_multi_float.return_value = float_values

    mean = 1.75
    calculate_mean.return_value = mean
    old_calculate_mean = calculate_mean.APPROACHES['arithmetic_mean']
    check_snmp_aggregate.APPROACHES['arithmetic_mean'] = calculate_mean

    instance_addresses = '192.0.2.5', '192.0.2.6'
    get_instance_addresses.return_value = instance_addresses

    host_addresses = ['addr1', 'addr2']
    get_host_address.side_effect = host_addresses

    perfdata = 'performance_data'
    generate_perfdata.return_value = perfdata

    check_identifier = 'check_id'
    generate_check_id.return_value = check_identifier

    node = 'therealhost'
    oids = 'somefakeoid,other'
    target_type = 'thetypeoftarget'

    check_snmp_aggregate.main(
        ['--node', node, '--oids', oids,
         '--approach', 'arithmetic_mean',
         '--unknown', 'ignore',
         '--target-type', target_type]
    )

    logger.string_appears_in('error', 'no values')
    mock_print_arg = mock_print.call_args_list[0][0][0].lower()
    assert 'no values' in mock_print_arg

    exit.assert_called_once_with(STATUS_UNKNOWN)

    check_snmp_aggregate.APPROACHES['arithmetic_mean'] = old_calculate_mean
