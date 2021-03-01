from managed_nagios_plugin._compat import SafeConfigParser as ConfigParser
from managed_nagios_plugin._compat import text_type
import hashlib
import os

from cloudify.decorators import operation
from cloudify.exceptions import NonRecoverableError

from managed_nagios_plugin.check import get_check_basedir
from managed_nagios_plugin.cloudify_utils import (
    get_all_relationship_targets,
)
from managed_nagios_plugin.target_type import (
    _FakeFile,
    create_target_type,
    get_connection_config_location,
    get_target_type_configuration_destination,
    get_target_type_host_template_destination,
)
from managed_nagios_plugin.nagios_utils import (
    get_hostgroup_members,
    get_node_details_from_name,
)
from managed_nagios_plugin.utils import (
    deploy_file,
    remove_configuration_file,
    run,
    _decode_if_bytes
)


@operation
def create(ctx):
    name = ctx.node.properties['name']
    description = ctx.node.properties['alias']

    ctx.logger.info('Validating instance health check command')
    available_checks = (
        'do-not-check',
        'check-host-icmp',
    )
    if ctx.node.properties['instance_health_check'] not in available_checks:
        raise NonRecoverableError(
            'Command "{cmd}" specified by instance_health_check was invalid. '
            'Valid options are: {options}'.format(
                cmd=ctx.node.properties['instance_health_check'],
                options=', '.join(available_checks),
            )
        )

    ctx.logger.info('Using most secure available SNMP configuration')
    connection_config = ConfigParser()
    connection_config.add_section('snmp_params')
    snmp_props = ctx.node.properties['snmp_properties']
    snmp_params = None

    # Pick the most secure snmp settings provided
    if snmp_props['v3']['username'] is not None:
        snmp_params = {
            'protocol': 3,
            'seclevel': 'authPriv',
            'authproto': 'SHA',
            'privproto': 'AES',
            'secname': snmp_props['v3']['username'],
            'authpasswd': snmp_props['v3']['auth_pass'],
            'privpasswd': snmp_props['v3']['priv_pass'],
        }
        if snmp_props['v3'].get('context'):
            snmp_params['context'] = snmp_props['v3']['context']
    elif snmp_props['v2c']['community'] is not None:
        snmp_params = {
            'protocol': '2c',
            'community': snmp_props['v2c']['community'],
        }

    if snmp_params is None:
        raise NonRecoverableError(
            'Currently checks require SNMP configuration.'
        )
    else:
        for key, value in snmp_params.items():
            connection_config.set('snmp_params', key, value)
        connection_config_text = _FakeFile()
        connection_config.write(connection_config_text)
        deploy_file(
            data=text_type(connection_config_text),
            destination=get_connection_config_location(name),
            sudo=True,
        )

    ctx.logger.info('Getting related checks')
    check_relationships = get_all_relationship_targets(
        ctx=ctx,
        target_relation_type='target_type_checks',
        no_target_error=(
            'Target types must be connected to 1+ checks with '
            'relationship {target_relation_type}'
        ),
    )

    ctx.logger.info('Deploying configuration')
    create_target_type(
        ctx.logger,
        name,
        description,
        check_relationships,
        instance_failure_reaction=ctx.node.properties[
            'action_on_instance_failure'],
        instance_health_check=ctx.node.properties[
            'instance_health_check'],
        check_interval=ctx.node.properties['check_interval'],
        retry_interval=ctx.node.properties['retry_interval'],
        max_check_retries=ctx.node.properties['max_check_retries'],
    )


@operation
def delete(ctx):
    name = ctx.node.properties['name']

    ctx.logger.info('Removing associated checks')
    run(['rm', '-rf',
         get_check_basedir(name)],
        sudo=True)

    ctx.logger.info('Removing associated targets')
    members = get_hostgroup_members(
        'target_type:{target_type}'.format(
            target_type=name,
        )
    )
    for member in members:
        node_details = get_node_details_from_name(member)
        if node_details:
            node_details = {
                key: hashlib.md5(_decode_if_bytes(value)).hexdigest()
                for key, value in node_details.items()
            }
            remove_configuration_file(
                ctx.logger,
                'deployments/{tenant}/{deployment}/{node}.cfg'.format(
                    **node_details
                ),
                sudo=True,
                reload_service=False,
            )
        else:
            remove_configuration_file(
                ctx.logger,
                'targets/{target}.cfg'.format(
                    target=hashlib.md5(_decode_if_bytes(member)).hexdigest(),
                ),
                sudo=True,
                reload_service=False,
            )

    ctx.logger.info('Removing tenant target types')
    target_type_config = '{name}.cfg'.format(name=name)
    # Each entry is: leading_path, directories, files
    for entry in os.walk('/etc/nagios/objects/target_types'):
        if entry[0] == '/etc/nagios/objects/target_types':
            continue
        else:
            if target_type_config in entry[2]:
                tenant = entry[0].rsplit('/', 1)[1]
                remove_configuration_file(
                    ctx.logger,
                    'target_types/{tenant}/{config}'.format(
                        tenant=tenant,
                        config=target_type_config,
                    ),
                    sudo=True,
                    reload_service=False,
                )

    ctx.logger.info('Removing target type template')
    remove_configuration_file(
        ctx.logger,
        get_target_type_host_template_destination(
            name,
        ),
        sudo=True,
        reload_service=False,
    )

    ctx.logger.info('Removing target type')
    remove_configuration_file(
        ctx.logger,
        get_target_type_configuration_destination(
            name,
        ),
        sudo=True,
    )

    # Remove connection config
    run(['rm', '-f',
         get_connection_config_location(name)],
        sudo=True)
