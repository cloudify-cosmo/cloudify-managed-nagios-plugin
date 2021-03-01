import hashlib
import json
import os

from managed_nagios_plugin._compat import text_type

from constants import (
    BASE_OBJECTS_DIR,
)
from utils import (
    deploy_configuration_file,
    deploy_file,
    make_config_subdir,
    run,
)
from nagiosrest_tenant import configure_tenant_group


def get_group_config_location(group_type):
    return os.path.join(
        BASE_OBJECTS_DIR,
        'groups/types/{group_type}.json'.format(
            group_type=hashlib.md5(group_type).hexdigest(),
        ),
    )


def get_group_host_configuration_destination(group_type, tenant):
    return 'groups/tenants/{tenant}/{group_type}.cfg'.format(
        group_type=hashlib.md5(group_type).hexdigest(),
        tenant=hashlib.md5(tenant).hexdigest(),
    )


def get_group_check_reaction_target_path(group_type,
                                         group_name,
                                         tenant):
    return os.path.join(
        BASE_OBJECTS_DIR,
        'groups/members/{tenant}/{group_type}/{group_name}_target'.format(
            group_type=group_type,
            group_name=group_name,
            tenant=tenant,
        ),
    )


def get_meta_group_reaction_target_path(group_type,
                                        group_instance_prefix,
                                        tenant):
    return os.path.join(
        BASE_OBJECTS_DIR,
        'groups/members/{tenant}/{group_type}/meta/'
        '{group_instance_prefix}_target'.format(
            group_type=group_type,
            group_instance_prefix=group_instance_prefix,
            tenant=tenant,
        ),
    )


def get_meta_group_reaction_configuration_path(group_type,
                                               group_instance_prefix,
                                               tenant):
    return os.path.join(
        BASE_OBJECTS_DIR,
        'groups/members/{tenant}/{group_type}/meta/'
        '{group_instance_prefix}.json'.format(
            group_type=group_type,
            group_instance_prefix=group_instance_prefix,
            tenant=tenant,
        ),
    )


def get_meta_group_configuration_destination(group_type,
                                             group_instance_prefix,
                                             tenant):
    return (
        'groups/group_instances/{tenant}/{group_type}/meta/'
        '{group_instance_prefix}.cfg'.format(
            group_type=hashlib.md5(group_type).hexdigest(),
            group_instance_prefix=hashlib.md5(
                group_instance_prefix
            ).hexdigest(),
            tenant=hashlib.md5(tenant).hexdigest(),
        )
    )


def get_group_check_configuration_destination(group_type,
                                              group_name,
                                              tenant):
    return (
        'groups/group_instances/{tenant}/{group_type}/'
        '{group_name}.cfg'.format(
            group_type=hashlib.md5(group_type).hexdigest(),
            group_name=hashlib.md5(group_name).hexdigest(),
            tenant=hashlib.md5(tenant).hexdigest(),
        )
    )


def get_group_members_path(group_type,
                           group_name,
                           tenant):
    return os.path.join(
        BASE_OBJECTS_DIR,
        (
            'groups/members/{tenant}/{group_type}/{group_name}'
        ).format(
            tenant=tenant,
            group_type=group_type,
            group_name=group_name,
        )
    )


def get_group_deployment_node_path(tenant, deployment,
                                   group_type, group_name):
    return os.path.join(
        get_group_members_path(
            tenant=tenant,
            group_type=group_type,
            group_name=group_name,
        ),
        deployment,
    )


def create_meta_group(logger,
                      group_instance_prefix,
                      group_type,
                      tenant,
                      approach,
                      unknown,
                      check_interval,
                      low_warning_threshold,
                      low_critical_threshold,
                      high_warning_threshold,
                      high_critical_threshold,
                      reaction_target,
                      low_reaction,
                      high_reaction):
    logger.info(
        'Creating meta group for prefix {prefix} '
        'for group {group_type}'.format(
            prefix=group_instance_prefix,
            group_type=group_type,
        )
    )

    logger.debug('Creating reaction configuration')
    reaction_conf = {
        'reactions': {}
    }
    if low_reaction:
        reaction_conf['reactions']['low'] = {
            'workflow': low_reaction,
        }
    if high_reaction:
        reaction_conf['reactions']['high'] = {
            'workflow': high_reaction,
        }
    reaction_conf_path = get_meta_group_reaction_configuration_path(
        group_type=group_type,
        group_instance_prefix=group_instance_prefix,
        tenant=tenant,
    )
    make_config_subdir(os.path.dirname(reaction_conf_path))
    deploy_file(
        data=json.dumps(reaction_conf),
        destination=reaction_conf_path,
        sudo=False,
    )

    logger.debug('Setting reaction target')
    reaction_target_path = get_meta_group_reaction_target_path(
        group_type=group_type,
        group_instance_prefix=group_instance_prefix,
        tenant=tenant,
    )
    make_config_subdir(os.path.dirname(reaction_target_path))
    deploy_file(
        data=reaction_target,
        destination=reaction_target_path,
        sudo=False,
    )

    logger.debug('Deploying meta group check configuration')
    meta_group_config_destination = get_meta_group_configuration_destination(
        group_type,
        group_instance_prefix,
        tenant,
    )
    make_config_subdir(
        os.path.dirname(
            os.path.join(
                BASE_OBJECTS_DIR,
                meta_group_config_destination,
            )
        )
    )
    check_config = {
        'group_type': group_type,
        'group_instance_prefix': group_instance_prefix,
        'tenant': tenant,
        'unknown': unknown,
        'approach': approach,
        'low_warning_threshold': low_warning_threshold,
        'low_critical_threshold': low_critical_threshold,
        'high_warning_threshold': high_warning_threshold,
        'high_critical_threshold': high_critical_threshold,
        'check_interval': check_interval,
    }
    logger.debug(
        'Full check configuration: {conf}'.format(conf=text_type(check_config))
    )
    deploy_configuration_file(
        logger,
        source='meta_group_check.template',
        destination=meta_group_config_destination,
        template_params=check_config,
        reload_service=True,
        use_pkg_data=False,
    )


def create_group_instance(logger,
                          group_name,
                          group_type,
                          tenant,
                          reaction_target):
    logger.info('Creating instance {name} of {group_type}'.format(
        name=group_name,
        group_type=group_type,
    ))

    logger.debug('Loading group check configuration')
    with open(get_group_config_location(group_type)) as config_handle:
        group_config = json.load(config_handle)
    check_config = group_config['check_configuration']
    logger.debug(
        'Check configuration loaded: {conf}'.format(conf=text_type(check_config))
    )

    logger.debug('Setting reaction target to {target}'.format(
        target=reaction_target,
    ))
    reaction_target_path = get_group_check_reaction_target_path(group_type,
                                                                group_name,
                                                                tenant)
    make_config_subdir(os.path.dirname(reaction_target_path))
    deploy_file(
        data=reaction_target,
        destination=reaction_target_path,
        sudo=False,
    )

    logger.info('Creating supporting hostgroups')
    configure_tenant_group(logger, tenant)

    logger.debug('Deploying group tenant configuration')
    group_config_destination = get_group_host_configuration_destination(
        group_type,
        tenant,
    )
    make_config_subdir(
        os.path.dirname(
            os.path.join(
                BASE_OBJECTS_DIR,
                group_config_destination,
            )
        )
    )
    deploy_configuration_file(
        logger,
        source='group.template',
        destination=group_config_destination,
        template_params={
            'group_type': group_type,
            'tenant': tenant,
        },
        reload_service=False,
        use_pkg_data=False,
    )

    logger.debug('Deploying group instance configuration')
    instance_config_destination = get_group_check_configuration_destination(
        group_type,
        group_name,
        tenant,
    )
    make_config_subdir(
        os.path.dirname(
            os.path.join(
                BASE_OBJECTS_DIR,
                instance_config_destination,
            )
        )
    )
    check_config.update({
        'group_type': group_type,
        'group_name': group_name,
        'tenant': tenant,
    })
    logger.debug(
        'Full check configuration: {conf}'.format(conf=text_type(check_config))
    )
    deploy_configuration_file(
        logger,
        source='group_check.template',
        destination=instance_config_destination,
        template_params=check_config,
        reload_service=True,
        use_pkg_data=False,
    )


def associate_node_with_group_instance(logger, tenant, deployment, node,
                                       group_type, group_name):
    # TODO: This should check the group type exists
    path = get_group_deployment_node_path(tenant, deployment,
                                          group_type, group_name)
    make_config_subdir(path)
    run(['touch', os.path.join(path, node)])
