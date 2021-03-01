import os
from subprocess import CalledProcessError
import time

from flask import (
    Flask,
    request,
)

import logging_utils
from nagiosrest_group import (
    create_group_instance,
    create_meta_group,
    associate_node_with_group_instance,
    get_group_check_configuration_destination,
    get_group_check_reaction_target_path,
    get_group_members_path,
    get_meta_group_configuration_destination,
    get_meta_group_reaction_configuration_path,
    get_meta_group_reaction_target_path,
)
from nagiosrest_target import (
    create_target,
    get_node_configuration_destination,
    get_target_configuration_destination,
    get_tenant_deployment_configuration_destination,
    get_tenant_target_type_configuration_destination,
)
from nagiosrest_tenant import (
    get_tenant_configuration_destination,
)
from constants import (
    BASE_OBJECTS_DIR,
    RATE_INSTANCE_BASE_PATH,
    RATE_NODE_BASE_PATH,
    TENANT_DEPLOYMENT_HOSTGROUP,
)
import nagios_utils
from utils import (
    remove_configuration_file,
    trigger_nagios_reload,
    get_node_id,
    run,
)

application = Flask(__name__)


REQUIRED_TARGET_CREATE_ARGS = (
    'instance_ip',
    'target_type',
)
OPTIONAL_TARGET_CREATE_ARGS = (
    'groups',
)
REQUIRED_GROUP_CREATE_ARGS = (
    'reaction_target',
)
REQUIRED_META_GROUP_CREATE_ARGS = (
    'approach',
    'unknown',
    'target',
)
OPTIONAL_META_GROUP_CREATE_ARGS = (
    'interval',
    'low_warning_threshold',
    'low_critical_threshold',
    'high_warning_threshold',
    'high_critical_threshold',
    'low_reaction',
    'high_reaction',
)


# Retrieved from flask.pocoo.org/snippets/69/
# Usage comment:
# This snippet by Armin Ronacher can be used freely for anything you like.
# Consider it public domain.
class RemoteUserMiddleware(object):
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        user = environ.pop('HTTP_PROXY_USER', None)
        environ['REMOTE_USER'] = user
        return self.app(environ, start_response)


application.wsgi_app = RemoteUserMiddleware(application.wsgi_app)


def get_user():
    return request.environ.get('REMOTE_USER')


@application.route("/")
def hello():
    return 'Hello ' + get_user() + '\n'


def check_request_json(logger, request, required_args):
    # TODO: This should be checking for any arguments that aren't in the
    # optional args list, and should provide feedback with optional args too
    if request.content_type != 'application/json' or not request.data:
        logger.error('Incorrect content type for create request. '
                     'Aborting')
        return (
            (
                'Content-Type header must be set to application/json '
                'and the following parameters supplied in a json dict: '
                '{args}. '
                '\n'.format(
                    args=','.join(required_args),
                )
            ),
            400
        )
    request_data = request.get_json()
    if not all(
        arg in request_data
        for arg in required_args
    ):
        logger.error('Required arguments were missing.')
        return (
            (
                'Not all arguments were supplied. Required args: '
                '{args}\n'.format(
                    args=','.join(required_args),
                )
            ),
            400
        )
    return request_data


@application.route("/groups/<tenant>/<group_type>/<group_name>",
                   methods=['PUT', 'DELETE'])
def groups(tenant, group_type, group_name):
    logger = logging_utils.Logger('nagiosrest')
    logger.info(
        'Group: '
        'Processing {method} for {name} of type {group_type}'.format(
            method=request.method,
            name=group_name,
            group_type=group_type,
        )
    )

    if request.method == 'PUT':
        logger.info('Creating group instance')
        request_data = check_request_json(logger, request,
                                          REQUIRED_GROUP_CREATE_ARGS)

        logger.debug('Checking group type {group_type} exists'.format(
            group_type=group_type,
        ))
        group_types = nagios_utils.get_types('group', logger)
        logger.debug('Found group types: {group_types}'.format(
            group_types=', '.join(group_types),
        ))
        if group_type not in group_types:
            message = (
                'Group type {group_type} was not valid. '
                'Group instance will not be created. '
                'Available group types are: {group_types}'.format(
                    group_type=request_data['group_type'],
                    group_types=', '.join(group_types),
                )
            )
            logger.error(message)
            return (message, 400)

        try:
            logger.debug('Attempting to add configuration')
            create_group_instance(
                logger,
                group_name,
                group_type,
                tenant,
                request_data['reaction_target'],
            )
            return 'Group instance {name} created\n'.format(name=group_name)
        except Exception as err:
            message = (
                'Failed to apply configuration with error {err_type}: '
                '{err_msg}'.format(
                    err_type=text_type(type(err)),
                    err_msg=text_type(err),
                )
            )
            logger.error(message)
            return (
                message,
                500
            )
    elif request.method == 'DELETE':
        logger.info('Deleting group instance')
        logger.debug('Removing group configuration')
        conf_path = get_group_check_configuration_destination(
            group_type,
            group_name,
            tenant,
        )
        remove_configuration_file(
            logger,
            conf_path,
        )

        logger.debug('Removing reaction target')
        reaction_target_path = get_group_check_reaction_target_path(
            group_type,
            group_name,
            tenant,
        )
        os.unlink(reaction_target_path)

        logger.debug('Removing group node listing')
        group_members_path = get_group_members_path(
            group_type,
            group_name,
            tenant,
        )
        run(['rm', '-rf', group_members_path])

        return '{group_name} of {group_type} for {tenant} deleted\n'.format(
            group_name=group_name,
            group_type=group_type,
            tenant=tenant,
        )


@application.route(
    "/metagroups/<tenant>/<group_type>/<group_instance_prefix>",
    methods=['PUT', 'DELETE'],
)
def meta_groups(tenant, group_type, group_instance_prefix):
    logger = logging_utils.Logger('nagiosrest')
    logger.info(
        'Meta group: '
        'Processing {method} for {name} of type {group_type}'.format(
            method=request.method,
            name=group_instance_prefix,
            group_type=group_type,
        )
    )

    if request.method == 'PUT':
        logger.info('Creating meta group')
        request_data = check_request_json(logger, request,
                                          REQUIRED_META_GROUP_CREATE_ARGS)

        logger.debug('Checking group type {group_type} exists'.format(
            group_type=group_type,
        ))
        group_types = nagios_utils.get_types('group', logger)
        logger.debug('Found group types: {group_types}'.format(
            group_types=', '.join(group_types),
        ))
        if group_type not in group_types:
            message = (
                'Group type {group_type} was not valid. '
                'Group instance will not be created. '
                'Available group types are: {group_types}'.format(
                    group_type=request_data['group_type'],
                    group_types=', '.join(group_types),
                )
            )
            logger.error(message)
            return (message, 400)

        try:
            logger.debug('Attempting to add configuration')
            create_meta_group(
                logger,
                group_instance_prefix,
                group_type,
                tenant,
                request_data['approach'],
                request_data['unknown'],
                request_data.get('interval', 1),
                request_data.get('low_warning_threshold', ""),
                request_data.get('low_critical_threshold', ""),
                request_data.get('high_warning_threshold', ""),
                request_data.get('high_critical_threshold', ""),
                request_data['target'],
                request_data.get('low_reaction'),
                request_data.get('high_reaction'),
            )
            return 'Meta group {name} created\n'.format(
                name=group_instance_prefix
            )
        except Exception as err:
            message = (
                'Failed to apply configuration with error {err_type}: '
                '{err_msg}'.format(
                    err_type=text_type(type(err)),
                    err_msg=text_type(err),
                )
            )
            logger.error(message)
            return (
                message,
                500
            )
    elif request.method == 'DELETE':
        logger.info('Deleting group instance')
        logger.debug('Removing group configuration')
        conf_path = get_meta_group_configuration_destination(
            group_type,
            group_instance_prefix,
            tenant,
        )
        remove_configuration_file(
            logger,
            conf_path,
        )

        logger.debug('Removing reaction configuration path')
        reaction_conf_path = get_meta_group_reaction_configuration_path(
            group_type,
            group_instance_prefix,
            tenant,
        )
        os.unlink(reaction_conf_path)

        logger.debug('Removing reaction target path')
        reaction_target_path = get_meta_group_reaction_target_path(
            group_type,
            group_instance_prefix,
            tenant,
        )
        os.unlink(reaction_target_path)

        return '{group_prefix} of {group_type} for {tenant} deleted\n'.format(
            group_prefix=group_instance_prefix,
            group_type=group_type,
            tenant=tenant,
        )


@application.route("/targets/<tenant>/<deployment>/<instance_id>",
                   methods=['PUT', 'DELETE'])
def targets(tenant, deployment, instance_id):
    logger = logging_utils.Logger('nagiosrest')
    logger.info(
        'Target: '
        'Processing {method} for {instance_id} in deployment {deployment} on '
        'tenant {tenant}'.format(
            method=request.method,
            instance_id=instance_id,
            deployment=deployment,
            tenant=tenant,
        )
    )

    if request.method == 'PUT':
        logger.info('Creating instance')
        request_data = check_request_json(logger, request,
                                          REQUIRED_TARGET_CREATE_ARGS)

        logger.debug('Checking target type {name} exists'.format(
            name=request_data['target_type'],
        ))
        target_types = nagios_utils.get_types('target', logger)
        logger.debug('Found target types: {target_types}'.format(
            target_types=', '.join(target_types),
        ))
        if request_data['target_type'] not in target_types:
            message = (
                'Target type {target_type} was not valid. '
                'Target will not be created. '
                'Available target types are: {target_types}'.format(
                    target_type=request_data['target_type'],
                    target_types=', '.join(target_types),
                )
            )
            logger.error(message)
            return (message, 400)

        try:
            logger.debug('Attempting to add configuration')
            create_target(
                logger,
                instance_id,
                request_data['instance_ip'],
                tenant,
                deployment,
                request_data['target_type'],
            )
        except Exception as err:
            message = (
                'Failed to apply configuration with error {err_type}: '
                '{err_msg}'.format(
                    err_type=text_type(type(err)),
                    err_msg=text_type(err),
                )
            )
            logger.error(message)
            return (
                message,
                500
            )
        logger.info(
            'Created {instance_id} in deployment {deployment} on '
            'tenant {tenant}'.format(
                method=request.method,
                instance_id=instance_id,
                deployment=deployment,
                tenant=tenant,
            )
        )
        logger.debug('Setting state of trap checks to OK')
        check = 0
        max_attempts = 15
        while check < max_attempts:
            nagios_status_dict = nagios_utils.get_nagios_status()
            logger.debug(
                'Current status dict loaded, checking services for host'
            )

            try:
                nagios_utils.get_target_type_for_instance(instance_id)
                break
            except TypeError:
                logger.debug('Instance not defined yet, retrying...')
                check += 1
                time.sleep(1)
                continue

        services = nagios_utils.get_services_for_host(instance_id,
                                                      nagios_status_dict)

        if services:
            logger.debug('Services found, looking for SNMPTRAP checks')
            for service in services:
                logger.debug('Checking service {name}'.format(
                    name=service['service_description'],
                ))
                if service['service_description'].split(':', 1)[1].startswith(
                    'SNMPTRAP '
                ):
                    logger.debug('Submitting OK passive check result')
                    nagios_utils.submit_passive_check_result(
                        host=instance_id,
                        service=service['service_description'],
                        status='0',
                        output='No traps received'
                    )
        else:
            logger.debug('Instance has no services')

        if 'groups' in request_data:
            logger.debug('Applying groups')
            # TODO: More error checking and helpful feedback (earlier in call)
            groups = request_data['groups']
            for group_type, group_name in groups:
                associate_node_with_group_instance(
                    logger,
                    tenant,
                    deployment,
                    get_node_id(instance_id),
                    group_type,
                    group_name,
                )

        return '{instance} target created\n'.format(instance=instance_id)
    elif request.method == 'DELETE':
        logger.info('Attempting to delete instance {instance_id}'.format(
            instance_id=instance_id,
        ))
        target_path = get_target_configuration_destination(instance_id)

        # Determine this before we delete the configuration
        rate_instance_path = RATE_INSTANCE_BASE_PATH.format(
            instance=nagios_utils.get_host_address(instance_id, logger),
        )

        try:
            logger.debug('Attempting to remove instance from {path}'.format(
                path=target_path,
            ))
            remove_configuration_file(
                logger,
                target_path,
                reload_service=False,
            )
        except CalledProcessError as err:
            # Perform this check afterwards to avoid race conditions while
            # providing some more accurate feedback
            if not os.path.exists(target_path):
                logger.warn(
                    'Could not remove instance, as it did not exist'
                )
                return (
                    'Target {name} does not exist.'.format(name=instance_id),
                    404
                )
            else:
                message = 'Failed to remove {name}. Error was: {err}'.format(
                    name=instance_id,
                    err=text_type(err),
                )
                logger.error(message)
                return (
                    message,
                    500
                )
        logger.debug('Removing any rate data from {path}'.format(
            path=rate_instance_path,
        ))
        run(['rm', '-rf', rate_instance_path])

        logger.debug('Determining related node and hostgroup names')
        this_node = get_node_id(instance_id)
        this_deployment_hostgroup = TENANT_DEPLOYMENT_HOSTGROUP.format(
            tenant=tenant,
            deployment=deployment,
        )
        this_tenant_hostgroup = 'tenant:{tenant}'.format(tenant=tenant)
        tenant_target_type_prefix = 'tenant:{tenant}/target_type:'.format(
            tenant=tenant,
        )

        logger.debug(
            'Checking for remaining instances with same node as '
            '{instance} in deployment {deployment} for tenant '
            '{tenant}'.format(
                instance=instance_id,
                deployment=deployment,
                tenant=tenant,
            ),
        )
        this_node_instances_found = False
        targets_dir = os.path.join(BASE_OBJECTS_DIR, 'targets')
        logger.debug('Looking for instances in {path}'.format(
            path=targets_dir,
        ))
        for instance in os.listdir(targets_dir):
            logger.debug(
                'Checking whether {instance} config file is part of node for '
                'deleted instance {deleted_instance}'.format(
                    instance=instance,
                    deleted_instance=instance_id,
                )
            )
            if not instance.endswith('.cfg'):
                logger.debug('{conf} is not nagios config, ignoring'.format(
                    conf=instance,
                ))
                # Not nagios configuration, ignore it.
                continue
            instance_name = instance[:-4]
            logger.debug('Instance name for config file is {name}'.format(
                name=instance_name,
            ))
            if get_node_id(instance_name) == this_node:
                logger.debug(
                    'Instance {name} has same node ID as deleted instance '
                    '{deleted}'.format(
                        name=instance_name,
                        deleted=instance_id,
                    )
                )
                # This instance belongs to a node with the same name
                # Check whether it also belongs to the same deployment
                try:
                    logger.debug('Attempting to read config {name}'.format(
                        name=instance,
                    ))
                    with open(
                        os.path.join(targets_dir, instance)
                    ) as inst_handle:
                        instance_config = inst_handle.read()
                except IOError:
                    # Most likely this file was deleted, e.g. by a workflow
                    # deleting all node instances of the same deployment
                    # Ignore this file
                    logger.warn(
                        'File {name} was unreadable. Treating file as '
                        'deleted by a concurrent workflow'.format(
                            name=instance,
                        )
                    )
                    continue
                if this_deployment_hostgroup in instance_config:
                    this_node_instances_found = True
                    logger.debug('Instances still exist for node')
                    break

        if not this_node_instances_found:
            logger.info(
                'No instances remaining, removing node for {instance} '
                'in deployment {deployment} on tenant {tenant}'.format(
                    instance=instance_id,
                    deployment=deployment,
                    tenant=tenant,
                )
            )
            path = get_node_configuration_destination(
                tenant,
                deployment,
                this_node,
            )
            logger.debug(
                'Removing instanceless node configuration from {path}'.format(
                    path=path,
                )
            )
            remove_configuration_file(
                logger,
                path,
                reload_service=False,
                # Don't cause failures on deployment uninstall
                ignore_missing=True,
            )
            logger.debug('Removed node configuration from {path}'.format(
                path=path,
            ))

            rate_node_path = RATE_NODE_BASE_PATH.format(
                node=this_node.replace('/', '_'),
            )
            logger.debug('Removing any rate data from {path}'.format(
                path=rate_node_path,
            ))
            run(['rm', '-rf', rate_node_path])

        nagios_utils.load_nagios_configuration()
        logger.info('Removing related empty hostgroups')
        for hostgroup in nagios_utils.NAGIOS_CONFIGURATION.get('hostgroup',
                                                               []):
            name = hostgroup['hostgroup_name']
            members = hostgroup.get('members')

            logger.debug('Group {group} has members: {members}'.format(
                group=name,
                members=members,
            ))
            if not members:
                remove_target = None
                if name == this_deployment_hostgroup:
                    logger.debug(
                        'Removing empty deployment hostgroup {group}'.format(
                            group=name,
                        ),
                    )
                    remove_target = \
                        get_tenant_deployment_configuration_destination(
                            tenant=tenant,
                            deployment=deployment,
                        )
                elif name == this_tenant_hostgroup:
                    logger.debug(
                        'Removing empty tenant hostgroup {group}'.format(
                            group=name,
                        )
                    )
                    remove_target = \
                        get_tenant_configuration_destination(
                            tenant=tenant,
                        )
                elif name.startswith(tenant_target_type_prefix):
                    logger.debug(
                        'Removing empty tenant target type hostgroup '
                        '{group}'.format(group=name),
                    )
                    # This will cover more than just this instance's
                    # target type, but should only take effect if the
                    # hostgroup is empty so this shouldn't cause problems.
                    target_type = name.split('target_type:')[1]
                    remove_target = \
                        get_tenant_target_type_configuration_destination(
                            tenant=tenant,
                            target_type=target_type,
                        )
                else:
                    # This isn't a host group we care about, ignore it
                    logger.debug(
                        'Host group {group} is not a candidate for '
                        'cleanup'.format(group=name),
                    )
                    remove_target = None

                if remove_target:
                    logger.debug(
                        'Group {group} to be removed has path: {path}'.format(
                            group=name,
                            path=remove_target,
                        )
                    )
                    remove_configuration_file(
                        logger,
                        remove_target,
                        reload_service=False,
                        # Don't cause failures on deployment uninstall
                        ignore_missing=True,
                    )
                    logger.info('Removed empty hostgroup {group}'.format(
                        group=name,
                    ))

        logger.debug('Triggering nagios reload')
        trigger_nagios_reload(set_group=False)

        logger.info(
            'Deleted {instance_id} from deployment {deployment} on '
            'tenant {tenant}'.format(
                method=request.method,
                instance_id=instance_id,
                deployment=deployment,
                tenant=tenant,
            )
        )
        return '{instance} deleted\n'.format(instance=instance_id)
