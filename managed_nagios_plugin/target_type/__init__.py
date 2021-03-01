import hashlib
import json
import os
from builtins import object

from managed_nagios_plugin._compat import text_type
from cloudify.exceptions import NonRecoverableError

from managed_nagios_plugin.check import create_check
from managed_nagios_plugin.constants import (
    BASE_OBJECTS_DIR,
)
from managed_nagios_plugin.snmp_utils import OIDLookup
from managed_nagios_plugin.utils import (
    deploy_configuration_file,
    deploy_file,
    trigger_nagios_reload
)


oid_lookup = OIDLookup()


def get_target_type_configuration_destination(name):
    return 'target_types/{name}.cfg'.format(
        name=hashlib.md5(name.encode('utf-8')).hexdigest(),
    )


def get_target_type_host_template_destination(name):
    return 'templates/{name}.cfg'.format(
        name=hashlib.md5(name.encode('utf-8')).hexdigest(),
    )


def get_reaction_configuration_destination(name):
    return os.path.join(
        BASE_OBJECTS_DIR,
        'target_types/{name}.json'.format(
            name=hashlib.md5(name.encode('utf-8')).hexdigest(),
        )
    )


def create_target_type(logger, name, description, check_relationships,
                       instance_failure_reaction, instance_health_check,
                       check_interval, retry_interval, max_check_retries):
    deploy_configuration_file(
        logger,
        source='resources/target_type.template',
        destination=get_target_type_configuration_destination(name),
        template_params={
            'name': name,
            'description': description,
        },
        reload_service=False,
        sudo=True,
    )

    deploy_configuration_file(
        logger,
        source='resources/target_type_host_template.template',
        destination=get_target_type_host_template_destination(name),
        template_params={
            'target_type': name,
            'check_command': instance_health_check,
            'check_interval': check_interval,
            'retry_interval': retry_interval,
            'max_check_retries': max_check_retries,
        },
        reload_service=False,
        sudo=True,
    )

    reactions = {'checks': {}, 'traps': {}}
    for check in check_relationships:
        props = check.node.properties
        # To avoid warnings in the logs, we'll set all notifications to 1
        # minute, or the check_interval, whichever is higher. This means that
        # notifications will be retried every minute or every check_interval
        # if health state of a check does not improve.
        # Nagios will not send notifications more often than check_interval,
        # and will leave a warning in the logs every time it reloads
        # configuration for each notification_interval that is set lower
        # than check_interval.
        notification_interval = max(1, int(props.get('check_interval', 1)))
        if check.node.type == 'cloudify.nagios.nodes.SNMPTrapReaction':
            normalised_oid = oid_lookup.get(props['trap_oid'])
            if props['reaction']:
                reactions['traps'][normalised_oid] = {
                    'workflow': make_workflow_object(
                        props['reaction'],
                    ),
                    'constraints': {
                        'min_instances': props['min_instances'],
                        'max_instances': props['max_instances'],
                    }
                }
            params = {
                'target_type': name,
                'oid': normalised_oid,
            }
            check_type = 'trap'
            disallowed = []
        elif check.node.type == 'cloudify.nagios.nodes.SNMPValueCheck':
            params = {
                'target_type': name,
                'check_description': props['check_description'],
                'snmp_oid': props['snmp_oid'],
                'low_warning_threshold': props['low_warning_threshold'],
                'low_critical_threshold': props['low_critical_threshold'],
                'high_warning_threshold': props['high_warning_threshold'],
                'high_critical_threshold': props['high_critical_threshold'],
                'max_check_retries': props['max_check_retries'],
                'check_interval': props['check_interval'],
                'retry_interval': props['retry_interval'],
                'notification_interval': notification_interval,
                'rate': '--rate' if props['rate_check'] else ''
            }
            check_type = 'snmp_poll'
            disallowed = []
        elif check.node.type == (
            'cloudify.nagios.nodes.SNMPAggregateValueCheck'
        ):
            params = {
                'target_type': name,
                'check_description': props['check_description'],
                'snmp_oids': props['snmp_oids'],
                'on_unknown': props['on_unknown'],
                'aggregation_type': props['aggregation_type'],
                'low_warning_threshold': props['low_warning_threshold'],
                'low_critical_threshold': props['low_critical_threshold'],
                'high_warning_threshold': props['high_warning_threshold'],
                'high_critical_threshold': props['high_critical_threshold'],
                'max_check_retries': props['max_check_retries'],
                'check_interval': props['check_interval'],
                'retry_interval': props['retry_interval'],
                'notification_interval': notification_interval,
                'rate': '--rate' if props['rate_check'] else ''
            }
            check_type = 'snmp_aggregate'
            disallowed = ['{{instance}}']
        else:
            raise NonRecoverableError(
                'Cannot parse check of type {node_type}'.format(
                    node_type=check.node.type,
                )
            )

        reaction = {}
        # Trap reactions are deployed separately
        if check_type != 'trap':
            for level in ('low', 'high'):
                property_name = 'action_on_{level}_threshold'.format(
                    level=level,
                )
                min_instances_limit_name = '{level}_min_instances'.format(
                    level=level,
                )
                max_instances_limit_name = '{level}_max_instances'.format(
                    level=level,
                )
                if props[property_name]:
                    action = make_workflow_object(props[property_name],
                                                  disallowed=disallowed)
                    reaction[level] = {
                        'workflow': action,
                        'constraints': {
                            'min_instances': props[min_instances_limit_name],
                            'max_instances': props[max_instances_limit_name],
                        }
                    }

        create_check(logger, check_type, name, check.node.id, params)

        if reaction:
            reactions['checks'][props['check_description']] = reaction

    host_reaction = make_workflow_object(instance_failure_reaction)
    if host_reaction:
        reactions['host'] = {'workflow': host_reaction}

    deploy_file(
        data=json.dumps(reactions),
        destination=get_reaction_configuration_destination(name),
        sudo=True,
    )

    trigger_nagios_reload(set_group=True)


def make_workflow_object(properties, disallowed=None):
    if disallowed is None:
        disallowed = []

    workflow = {}

    if properties['workflow_id']:
        for prop in ('workflow_id',
                     'parameters',
                     'allow_custom_parameters',
                     'force'):
            value = properties[prop]
            if isinstance(value, text_type):
                for substitution in disallowed:
                    if substitution in value:
                        raise NonRecoverableError(
                            'Disallowed substitution found in workflow '
                            'property "{prop}". Value was "{val}". '
                            'Disallowed substitutions are '
                            '{disallowed}.'.format(
                                prop=prop,
                                val=value,
                                disallowed=', '.join(disallowed),
                            )
                        )
            workflow[prop] = value

    return workflow


class _FakeFile(object):
    # To get a string from ConfigParser
    contents = ''

    def write(self, text):
        self.contents += text

    def __repr__(self):
        return self.contents


def get_connection_config_location(target_type):
    return os.path.join(
        BASE_OBJECTS_DIR, 'target_types',
        hashlib.md5(target_type.encode('utf-8')).hexdigest() + '.ini',
    )
