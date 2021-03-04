#! /usr/bin/env python
import os
import re
import time

try:
    from .constants import TENANT_DEPLOYMENT_HOSTGROUP
    from .utils import get_node_id
except:
    from constants import TENANT_DEPLOYMENT_HOSTGROUP
    from utils import get_node_id

NAGIOS_EXTERNAL_COMMAND_FILE = '/var/spool/nagios/cmd/nagios.cmd'
NAGIOS_STATUS_FILE = '/var/log/nagios/status.dat'
NAGIOS_CONFIG_CACHE_FILE = '/var/spool/nagios/objects.cache'
COMMENT_AUTHOR = 'Cloudify'
INSTANCE_FINDER_FOR_TENANT_DEPLOYMENT = re.compile(
    '^tenant:(?P<tenant>[^/]+)/deployment:(?P<deployment>[^/]+)$'
)
INSTANCE_FINDER_FOR_TARGET_TYPE = re.compile(
    '^target_type:(?P<target_type>[^/]+)$'
)
NODE_DETAILS_FINDER = re.compile(
    '^tenant:(?P<tenant>[^/]+)/'
    'deployment:(?P<deployment>[^/]+)/'
    'node:(?P<node>[^/]+)$'
)


# This will be populated once, whereas the cache will be retrieved each time
# it is needed (as status check results may change)
NAGIOS_CONFIGURATION = None


class DeploymentGroupNotFound(Exception):
    pass


class HostNotHealthy(Exception):
    pass


def parse_nagios_data_file(data_file_path, separator):
    with open(data_file_path) as fh:
        raw_data = fh.readlines()

    conf_cache_prefix = 'define '
    sections = {}
    section = None
    section_contents = None
    for line in raw_data:
        line = line.strip()
        if not line.startswith(' ') and line.endswith('{'):
            if line.startswith(conf_cache_prefix):
                line = line[len(conf_cache_prefix):]
            section = line.split(' ')[0]
            section_contents = {}
        elif line == '}':
            if section in sections:
                sections[section].append(section_contents)
            else:
                sections[section] = [section_contents]
            section = None
            section_contents = None
        elif section and line:
            key, value = line.split(separator, 1)
            section_contents[key] = value.lstrip()

    return sections


def send_nagios_command(command):
    with open(NAGIOS_EXTERNAL_COMMAND_FILE, 'w') as command_handle:
        command_handle.write('[{time}] {command}\n'.format(
            command=command,
            time=time.time(),
        ))


def submit_passive_check_result(host, service, status, output):
    command = (
        'PROCESS_SERVICE_CHECK_RESULT;{host};{service};{status};{output}'
    )
    send_nagios_command(
        command.format(
            host=host,
            service=service,
            status=status,
            output=output,
        )
    )


def add_comment(host, comment):
    # ADD_HOST_COMMENT;<nagios host name>;<persist across nagios restarts>;
    # <author>;<comment>
    # From nagios docs: https://www.nagios.org/developerinfo/externalcommands/
    command = 'ADD_HOST_COMMENT;{host};1;{author};{comment}'
    send_nagios_command(
        command.format(
            host=host,
            comment=comment,
            author=COMMENT_AUTHOR,
        )
    )


def delete_comment(comment_id):
    command = 'DEL_HOST_COMMENT;{comment_id}'
    send_nagios_command(
        command.format(
            comment_id=comment_id,
        )
    )


def send_host_notification(host, comment):
    # SEND_CUSTOM_HOST_NOTIFICATION;<host_name>;<options>;<author>;<comment>
    # Force the notification, send it to all normal and escalated contacts,
    # and increment the notification number
    # See nagios docs for details of options
    options = '7'

    command = (
        'SEND_CUSTOM_HOST_NOTIFICATION;{host};{options};{author};{comment}'
    )

    send_nagios_command(
        command.format(
            host=host,
            comment=comment,
            author=COMMENT_AUTHOR,
            options=options,
        )
    )


def schedule_immediate_service_check(host_name, service_check_description):
    command = 'SCHEDULE_SVC_CHECK;{host};{service};{check_time}'
    send_nagios_command(
        command.format(
            host=host_name,
            service=service_check_description,
            check_time=int(time.time()) + 3,
        )
    )


def schedule_immediate_host_check(host_name):
    command = 'SCHEDULE_HOST_CHECK;{host};{check_time}'
    send_nagios_command(
        command.format(
            host=host_name,
            check_time=int(time.time()) + 3,
        )
    )


def delete_old_host_comments(max_age, nagios_status_dict):
    current_time = time.time()

    for hostcomment in nagios_status_dict['hostcomment']:
        if hostcomment['author'] != COMMENT_AUTHOR:
            continue

        comment_time = int(hostcomment['entry_time'])
        if current_time - comment_time > max_age:
            delete_comment(hostcomment['comment_id'])
        else:
            continue


def get_status_for_hostgroup(hostgroup_name,
                             nagios_status_dict):
    hosts = {}
    for hostgroup in NAGIOS_CONFIGURATION['hostgroup']:
        if hostgroup['hostgroup_name'] == hostgroup_name:
            break
    for host in hostgroup.get('members', '').split(','):
        hosts[host] = get_host_status_with_services(host, nagios_status_dict)
    return hosts


def get_host_status_with_services(host_name, nagios_status_dict):
    results = {
        'host_state': None,
        'healthy': [],
        'failing': [],
    }
    for host in nagios_status_dict['hoststatus']:
        if host['host_name'] == host_name:
            results['host_state'] = host['current_state']
            break
    for service in get_services_for_host(host_name, nagios_status_dict):
        if service['current_state'] == '0':
            results['healthy'].append(service['service_description'])
        else:
            results['failing'].append(service['service_description'])
    return results


def get_services_for_host(host_name, nagios_status_dict):
    services = []
    for svc in nagios_status_dict['servicestatus']:
        if svc['host_name'] == host_name:
            services.append(svc)
    return services


def recheck_all_failing_checks_for_host(host_name, host_status):
    if host_status['host_state'] != '0':
        schedule_immediate_host_check(host_name)
    for service in host_status['failing']:
        schedule_immediate_service_check(
            host_name=host_name,
            service_check_description=service,
        )


def recheck_all_failing_checks_for_hostgroup(hostgroup_name,
                                             nagios_status_dict):
    # TODO: This should be for a given node?
    hostgroup_state = get_status_for_hostgroup(
        hostgroup_name,
        nagios_status_dict,
    )
    for host_name, host_status in hostgroup_state.items():
        recheck_all_failing_checks_for_host(host_name, host_status)


def get_node_instances(tenant, deployment, node, logger):
    load_nagios_configuration()
    target_group = TENANT_DEPLOYMENT_HOSTGROUP.format(
        tenant=tenant,
        deployment=deployment,
    )
    logger.debug('Looking for target group: {group}'.format(
        group=target_group,
    ))
    deployment_group = None
    for hostgroup in NAGIOS_CONFIGURATION['hostgroup']:
        if hostgroup['hostgroup_name'] == target_group:
            deployment_group = hostgroup
            break
    logger.debug('Finished searching nagios configuration')

    if deployment_group is None:
        logger.error('Could not find target group {group}'.format(
            group=target_group,
        ))
        raise DeploymentGroupNotFound(target_group)
    logger.debug('Found target group: {details}'.format(
        details=deployment_group,
    ))

    all_instances = deployment_group['members'].split(',')
    logger.debug('Group members: {members}'.format(
        members=all_instances,
    ))
    target_instances = []
    for instance in all_instances:
        logger.debug(
            'Checking whether {instance} is part of node {node}'.format(
                instance=instance,
                node=node,
            )
        )
        instance_node_id = get_node_id(instance)
        logger.debug('Instance node is {node_id}'.format(
            node_id=instance_node_id,
        ))
        if instance_node_id == node:
            logger.debug('Added instance to target instances')
            target_instances.append(instance)
        else:
            logger.debug('Skipping instance')

    logger.debug('Target instances: {targets}'.format(
        targets=target_instances,
    ))
    return target_instances


def get_host_address(host_name, logger):
    load_nagios_configuration()

    logger.debug('Finding host IP for {name}'.format(
        name=host_name,
    ))
    if 'node:' in host_name:
        logger.warn('Only instances have addresses, nodes do not')
        # A node is not a real host, it has no address
        return None

    for host in NAGIOS_CONFIGURATION['host']:
        logger.debug('Checking host {host}'.format(host=host['host_name']))
        if host['host_name'] == host_name:
            logger.debug('Found host. Address found: {addr}'.format(
                addr=host['address'],
            ))
            return host['address']


def _get_details_for_instance(instance_id, finder_regex):
    load_nagios_configuration()
    for hostgroup in NAGIOS_CONFIGURATION['hostgroup']:
        result = finder_regex.match(
            hostgroup['hostgroup_name']
        )
        if result:
            result = result.groupdict()
            # Hostgroup members is comma delimited, but instance ID cannot
            # contain a comma so we can use a simple string check
            if instance_id in hostgroup.get('members', []):
                return result


def get_node_details_from_name(node_name):
    result = NODE_DETAILS_FINDER.match(node_name)
    if result:
        return result.groupdict()
    else:
        # Not a node, we can't get details from it
        return None


def get_tenant_and_deployment_for_instance(instance_id):
    result = _get_details_for_instance(
        instance_id,
        INSTANCE_FINDER_FOR_TENANT_DEPLOYMENT,
    )
    return result['tenant'], result['deployment']


def get_target_type_for_instance(instance_id):
    result = _get_details_for_instance(
        instance_id,
        INSTANCE_FINDER_FOR_TARGET_TYPE,
    )
    return result['target_type']


def get_host_name_from_address(address):
    load_nagios_configuration()
    for host in NAGIOS_CONFIGURATION['host']:
        if host['address'] == address:
            return host['host_name']


def get_hostgroup_members(group_name):
    load_nagios_configuration()
    members = []
    for group in NAGIOS_CONFIGURATION['hostgroup']:
        if group['hostgroup_name'] == group_name:
            members = group.get('members', '').split(',')
    return members


def get_node_instances_for_target(target):
    node_details = get_node_details_from_name(target)
    if node_details:
        node_id = node_details['node']
        tenant = node_details['tenant']
        deployment = node_details['deployment']
    else:
        node_id = get_node_id(target)
        tenant, deployment = get_tenant_and_deployment_for_instance(target)

    deployment_instances = get_hostgroup_members(
        'tenant:{tenant}/deployment:{deployment}'.format(
            tenant=tenant,
            deployment=deployment,
        )
    )
    return [
        instance for instance in deployment_instances
        if get_node_id(instance) == node_id and '/' not in instance
    ]


def load_nagios_configuration(force=False):
    global NAGIOS_CONFIGURATION
    if NAGIOS_CONFIGURATION and not force:
        return
    NAGIOS_CONFIGURATION = parse_nagios_data_file(NAGIOS_CONFIG_CACHE_FILE,
                                                  separator='\t')


def get_nagios_status():
    return parse_nagios_data_file(
        NAGIOS_STATUS_FILE, separator='=',
    )


def get_types(which_type, logger):
    types_path = {
        'group': '/etc/nagios/objects/groups/types',
        'target': '/etc/nagios/objects/target_types',
    }[which_type]

    type_files = [
        filename
        for filename in os.listdir(types_path)
        if filename.endswith('.cfg')
    ]
    logger.debug('Checking type files: {files}'.format(
        files=', '.join(type_files),
    ))

    found_types = []
    for type_file in type_files:
        logger.debug('Checking file: {path}'.format(path=type_file))
        with open(os.path.join(types_path, type_file)) as type_handle:
            type_content = type_handle.readlines()

        for line in type_content:
            line = line.strip()
            logger.debug('Checking line: {line}'.format(line=line))
            if which_type == 'group':
                if line.startswith('hostgroup_name '):
                    group = line.split('group_type:', 1)[1]
                    logger.debug('Found group: {group}'.format(group=group))
                    found_types.append(group)
            elif which_type == 'target':
                if 'target_type:' in line:
                    target_type = line.split('target_type:', 1)[1]
                    logger.debug('Found target type: {target_type}'.format(
                        target_type=target_type,
                    ))
                    found_types.append(target_type)

    return found_types
