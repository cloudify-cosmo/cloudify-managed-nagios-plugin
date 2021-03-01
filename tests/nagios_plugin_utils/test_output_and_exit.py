import mock

from managed_nagios_plugin._compat import text_type

import nagios_plugin_utils


@mock.patch('nagios_plugin_utils.sys.exit')
@mock.patch('nagios_plugin_utils.print')
def test_output_and_exit_rate(mock_print, exit):
    value = 42
    perfdata = 'abc123'
    state = 'OK'
    level = 'somelevel'
    rate_check = True

    nagios_plugin_utils.output_and_exit(value, perfdata, state, level,
                                        rate_check)

    mock_print_arg = mock_print.call_args_list[0][0][0]
    result, result_perfdata = mock_print_arg.split('|')

    assert perfdata == result_perfdata
    assert text_type(value) in result
    assert state in result
    assert level in result
    assert result.startswith('SNMP RATE')

    exit.assert_called_once_with(nagios_plugin_utils.STATUS_DETAILS[state][0])


@mock.patch('nagios_plugin_utils.sys.exit')
@mock.patch('nagios_plugin_utils.print')
def test_output_and_exit_non_rate(mock_print, exit):
    value = 42
    perfdata = 'abc123'
    state = 'WARNING'
    level = 'somelevel'
    rate_check = False

    nagios_plugin_utils.output_and_exit(value, perfdata, state, level,
                                        rate_check)

    mock_print_arg = mock_print.call_args_list[0][0][0]
    result, result_perfdata = mock_print_arg.split('|')

    assert perfdata == result_perfdata
    assert text_type(value) in result
    assert state in result
    assert level in result
    assert result.startswith('SNMP ')
    assert not result.startswith('SNMP RATE')

    exit.assert_called_once_with(nagios_plugin_utils.STATUS_DETAILS[state][0])


@mock.patch('nagios_plugin_utils.sys.exit')
@mock.patch('nagios_plugin_utils.print')
def test_output_and_exit_bad_state(mock_print, exit):
    value = 42
    perfdata = 'abc123'
    state = 'what is this?'
    level = 'somelevel'
    rate_check = False

    nagios_plugin_utils.output_and_exit(value, perfdata, state, level,
                                        rate_check)

    mock_print_arg = mock_print.call_args_list[0][0][0]
    result, result_perfdata = mock_print_arg.split('|')

    assert perfdata == result_perfdata
    assert text_type(value) in result
    assert state in result
    assert level in result
    assert result.startswith('SNMP ')
    assert not result.startswith('SNMP RATE')

    exit.assert_called_once_with(nagios_plugin_utils.STATUS_UNKNOWN)
