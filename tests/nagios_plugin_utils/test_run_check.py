import hashlib
import subprocess

from managed_nagios_plugin._compat import text_type

import mock

import nagios_plugin_utils
from tests.fakes import FakeLogger

BASE_DIR_LIST = ['no.in', 'this.cfg', 'other.cfg']


@mock.patch('nagios_plugin_utils.get_types')
@mock.patch('nagios_plugin_utils.os')
@mock.patch('nagios_plugin_utils.check_output')
@mock.patch('nagios_plugin_utils.sys.exit')
@mock.patch('nagios_plugin_utils.print')
def test_run_check_missing_ini(mock_print, exit, mock_subproc, mock_os,
                               mock_get_types):
    logger = FakeLogger()
    script_path = 'something'
    target_type = 'thistargettype'
    hostname = 'thehost'
    oid = 'theoid'
    ignore_unknown = False

    mock_os.path.exists.return_value = False
    ini_names = ['yes', 'that']
    ini_files = [ini_name + '.ini' for ini_name in ini_names]
    mock_os.listdir.return_value = BASE_DIR_LIST + ini_files

    mock_get_types.return_value = ini_names

    nagios_plugin_utils.run_check(script_path, target_type, hostname,
                                  oid, logger, ignore_unknown)

    mock_print_arg = mock_print.call_args_list[0][0][0].lower()
    assert 'target type' in mock_print_arg
    assert 'valid types' in mock_print_arg
    logger.string_appears_in('error', ('target type', 'valid types'))
    for ini_name in ini_names:
        assert ini_name in mock_print_arg
        logger.string_appears_in('error', ini_name)

    exit.assert_called_once_with(nagios_plugin_utils.STATUS_UNKNOWN)


@mock.patch('nagios_plugin_utils.get_types')
@mock.patch('nagios_plugin_utils.os')
@mock.patch('nagios_plugin_utils.check_output')
@mock.patch('nagios_plugin_utils.sys.exit')
@mock.patch('nagios_plugin_utils.print')
def test_run_check_no_inis(mock_print, exit, mock_subproc, mock_os,
                           mock_get_types):
    logger = FakeLogger()
    script_path = 'something'
    target_type = 'thistargettype'
    hostname = 'thehost'
    oid = 'theoid'
    ignore_unknown = False

    mock_os.path.exists.return_value = False
    mock_os.listdir.return_value = BASE_DIR_LIST

    mock_get_types.return_value = []

    nagios_plugin_utils.run_check(script_path, target_type, hostname,
                                  oid, logger, ignore_unknown)

    mock_print_arg = mock_print.call_args_list[0][0][0].lower()
    assert 'target type' in mock_print_arg
    assert 'valid types' in mock_print_arg
    assert 'none' in mock_print_arg
    logger.string_appears_in('error', ('target type', 'valid types', 'none'))

    exit.assert_called_once_with(nagios_plugin_utils.STATUS_UNKNOWN)


@mock.patch('nagios_plugin_utils.get_types')
@mock.patch('nagios_plugin_utils.os')
@mock.patch('nagios_plugin_utils.check_output')
@mock.patch('nagios_plugin_utils.sys.exit')
@mock.patch('nagios_plugin_utils.print')
def test_run_check_missing_script(mock_print, exit, mock_subproc, mock_os,
                                  mock_get_types):
    logger = FakeLogger()
    script_path = 'something'
    target_type = 'thistargettype'
    hostname = 'thehost'
    oid = 'theoid'
    ignore_unknown = False

    mock_os.path.exists.return_value = True

    mock_os.path.isfile.return_value = False

    nagios_plugin_utils.run_check(script_path, target_type, hostname,
                                  oid, logger, ignore_unknown)

    exist_check = mock_os.path.exists.call_args_list[0][0][0]
    assert exist_check.endswith(
        hashlib.md5(target_type).hexdigest() + '.ini'
    )

    mock_print_arg = mock_print.call_args_list[0][0][0].lower()
    assert 'check_snmp' in mock_print_arg
    assert 'not found' in mock_print_arg
    logger.string_appears_in('error', ('check_snmp', 'not found'))

    exit.assert_called_once_with(nagios_plugin_utils.STATUS_UNKNOWN)


@mock.patch('nagios_plugin_utils.get_types')
@mock.patch('nagios_plugin_utils.os')
@mock.patch('nagios_plugin_utils.check_output')
@mock.patch('nagios_plugin_utils.sys.exit')
@mock.patch('nagios_plugin_utils.print')
def test_run_check_bad_output(mock_print, exit, mock_subproc, mock_os,
                              mock_get_types):
    logger = FakeLogger()
    script_path = 'something'
    target_type = 'thistargettype'
    hostname = 'thehost'
    oid = 'theoid'
    ignore_unknown = False

    mock_os.path.exists.return_value = True

    mock_os.path.isfile.return_value = True

    exit_status = 42
    exit_output = 'badexitoutput'
    error = subprocess.CalledProcessError(
        exit_status,
        'notarealcommand',
        exit_output,
    )
    mock_subproc.side_effect = error

    nagios_plugin_utils.run_check(script_path, target_type, hostname,
                                  oid, logger, ignore_unknown)

    mock_print_arg = mock_print.call_args_list[0][0][0].lower()
    assert exit_output == mock_print_arg
    logger.string_appears_in('error',
                             ('unknown or error',
                              'status', text_type(exit_status),
                              'output', exit_output))

    exit.assert_called_once_with(exit_status)


@mock.patch('nagios_plugin_utils.get_types')
@mock.patch('nagios_plugin_utils.os')
@mock.patch('nagios_plugin_utils.check_output')
@mock.patch('nagios_plugin_utils.sys.exit')
@mock.patch('nagios_plugin_utils.print')
def test_run_check_ignore_unknown(mock_print, exit, mock_subproc, mock_os,
                                  mock_get_types):
    logger = FakeLogger()
    script_path = 'something'
    target_type = 'thistargettype'
    hostname = 'thehost'
    oid = 'theoid'
    ignore_unknown = True

    mock_os.path.exists.return_value = True

    mock_os.path.isfile.return_value = True

    exit_status = 3
    exit_output = 'badexitoutput'
    error = subprocess.CalledProcessError(
        exit_status,
        'notarealcommand',
        exit_output,
    )
    mock_subproc.side_effect = error

    result = nagios_plugin_utils.run_check(script_path, target_type, hostname,
                                           oid, logger, ignore_unknown)

    logger.string_appears_in('warn',
                             ('unknown state', 'ignoring'))

    assert result is None

    assert mock_print.call_count == 0
    assert exit.call_count == 0


@mock.patch('nagios_plugin_utils.get_types')
@mock.patch('nagios_plugin_utils.os')
@mock.patch('nagios_plugin_utils.check_output')
@mock.patch('nagios_plugin_utils.sys.exit')
@mock.patch('nagios_plugin_utils.print')
def test_run_check_ignore_not_unknown(mock_print, exit, mock_subproc,
                                      mock_os, mock_get_types):
    logger = FakeLogger()
    script_path = 'something'
    target_type = 'thistargettype'
    hostname = 'thehost'
    oid = 'theoid'
    ignore_unknown = True

    mock_os.path.exists.return_value = True

    mock_os.path.isfile.return_value = True

    exit_status = 42
    exit_output = 'badexitoutput'
    error = subprocess.CalledProcessError(
        exit_status,
        'notarealcommand',
        exit_output,
    )
    mock_subproc.side_effect = error

    nagios_plugin_utils.run_check(script_path, target_type, hostname,
                                  oid, logger, ignore_unknown)

    mock_print_arg = mock_print.call_args_list[0][0][0].lower()
    assert exit_output == mock_print_arg
    logger.string_appears_in('error',
                             ('unknown or error',
                              'status', text_type(exit_status),
                              'output', exit_output))

    exit.assert_called_once_with(exit_status)


@mock.patch('nagios_plugin_utils.get_types')
@mock.patch('nagios_plugin_utils.os')
@mock.patch('nagios_plugin_utils.check_output')
@mock.patch('nagios_plugin_utils.sys.exit')
@mock.patch('nagios_plugin_utils.print')
def test_run_check_success(mock_print, exit, mock_subproc, mock_os,
                           mock_get_types):
    logger = FakeLogger()
    script_path = 'something'
    target_type = 'thistargettype'
    hostname = 'thehost'
    oid = 'theoid'
    ignore_unknown = False
    expected_result = 'thegoodreturnvalue'

    mock_os.path.exists.return_value = True

    mock_os.path.isfile.return_value = True

    mock_subproc.return_value = expected_result

    result = nagios_plugin_utils.run_check(script_path, target_type, hostname,
                                           oid, logger, ignore_unknown)

    assert result == expected_result

    assert mock_print.call_count == 0
    assert exit.call_count == 0
