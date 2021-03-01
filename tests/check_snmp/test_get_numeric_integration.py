import mock

from nagios_plugin_utils import STATUS_UNKNOWN

from managed_nagios_plugin._compat import text_type

from tests.fakes import FakeLogger
import tests.links.check_snmp_numeric as check_snmp_numeric


@mock.patch('tests.links.check_snmp_numeric.'
            'logging_utils')
@mock.patch('tests.links.check_snmp_numeric.'
            'check_thresholds_and_exit')
@mock.patch('tests.links.check_snmp_numeric.'
            'store_value_and_calculate_rate')
@mock.patch('tests.links.check_snmp_numeric.'
            'get_instance_rate_storage_path')
@mock.patch('tests.links.check_snmp_numeric.'
            'get_single_float_from_result')
@mock.patch('tests.links.check_snmp_numeric.'
            'get_perfdata')
@mock.patch('tests.links.check_snmp_numeric.'
            'run_check')
@mock.patch('tests.links.check_snmp_numeric.'
            'validate_and_structure_thresholds')
@mock.patch('tests.links.check_snmp_numeric.sys.exit')
@mock.patch('tests.links.check_snmp_numeric.print')
def test_rate(mock_print, exit, thresholds, run_check, get_perfdata,
              get_single_float, get_instance_rate_path, calculate_rate,
              check_thresholds_and_exit, logging_utils):
    logger = FakeLogger()
    logging_utils.Logger.return_value = logger

    run_check_result = 'checkresult'
    run_check.return_value = run_check_result

    returned_thresholds = 'thresholds'
    thresholds.return_value = returned_thresholds

    instance_rate_storage_path = 'instancestoragepath'
    get_instance_rate_path.return_value = instance_rate_storage_path

    perfdata = 'theperfdata'
    get_perfdata.return_value = perfdata

    float_value = 1.234
    get_single_float.return_value = float_value

    rate_result = 0.123
    calculate_rate.return_value = rate_result

    hostname = 'therealhost'
    oid = 'somefakeoid'
    target_type = 'thetypeoftarget'

    check_snmp_numeric.main(
        ['--rate', '--hostname', hostname, '--oid', oid,
         '--target-type', target_type]
    )

    run_check.assert_called_once_with(
        check_snmp_numeric.__file__, target_type, hostname, oid, logger,
    )

    get_perfdata.assert_called_once_with(run_check_result)

    get_single_float.assert_called_once_with(run_check_result)

    get_instance_rate_path.assert_called_once_with(hostname, oid)

    calculate_rate.assert_called_once_with(
        logger, float_value, instance_rate_storage_path
    )

    check_thresholds_and_exit.assert_called_once_with(
        rate_result, returned_thresholds, perfdata, True,
    )


@mock.patch('tests.links.check_snmp_numeric.'
            'logging_utils')
@mock.patch('tests.links.check_snmp_numeric.'
            'check_thresholds_and_exit')
@mock.patch('tests.links.check_snmp_numeric.'
            'store_value_and_calculate_rate')
@mock.patch('tests.links.check_snmp_numeric.'
            'get_instance_rate_storage_path')
@mock.patch('tests.links.check_snmp_numeric.'
            'get_single_float_from_result')
@mock.patch('tests.links.check_snmp_numeric.'
            'get_perfdata')
@mock.patch('tests.links.check_snmp_numeric.'
            'run_check')
@mock.patch('tests.links.check_snmp_numeric.'
            'validate_and_structure_thresholds')
@mock.patch('tests.links.check_snmp_numeric.sys.exit')
@mock.patch('tests.links.check_snmp_numeric.print')
def test_not_rate(mock_print, exit, thresholds, run_check, get_perfdata,
                  get_single_float, get_instance_rate_path, calculate_rate,
                  check_thresholds_and_exit, logging_utils):
    logger = FakeLogger()
    logging_utils.Logger.return_value = logger

    run_check_result = 'checkresult'
    run_check.return_value = run_check_result

    returned_thresholds = 'thresholds'
    thresholds.return_value = returned_thresholds

    perfdata = 'theperfdata'
    get_perfdata.return_value = perfdata

    float_value = 1.234
    get_single_float.return_value = float_value

    hostname = 'therealhost'
    oid = 'somefakeoid'
    target_type = 'thetypeoftarget'

    check_snmp_numeric.main(
        ['--hostname', hostname, '--oid', oid,
         '--target-type', target_type]
    )

    run_check.assert_called_once_with(
        check_snmp_numeric.__file__, target_type, hostname, oid, logger,
    )

    get_perfdata.assert_called_once_with(run_check_result)

    get_single_float.assert_called_once_with(run_check_result)

    check_thresholds_and_exit.assert_called_once_with(
        float_value, returned_thresholds, perfdata, False,
    )


@mock.patch('tests.links.check_snmp_numeric.'
            'logging_utils')
@mock.patch('tests.links.check_snmp_numeric.'
            'check_thresholds_and_exit')
@mock.patch('tests.links.check_snmp_numeric.'
            'store_value_and_calculate_rate')
@mock.patch('tests.links.check_snmp_numeric.'
            'get_instance_rate_storage_path')
@mock.patch('tests.links.check_snmp_numeric.'
            'get_single_float_from_result')
@mock.patch('tests.links.check_snmp_numeric.'
            'get_perfdata')
@mock.patch('tests.links.check_snmp_numeric.'
            'run_check')
@mock.patch('tests.links.check_snmp_numeric.'
            'validate_and_structure_thresholds')
@mock.patch('tests.links.check_snmp_numeric.sys.exit')
@mock.patch('tests.links.check_snmp_numeric.print')
def test_no_thresholds(mock_print, exit, thresholds, run_check, get_perfdata,
                       get_single_float, get_instance_rate_path,
                       calculate_rate, check_thresholds_and_exit,
                       logging_utils):
    logger = FakeLogger()
    logging_utils.Logger.return_value = logger

    returned_thresholds = 'thresholds'
    thresholds.return_value = returned_thresholds

    perfdata = 'theperfdata'
    get_perfdata.return_value = perfdata

    float_value = 1.234
    get_single_float.return_value = float_value

    hostname = 'therealhost'
    oid = 'somefakeoid'
    target_type = 'thetypeoftarget'

    check_snmp_numeric.main(
        ['--hostname', hostname, '--oid', oid,
         '--target-type', target_type]
    )

    check_thresholds_and_exit.assert_called_once_with(
        float_value, returned_thresholds, perfdata, False,
    )

    thresholds.assert_called_once_with("", "", "", "", logger)


@mock.patch('tests.links.check_snmp_numeric.'
            'logging_utils')
@mock.patch('tests.links.check_snmp_numeric.'
            'check_thresholds_and_exit')
@mock.patch('tests.links.check_snmp_numeric.'
            'store_value_and_calculate_rate')
@mock.patch('tests.links.check_snmp_numeric.'
            'get_instance_rate_storage_path')
@mock.patch('tests.links.check_snmp_numeric.'
            'get_single_float_from_result')
@mock.patch('tests.links.check_snmp_numeric.'
            'get_perfdata')
@mock.patch('tests.links.check_snmp_numeric.'
            'run_check')
@mock.patch('tests.links.check_snmp_numeric.'
            'validate_and_structure_thresholds')
@mock.patch('tests.links.check_snmp_numeric.sys.exit')
@mock.patch('tests.links.check_snmp_numeric.print')
def test_thresholds(mock_print, exit, thresholds, run_check, get_perfdata,
                    get_single_float, get_instance_rate_path,
                    calculate_rate, check_thresholds_and_exit,
                    logging_utils):
    logger = FakeLogger()
    logging_utils.Logger.return_value = logger

    returned_thresholds = 'thresholds'
    thresholds.return_value = returned_thresholds

    perfdata = 'theperfdata'
    get_perfdata.return_value = perfdata

    float_value = 1.234
    get_single_float.return_value = float_value

    low_warn = 2
    low_crit = 1
    high_warn = 3
    high_crit = 4

    hostname = 'therealhost'
    oid = 'somefakeoid'
    target_type = 'thetypeoftarget'

    check_snmp_numeric.main(
        ['--hostname', hostname, '--oid', oid,
         '--target-type', target_type,
         '--low-warning', text_type(low_warn),
         '--low-critical', text_type(low_crit),
         '--high-warning', text_type(high_warn),
         '--high-critical', text_type(high_crit)]
    )

    check_thresholds_and_exit.assert_called_once_with(
        float_value, returned_thresholds, perfdata, False,
    )

    thresholds.assert_called_once_with(
        low_warn, low_crit, high_warn, high_crit, logger,
    )


@mock.patch('tests.links.check_snmp_numeric.'
            'logging_utils')
@mock.patch('tests.links.check_snmp_numeric.'
            'check_thresholds_and_exit')
@mock.patch('tests.links.check_snmp_numeric.'
            'store_value_and_calculate_rate')
@mock.patch('tests.links.check_snmp_numeric.'
            'get_instance_rate_storage_path')
@mock.patch('tests.links.check_snmp_numeric.'
            'get_single_float_from_result')
@mock.patch('tests.links.check_snmp_numeric.'
            'get_perfdata')
@mock.patch('tests.links.check_snmp_numeric.'
            'run_check')
@mock.patch('tests.links.check_snmp_numeric.'
            'validate_and_structure_thresholds')
@mock.patch('tests.links.check_snmp_numeric.sys.exit')
@mock.patch('tests.links.check_snmp_numeric.print')
def test_multi_oid(mock_print, exit, thresholds, run_check, get_perfdata,
                   get_single_float, get_instance_rate_path,
                   calculate_rate, check_thresholds_and_exit,
                   logging_utils):
    logger = FakeLogger()

    hostname = 'therealhost'
    oid = 'somefakeoid,otheroid'
    target_type = 'thetypeoftarget'

    check_snmp_numeric.main(
        ['--hostname', hostname, '--oid', oid,
         '--target-type', target_type]
    )

    logger.string_appears_in('error', 'single oid')
    mock_print_arg = mock_print.call_args_list[0][0][0].lower()
    assert 'single oid' in mock_print_arg

    exit.assert_called_once_with(STATUS_UNKNOWN)
