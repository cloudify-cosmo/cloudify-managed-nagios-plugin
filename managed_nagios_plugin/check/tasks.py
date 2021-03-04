import hashlib
import json
import os

from cloudify.decorators import operation
from cloudify.exceptions import NonRecoverableError

from managed_nagios_plugin.cloudify_utils import (
    get_all_relationship_targets,
)
from managed_nagios_plugin.constants import (
    BASE_OBJECTS_DIR,
)
from managed_nagios_plugin.utils import (
    deploy_configuration_file,
    deploy_file,
    make_config_subdir,
    run
)


@operation
def create_group(ctx):
    props = ctx.node.properties
    name = props['name']

    if ':' in name or '/' in name:
        raise NonRecoverableError(
            'Group names must not contain : or /.'
        )

    ctx.logger.info('Getting related checks')
    check_relationships = get_all_relationship_targets(
        ctx=ctx,
        target_relation_type='group_check',
        no_target_error=(
            'Group types must be connected to 1+ checks with '
            'relationship {target_relation_type}'
        ),
    )
    allowed_check_types = (
        'cloudify.nagios.nodes.SNMPAggregateValueCheck',
    )
    for check in check_relationships:
        if check.node.type not in allowed_check_types:
            raise NonRecoverableError(
                'Group checks only support targeting checks of type: '
                '{allowed}'.format(
                    allowed = ', '.join(allowed_check_types),
                )
            )

    ctx.logger.info('Generating group configuration')
    group_checks = get_all_relationship_targets(
        ctx=ctx,
        target_relation_type='group_check',
        no_target_error=(
            'Check groups must be associated with checks.'
        ),
    )
    check_descriptions = [
        check.node.properties['check_description']
        for check in group_checks
    ]

    configuration = {
        "services": check_descriptions,
        "reactions": {},
        "check_configuration": {
            "unknown": props["on_unknown"],
            "approach": props["aggregation_type"],
            "check_interval": props["check_interval"],
            "low_warning_threshold": props["low_warning_threshold"],
            "low_critical_threshold": props["low_critical_threshold"],
            "high_warning_threshold": props["high_warning_threshold"],
            "high_critical_threshold": props["high_critical_threshold"],
        },
    }
    for level in 'low', 'high':
        action_name = 'action_on_{level}_threshold'.format(level=level)
        if props[action_name]['workflow_id']:
            configuration['reactions'][level] = {
                'workflow': props[action_name]
            }

    ctx.logger.info('Creating group subdirectories')
    for subdir in ('groups/tenants',
                   'groups/types',
                   'groups/members',
                   'groups/checks'):
        make_config_subdir(subdir, sudo=True)

    ctx.logger.info('Creating group base configuration')
    deploy_file(
        data=json.dumps(configuration),
        destination=os.path.join(
            BASE_OBJECTS_DIR,
            'groups/types/{name}.json'.format(
                name=hashlib.md5(name.encode('utf-8')).hexdigest(),
            )
        ),
        sudo=True,
    )

    ctx.logger.info('Deploying check list')
    check_list = [
        check.node.properties['check_description']
        for check in check_relationships
    ]
    deploy_file(
        data=json.dumps(check_list),
        destination=os.path.join(
            BASE_OBJECTS_DIR,
            'groups/checks/{name}.json'.format(
                name=name,
            )
        ),
        sudo=True,
    )

    ctx.logger.info('Creating hostgroup')
    deploy_configuration_file(
        ctx.logger,
        source='resources/group_type.template',
        destination=os.path.join('groups/types', name + '.cfg'),
        template_params={
            'group_name': name,
        },
        reload_service=True,
        sudo=True,
    )


@operation
def delete_group(ctx):
    props = ctx.node.properties
    name = props['name'].encode('utf-8')

    members_base = os.path.join(BASE_OBJECTS_DIR, 'groups/members')
    members_path = os.path.join(members_base, '{tenant}/{name}')
    for tenant in run(['ls', members_base], sudo=True).splitlines():
        run(
            [
                'rm', '-rf', members_path.format(
                    tenant=hashlib.md5(tenant.encode('utf-8')).hexdigest(),
                    name=hashlib.md5(name).hexdigest(),
                )
            ],
            sudo=True,
        )

    group_tenant_conf_base = os.path.join(BASE_OBJECTS_DIR, 'groups/tenants')
    group_tenant_conf_path = os.path.join(group_tenant_conf_base,
                                          '{tenant}/{name}.cfg')
    for tenant in run(['ls', members_base], sudo=True).splitlines():
        run(
            [
                'rm', '-f', group_tenant_conf_path.format(
                    tenant=hashlib.md5(tenant.encode('utf-8')).hexdigest(),
                    name=hashlib.md5(name).hexdigest(),
                ),
            ],
            sudo=True,
        )

    for group_conf in (
        'groups/types/{name}.json',
        'groups/types/{name}.cfg',
    ):
        group_conf_path = os.path.join(BASE_OBJECTS_DIR, group_conf).format(
            name=hashlib.md5(name).hexdigest(),
        )
        run(['rm', '-f', group_conf_path], sudo=True)
