#! /usr/bin/env python

import argparse
import hashlib
import json
import os
import re
from subprocess import check_output, CalledProcessError
import sys
import time

from constants import RATE_NODE_PATH, RATE_INSTANCE_PATH
from nagios_utils import get_types
from utils import run


STATUS_OK = 0
STATUS_WARNING = 1
STATUS_CRITICAL = 2
STATUS_UNKNOWN = 3
STATUS_DETAILS = {
    'OK': (STATUS_OK, ''),
    'WARNING': (STATUS_WARNING, '*'),
    'CRITICAL': (STATUS_CRITICAL, '*'),
    'UNKNOWN': (STATUS_UNKNOWN, '?'),
}
TARGET_TYPE_BASE_PATH = '/etc/nagios/objects/target_types'
RESULT_REGEX_BASE = '^SNMP (?:RATE )?OK - "?({val_string})"?.*'


def output_and_exit(value, perfdata, state, level, rate_check, group=False):
    exit_status, value_delimiters = STATUS_DETAILS.get(
        state,
        STATUS_DETAILS['UNKNOWN'],
    )
    if level:
        state = level + ' ' + state
    if group:
        prefix = 'GROUP'
    else:
        prefix = 'SNMP'
    if rate_check:
        prefix += ' RATE'
    print('{prefix} {state} - {delim}{value}{delim} |{perfdata}'.format(
        prefix=prefix,
        state=state,
        value=value,
        delim=value_delimiters,
        perfdata=perfdata,
    ))
    sys.exit(exit_status)


def float_or_empty(value):
    # Allow supplied value to be float or an empty string (not supplied)
    if value == "":
        return value
    else:
        return float(value)


def get_argument_parser(description, group=False, allow_rate=True):
    parser = argparse.ArgumentParser(
        description=description,
    )

    if group:
        parser.add_argument(
            '--group-type',
            help=(
                "Group type to obtain parameters from."
            ),
            required=True,
        )
    else:
        parser.add_argument(
            '--target-type',
            help=(
                "Target type to obtain parameters from."
            ),
            required=True,
        )
    parser.add_argument(
        '--low-warning',
        help=(
            "Value below which to enter a warning state."
        ),
        default="",
        type=float_or_empty,
    )
    parser.add_argument(
        '--low-critical',
        help=(
            "Value below which to enter a critical state."
        ),
        default="",
        type=float_or_empty,
    )
    parser.add_argument(
        '--high-warning',
        help=(
            "Value above which to enter a warning state."
        ),
        default="",
        type=float_or_empty,
    )
    parser.add_argument(
        '--high-critical',
        help=(
            "Value above which to enter a critical state."
        ),
        default="",
        type=float_or_empty,
    )
    if allow_rate:
        parser.add_argument(
            '--rate',
            help=(
                "Set if the OID(s) being checked are counters which should "
                "be converted to a rate (change since last check)."
            ),
            default=False,
            action="store_true",
        )

    return parser


def validate_and_structure_thresholds(low_warning,
                                      low_critical,
                                      high_warning,
                                      high_critical,
                                      logger):
    high_thresholds = [
        threshold for threshold in (high_warning, high_critical)
        if threshold != ""
    ]
    logger.debug('High thresholds: {high}'.format(high=high_thresholds))
    low_thresholds = [
        threshold for threshold in (low_warning, low_critical)
        if threshold != ""
    ]
    logger.debug('Low thresholds: {low}'.format(low=low_thresholds))
    if (
        low_thresholds and high_thresholds
        and max(low_thresholds) >= min(high_thresholds)
    ):
        message = 'High thresholds must be higher than low thresholds'
        logger.error(message)
        print(message)
        sys.exit(STATUS_UNKNOWN)

    return {
        'low': {
            'warning': low_warning,
            'critical': low_critical,
        },
        'high': {
            'warning': high_warning,
            'critical': high_critical,
        },
    }


def run_check(script_path, target_type, hostname, oid, logger,
              ignore_unknown=False):
    # Make sure we have the target type ini file we need
    target_type_ini_path = '{base}/{target_type}.ini'.format(
        base=TARGET_TYPE_BASE_PATH,
        target_type=hashlib.md5(target_type).hexdigest(),
    )
    logger.debug('Using target type configuration from: {path}'.format(
        path=target_type_ini_path,
    ))
    if not os.path.exists(target_type_ini_path):
        valid = get_types('target', logger)
        valid_string = ','.join(valid) if valid else 'None'
        logger.error(
            'Target type configuration invalid. Valid options were: '
            '{valid}'.format(valid=valid_string)
        )
        print(
            'Could not find target type {type} ini file in {location}. '
            'Valid types were: {valid}'.format(
                type=target_type,
                location=TARGET_TYPE_BASE_PATH,
                valid=','.join(valid) if valid else 'None'
            )
        )
        # Unknown status as we couldn't perform the check
        sys.exit(STATUS_UNKNOWN)

    # This script expects to be located in the same plugins dir as check_snmp
    this_dir = os.path.dirname(os.path.realpath(script_path))
    check_snmp_script_name = 'check_snmp'
    check_snmp_location = os.path.join(
        this_dir,
        check_snmp_script_name,
    )
    logger.debug('Using check_snmp script at: {path}'.format(
        path=check_snmp_location,
    ))
    if not os.path.isfile(check_snmp_location):
        logger.error('check_snmp script not found')
        print(
            'check_snmp executable {target} not found in {location}. '
            'Wrapper script should be located in the same path as the '
            'check_snmp executable.'.format(
                location=this_dir,
                target=check_snmp_script_name,
            )
        )
        sys.exit(STATUS_UNKNOWN)

    # This will retrieve SNMP settings for a target type from file to avoid
    # exposing them to ps output on the command line
    extra_opts_arg = '--extra-opts=snmp_params@{ini_path}'.format(
        ini_path=target_type_ini_path,
    )

    command = [
        check_snmp_location,
        extra_opts_arg,
        '--hostname={hostname}'.format(hostname=hostname),
        '--oid={oid}'.format(oid=oid),
        '--timeout=2:3',  # Time-out after 2 seconds as unknown(3)
    ]
    logger.debug(
        'Executing command {raw_command}'.format(
            raw_command=command,
        )
    )

    result = None
    try:
        result = check_output(command)
    except CalledProcessError as err:
        if ignore_unknown and err.returncode == 3:
            logger.warn('Command returned unknown state, ignoring.')
            return None
        logger.error(
            'Command returned an unknown or error status. '
            'Status was {status}, output was: {output}'.format(
                status=err.returncode,
                output=err.output,
            )
        )
        # If it returned an unexpected error (any error) then we just pass
        # the results straight back
        print(err.output)
        sys.exit(err.returncode)

    return result


def get_perfdata(result):
    return result.split('|', 1)[1].rstrip('\n')


def get_floats_from_result(result):
    search_expression = RESULT_REGEX_BASE.format(val_string='[0-9. ]+')
    values = re.findall(search_expression, result)
    if values:
        values = values[0].split(' ')
        try:
            values = [float(value) for value in values if value != '']
        except ValueError:
            _fail_float_conversion(value)

    return values


def get_single_float_from_result(result):
    search_expression = RESULT_REGEX_BASE.format(val_string='[0-9.]+')
    value = re.findall(search_expression, result)
    if not value:
        print('Value not found in output: {output}'.format(output=result))
        sys.exit(STATUS_UNKNOWN)

    value = value[0]
    try:
        value = float(value)
    except ValueError:
        _fail_float_conversion(value)
    return value


def _fail_float_conversion(value):
    print('Could not convert "{value}" to float.'.format(value=value))
    sys.exit(STATUS_UNKNOWN)


def check_thresholds_and_exit(value, thresholds, perfdata, rate_check,
                              group=False):
    for level in 'low', 'high':
        # We check critical before warning so that we exit correctly on a
        # critical state, rather than having already exited on a warning
        # because a critical state also breaches the warning threshold.
        for state in 'critical', 'warning':
            threshold = thresholds[level][state]
            if threshold == "":
                continue
            elif level == 'low' and value <= threshold:
                output_and_exit(value, perfdata, state.upper(), level.upper(),
                                rate_check, group)
            elif level == 'high' and value >= threshold:
                output_and_exit(value, perfdata, state.upper(), level.upper(),
                                rate_check, group)

    output_and_exit(value, perfdata, 'OK', None, rate_check, group)


def get_instance_rate_storage_path(hostname, check):
    return RATE_INSTANCE_PATH.format(
        instance=hostname,
        check=check,
    )


def get_node_rate_storage_path(node, check):
    return RATE_NODE_PATH.format(
        node=node.replace('/', '_'),
        check=check,
    )


def store_value_and_calculate_rate(logger, value, path):
    logger.debug(
        'Attempting to store value ({value}) and calculate rate with data '
        'from {path}'.format(
            value=value,
            path=path,
        )
    )
    current_time = int(time.time())
    logger.debug('Current time: {current_time}'.format(
        current_time=current_time,
    ))

    old_results = None
    logger.debug('Attempting to load old results')
    try:
        with open(path) as data_handle:
            old_results = json.load(data_handle)
    except IOError:
        logger.debug('Previous results not found.')
        print("Could not open previous data to calculate rate.")
        sys.exit(STATUS_UNKNOWN)
    except ValueError:
        logger.warn('Previous data in {path} was in unknown format'.format(
            path=path,
        ))
        print(
            "Previous data was in an unknown format, cannot calculate rate."
        )
        sys.exit(STATUS_UNKNOWN)
    finally:
        logger.debug('Storing data')
        run(['mkdir', '-p', os.path.dirname(path)])
        with open(path, 'w') as save_handle:
            json.dump(
                obj={
                    'timestamp': current_time,
                    'result': value,
                },
                fp=save_handle,
            )
        logger.debug('Old data stored')

    logger.debug('Old results were: {old_results}'.format(
        old_results=old_results,
    ))

    if 'timestamp' in old_results and 'result' in old_results:
        logger.debug('Calculating rate')
        old_time = old_results['timestamp']
        interval = current_time - old_time
        logger.debug('Interval was: {interval}'.format(interval=interval))
        if interval < 1:
            logger.warn(
                'Previous data collection was too recent, cannot calculate '
                'rate'
            )
            print(
                "Previous data was collected too recently, cannot calculate "
                "rate."
            )
            sys.exit(STATUS_UNKNOWN)
        else:
            difference = value - old_results['result']
            logger.debug('Difference was: {diff}'.format(diff=difference))
            return float(difference)/interval
    else:
        logger.warn(
            'Old data in {path} was incomplete, cannot calculate rate'.format(
                path=path,
            )
        )
        print("Previous data was incomplete, cannot calculate rate.")
        sys.exit(STATUS_UNKNOWN)
