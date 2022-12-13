import grp
import json
import logging
import os
import pkgutil
import tempfile

from cloudify.decorators import operation
from cloudify.exceptions import NonRecoverableError

from managed_nagios_plugin._compat import text_type
from managed_nagios_plugin.constants import (
    BASE_OBJECTS_DIR,
    OBJECT_DIR_PERMISSIONS,
    OBJECT_OWNERSHIP,
    RATE_BASE_PATH,
)
from managed_nagios_plugin.rest_utils import (
    get_entities,
    run_workflow,
    StartWorkflowFailed,
)
from managed_nagios_plugin.utils import (
    deploy_configuration_file,
    deploy_file,
    disable_service,
    download_and_deploy_file_from_blueprint,
    enable_service,
    generate_certs,
    reload_systemd_configuration,
    run,
    start_service,
    stop_service,
    yum_install,
    yum_remove,
    _decode_if_bytes
)

SSL_KEY_PATH = '/etc/nagios/ssl.key'
SSL_CERT_PATH = '/etc/nagios/ssl.crt'
BLUEPRINT_SSL_KEY_PATH = 'ssl/{key_file}'
BLUEPRINT_SSL_CERT_PATH = 'ssl/{cert_file}'
NAGIOSREST_SERVICES = ['nagiosrest-gunicorn', 'httpd']


@operation
def create(ctx):
    props = ctx.node.properties

    ctx.logger.info('Validating SSL properties')
    if bool(props['ssl_certificate']) != bool(props['ssl_key']):
        raise NonRecoverableError(
            'Either ssl_certificate and ssl_key must both be provided, '
            'or neither of them must be provided. '
            'ssl_certificate was: {ssl_certificate}; '
            'ssl_key was: {ssl_key}'.format(
                ssl_certificate=props['ssl_certificate'],
                ssl_key=props['ssl_key'],
            )
        )

    ctx.logger.info('Enabling EPEL (if required)')
    yum_install(text_type('epel-release'))

    ctx.logger.info('Installing required packages')
    x = run(['cd', '/tmp'], sudo=True)
    ctx.logger.info(x)
    yum_install(['wget'])
    x = run(['wget',
             'https://assets.nagios.com/downloads/nagiosxi/xi-latest.tar.gz'],
            sudo=True)
    ctx.logger.info(x)
    x = run(['tar', 'xzf', 'xi-latest.tar.gz'], sudo=True)
    ctx.logger.info(x)
    x = run(['cd', 'nagiosxi'], sudo=True)
    ctx.logger.info(x)
    x = run(['./fullinstall'], sudo=True)
    ctx.logger.info(x)
    # yum_install([
    #     'mod_ssl',
    #     'nagios',
    #     'nagios-plugins-disk',
    #     'nagios-plugins-load',
    #     'nagios-plugins-ping',
    #     'nagios-plugins-snmp',
    #     'nagios-selinux',
    #     'net-snmp',
    #     'net-snmp-utils',
    #     'python-flask',
    #     'python-gunicorn',
    #     'python-jinja2',
    #     'python-requests',
    #     'selinux-policy-devel',
    #     'incron',
    # ])

    ctx.logger.info('Deploying SELinux configuration')
    # Prepare SELinux context for trap handler
    tmp_path = tempfile.mkdtemp()
    with open(
        os.path.join(tmp_path, 'cloudify-nagios-snmp-trap-handler.te'), 'w',
    ) as policy_handle:
        policy_handle.write(_decode_if_bytes(pkgutil.get_data(
            'managed_nagios_plugin',
            'resources/selinux/cloudify_nagios_snmp_trap_handler.te',
        )))
    run(['make', '-f', '/usr/share/selinux/devel/Makefile', '-C', tmp_path],
        sudo=True)
    run(['semodule',
         '-i',
         os.path.join(tmp_path, 'cloudify-nagios-snmp-trap-handler.pp')],
        sudo=True)
    run(['rm', '-rf', tmp_path], sudo=True)

    ctx.logger.info('Deploying nagios plugins and SNMP trap handler')
    for supporting_lib in ('_compat.py',
                           'constants.py',
                           'utils.py',
                           'snmp_utils.py',
                           'nagios_utils.py',
                           'rest_utils.py',
                           'resources/scripts/nagios_plugin_utils.py',
                           'resources/scripts/logging_utils.py'):
        if supporting_lib.startswith('resources/scripts/'):
            destination_filename = supporting_lib[len('resources/scripts/'):]
        else:
            destination_filename = supporting_lib
        deploy_file(
            data=pkgutil.get_data(
                'managed_nagios_plugin',
                supporting_lib,
            ),
            destination='/usr/lib64/nagios/plugins/' + destination_filename,
            ownership='root.nagios',
            permissions='440',
            sudo=True,
        )
    for script in ('check_snmp_numeric',
                   'check_snmp_aggregate',
                   'check_group_aggregate',
                   'check_group_meta_aggregate',
                   'cloudify_nagios_snmp_trap_handler',
                   'notify_cloudify',
                   'check_nagios_command_file',
                   'check_snmptrap_checks'):
        source = os.path.join('resources/scripts/', script)
        script_content = pkgutil.get_data('managed_nagios_plugin', source)
        destination = os.path.join('/usr/lib64/nagios/plugins', script)
        deploy_file(
            data=script_content,
            destination=destination,
            permissions='550',
            sudo=True,
        )

    ctx.logger.info('Deploying nagiosrest')
    run(['mkdir', '-p', '/usr/local/www/nagiosrest'], sudo=True)
    for nagiosrest_file in ('nagiosrest.py',
                            'nagiosrest_group.py',
                            'nagiosrest_target.py',
                            'nagiosrest_tenant.py',
                            'logging_utils.py'):
        deploy_file(
            data=pkgutil.get_data(
                'managed_nagios_plugin',
                'resources/scripts/' + nagiosrest_file,
            ),
            destination='/usr/local/www/nagiosrest/' + nagiosrest_file,
            ownership='root.nagios',
            permissions='440',
            sudo=True,
        )
    for supporting_lib in ('_compat.py',
                           'nagios_utils.py',
                           'utils.py',
                           'constants.py'):
        deploy_file(
            data=pkgutil.get_data(
                'managed_nagios_plugin',
                supporting_lib,
            ),
            destination='/usr/local/www/nagiosrest/' + supporting_lib,
            ownership='root.nagios',
            permissions='440',
            sudo=True,
        )
    for template in ('hostgroup.template', 'target.template', 'node.template',
                     'group.template', 'group_check.template',
                     'meta_group_check.template'):
        deploy_file(
            data=pkgutil.get_data(
                'managed_nagios_plugin',
                os.path.join('resources', template),
            ),
            destination='/usr/local/www/nagiosrest/' + template,
            ownership='root.nagios',
            permissions='440',
            sudo=True,
        )
    deploy_file(
        data=pkgutil.get_data(
            'managed_nagios_plugin',
            'resources/base_configuration/systemd_nagiosrest.conf',
        ),
        destination='/usr/lib/systemd/system/nagiosrest-gunicorn.service',
        ownership='root.root',
        permissions='440',
        sudo=True,
    )

    ctx.logger.info('Deploying notification configuration script')
    deploy_file(
        data=pkgutil.get_data(
            'managed_nagios_plugin',
            'resources/scripts/update_notify_cloudify_configuration',
        ),
        destination='/usr/local/bin/update_notify_cloudify_configuration',
        ownership='root.root',
        permissions='500',
        sudo=True,
        # Must have the group of the agent user for reconcile operation to
        # work correctly
        template_params={'group': grp.getgrgid(os.getgid()).gr_name},
    )
    deploy_file(
        data=pkgutil.get_data(
            'managed_nagios_plugin',
            '_compat.py',
        ),
        destination='/usr/local/bin/_compat.py',
        ownership='root.root',
        permissions='400',
        sudo=True,
    )
    deploy_file(
        data=pkgutil.get_data(
            'managed_nagios_plugin',
            'utils.py',
        ),
        destination='/usr/local/bin/utils.py',
        ownership='root.root',
        permissions='400',
        sudo=True,
    )
    deploy_file(
        data=pkgutil.get_data(
            'managed_nagios_plugin',
            'constants.py',
        ),
        destination='/usr/local/bin/constants.py',
        ownership='root.root',
        permissions='400',
        sudo=True,
    )

    ctx.logger.info(
        'Creating directory structure for storing temporary rate data'
    )
    for rate_dir in ('nodes', 'instances'):
        rate_storage_path = os.path.join(RATE_BASE_PATH, rate_dir)
        run(['mkdir', '-p', rate_storage_path], sudo=True)
        run(['chown', 'nagios.', rate_storage_path], sudo=True)
        run(['restorecon', rate_storage_path], sudo=True)

    if props['ssl_certificate']:

        if props['ssl_certificate'].startswith("-----BEGIN CERTIFICATE-----"):
            deploy_file(
                data=props['ssl_key'],
                destination=SSL_KEY_PATH,
                ownership='root.root',
                permissions='440',
                sudo=True,
            )
            deploy_file(
                data=props['ssl_certificate'],
                destination=SSL_CERT_PATH,
                ownership='root.root',
                permissions='444',
                sudo=True,
            )
        else:
            download_and_deploy_file_from_blueprint(
                source=BLUEPRINT_SSL_KEY_PATH.format(
                    key_file=props['ssl_key'],
                ),
                destination=SSL_KEY_PATH,
                ownership='root.root',
                permissions='440',
                ctx=ctx,
            )
            download_and_deploy_file_from_blueprint(
                source=BLUEPRINT_SSL_CERT_PATH.format(
                    cert_file=props['ssl_certificate'],
                ),
                destination=SSL_CERT_PATH,
                ownership='root.root',
                permissions='444',
                ctx=ctx,
            )
    else:
        ctx.logger.info('Generating SSL certificate')
        generate_certs(SSL_KEY_PATH, SSL_CERT_PATH, ctx.logger)
    with open(SSL_CERT_PATH) as crt_handle:
        ctx.instance.runtime_properties['ssl_certificate'] = crt_handle.read()

    ctx.logger.info('Reloading systemd configuration')
    reload_systemd_configuration()


@operation
def configure(ctx):
    props = ctx.node.properties

    ctx.logger.info('Configuring nagios web user')
    username = props['nagios_web_username']
    password = props['nagios_web_password']
    tmpdir = tempfile.mkdtemp()
    tmp_htpass = os.path.join(tmpdir, 'passwd')
    run(['htpasswd', '-bc', tmp_htpass, username, password])
    run(['mv', tmp_htpass, '/etc/nagios/passwd'], sudo=True)
    run(['rm', '-rf', tmpdir])
    run(['chown', 'root.apache', '/etc/nagios/passwd'], sudo=True)
    run(['chmod', '640', '/etc/nagios/passwd'], sudo=True)
    run(['usermod', '-G', 'nagios', 'apache'], sudo=True)

    ctx.logger.info('Deploying automated reaction configuration')
    # We're using username+password because current token implementation is
    # unsuitable for this.
    reaction_configuration = {
        'username': props['cloudify_manager_username'],
        'password': props['cloudify_manager_password'],
    }
    deploy_file(
        data=json.dumps(reaction_configuration),
        destination='/etc/nagios/cloudify_manager.json',
        ownership='nagios.{group}'.format(
            # Must have the group of the agent user for reconcile operation to
            # work correctly
            group=grp.getgrgid(os.getgid()).gr_name,
        ),
        permissions='440',
        sudo=True,
    )
    notification_plugin_storage_dir = '/var/spool/nagios/cloudifyreaction'
    run(['mkdir', '-p', notification_plugin_storage_dir], sudo=True)
    run(['restorecon', notification_plugin_storage_dir], sudo=True)
    run(['chown', 'nagios.nagios', notification_plugin_storage_dir],
        sudo=True)
    run(['chmod', '750', notification_plugin_storage_dir], sudo=True)

    ctx.logger.info('Preparing object paths')
    run(['rm', '-rf', BASE_OBJECTS_DIR], sudo=True)
    object_subdirs = [
        'checks',
        'commands',
        'contacts',
        'groups/group_instances',
        'groups/tenants',
        'groups/types',
        'templates',
        'timeperiods',
        'deployments',
        'snmp_traps',
        'targets',
        'target_types',
        'tenants',
    ]
    for subdir in object_subdirs:
        subdir = os.path.join(BASE_OBJECTS_DIR, subdir)
        run(['mkdir', '-p', subdir], sudo=True)
    run(['chown', '-R', OBJECT_OWNERSHIP, BASE_OBJECTS_DIR], sudo=True)
    run(['chmod', '-R', OBJECT_DIR_PERMISSIONS, BASE_OBJECTS_DIR], sudo=True)

    ctx.logger.info('Deploying nagios object configuration')
    config_source_dest_params = (
        # Fully qualified paths because these two go outside the objects dir
        ('cgi.cfg', '/etc/nagios/cgi.cfg', {'user': username}),
        ('nagios.cfg', '/etc/nagios/nagios.cfg', {}),
        # The rest are 'normal' configuration files
        ('base_system.cfg', 'base_system.cfg', {}),
        ('command_host_icmp.cfg', 'commands/check_host_icmp.cfg', {}),
        ('command_no_check.cfg', 'commands/no_check.cfg', {}),
        ('command_local_load.cfg', 'commands/check_local_load.cfg', {}),
        ('command_local_disk.cfg', 'commands/check_local_disk.cfg', {}),
        ('command_snmp_value.cfg', 'commands/check_snmp_value.cfg', {}),
        ('command_check_nagios_command_file.cfg',
         'commands/check_nagios_command_file.cfg', {}),
        ('command_snmp_aggregate.cfg',
         'commands/check_snmp_aggregate.cfg', {}),
        ('command_group_aggregate.cfg',
         'commands/check_group_aggregate.cfg', {}),
        ('command_group_meta_aggregate.cfg',
         'commands/check_group_meta_aggregate.cfg', {}),
        ('command_snmptrap_checks.cfg',
         'commands/check_snmptrap_checks.cfg', {}),
        ('notification.cfg', 'commands/notify_automation.cfg', {}),
        ('contact.cfg', 'contacts/automation.cfg', {}),
        ('template_generic_service.cfg', 'templates/generic_service.cfg', {}),
        ('template_generic_host.cfg', 'templates/generic_host.cfg', {}),
        ('template_pseudo_host.cfg', 'templates/pseudo_host.cfg', {}),
        ('timeperiod_24x7.cfg', 'timeperiods/24x7.cfg', {}),
    )
    for source, dest, params in config_source_dest_params:
        deploy_configuration_file(
            ctx.logger,
            source=os.path.join('resources/base_configuration', source),
            destination=dest,
            template_params=params,
            # We can't validate before we've put all of the configuration in
            # place as it will be invalid until it's finished
            validate=False,
            # We can't reload, it's not running yet
            reload_service=False,
            sudo=True,
        )

    ctx.logger.info('Configuring httpd for ssl')
    deploy_file(
        data=pkgutil.get_data(
            'managed_nagios_plugin',
            'resources/base_configuration/httpd.conf',
        ),
        destination='/etc/httpd/conf/httpd.conf',
        ownership='root.apache',
        permissions='440',
        sudo=True,
    )
    deploy_file(
        data=pkgutil.get_data(
            'managed_nagios_plugin',
            'resources/base_configuration/ssl.conf',
        ),
        destination='/etc/httpd/conf.d/ssl.conf',
        ownership='root.apache',
        permissions='440',
        sudo=True,
    )

    ctx.logger.info('Configuring httpd for nagiosrest')
    deploy_file(
        data=pkgutil.get_data(
            'managed_nagios_plugin',
            'resources/base_configuration/httpd_nagiosrest.conf',
        ),
        destination='/etc/httpd/conf.d/nagiosrest.conf',
        ownership='root.apache',
        permissions='440',
        sudo=True,
    )

    ctx.logger.info('Allowing nagiosrest to restart nagios')
    deploy_file(
        data=pkgutil.get_data(
            'managed_nagios_plugin',
            'resources/base_configuration/sudoers-nagiosrest',
        ),
        destination='/etc/sudoers.d/nagios-service-restart',
        ownership='root.root',
        permissions='440',
        sudo=True,
    )

    ctx.logger.info('Deploying base SNMP configuration')
    deploy_file(
        data=pkgutil.get_data(
            'managed_nagios_plugin',
            'resources/base_configuration/snmp',
        ),
        destination='/etc/snmp/snmp.conf',
        ownership='root.root',
        permissions='440',
        sudo=True,
    )

    trap_community = ctx.node.properties['trap_community']
    if trap_community:
        ctx.logger.info('Configuring SNMP traps to use handler')
        deploy_file(
            data=pkgutil.get_data(
                'managed_nagios_plugin',
                'resources/base_configuration/snmptrapd',
            ),
            destination='/etc/snmp/snmptrapd.conf',
            ownership='root.root',
            permissions='440',
            sudo=True,
            template_params={
                'trap_community': trap_community,
            },
        )

    ctx.logger.info('Configuring notification script')
    deploy_file(
        data=pkgutil.get_data(
            'managed_nagios_plugin',
            'resources/base_configuration/incron.allow',
        ),
        destination='/etc/incron.allow',
        ownership='root.root',
        permissions='440',
        sudo=True,
    )
    deploy_file(
        data=pkgutil.get_data(
            'managed_nagios_plugin',
            'resources/base_configuration/incron_root_spool',
        ),
        destination='/var/spool/incron/root',
        ownership='root.root',
        permissions='400',
        template_params={
            'homedir': os.path.expanduser('~'),
        },
        sudo=True,
    )
    agent_config_dir = os.path.join(
        os.path.expanduser('~'),
        '.cfy-agent',
    )
    agent_configs = [
        os.path.join(agent_config_dir, filename)
        for filename in os.listdir(agent_config_dir)
    ]
    # We'll use the most recently updated agent config
    current_agent_config = max(agent_configs, key=os.path.getmtime)
    run(
        [
            '/usr/local/bin/update_notify_cloudify_configuration',
            current_agent_config,
        ],
        sudo=True,
    )

    ctx.logger.info('Deploying logging configuration')
    level = props['component_log_level'].upper()
    validate_level = logging.getLevelName(level)
    if not isinstance(validate_level, int):
        raise NonRecoverableError(
            '{level} is not a valid logging level. '
            'It is recommended that component_log_level be set to one of '
            'DEBUG, INFO, WARNING, ERROR'.format(level=level)
        )
    component_logging_config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'default': {
                'format': '%(name)s(%(process)s) [%(levelname)s]: %(message)s',
            },
        },
        'handlers': {
            'syslog': {
                'formatter': 'default',
                'level': level,
                'class': 'logging.handlers.SysLogHandler',
                'address': '/dev/log',
            },
        },
        'loggers': {
            '': {
                'handlers': ['syslog'],
                'level': level,
                'propagate': True,
            },
        },
    }
    deploy_file(
        data=json.dumps(component_logging_config),
        destination='/etc/nagios/cloudify_components_logging.cfg',
        ownership='root.nagios',
        permissions='440',
        sudo=True,
    )
    deploy_file(
        data=pkgutil.get_data(
            'managed_nagios_plugin',
            'resources/base_configuration/logrotate_config',
        ),
        destination='/etc/logrotate.d/managed_nagios',
        ownership='root.root',
        permissions='444',
        sudo=True,
    )
    deploy_file(
        data=pkgutil.get_data(
            'managed_nagios_plugin',
            'resources/base_configuration/rsyslog_config',
        ),
        destination='/etc/rsyslog.d/managed_nagios_logging.conf',
        ownership='root.root',
        permissions='444',
        sudo=True,
    )
    stop_service('rsyslog')
    start_service('rsyslog')


@operation
def start(ctx):
    ctx.logger.info('Enabling and starting nagios and httpd services')
    services = ['nagios', 'incrond']
    if ctx.node.properties['start_nagiosrest']:
        services.extend(NAGIOSREST_SERVICES)
    if ctx.node.properties['trap_community']:
        services.append('snmptrapd')
    for service in services:
        enable_service(service)
        start_service(service)


@operation
def delete(ctx):
    ctx.logger.info('Uninstalling nagios and web server packages')
    yum_remove([
        'nagios',
        'httpd',  # Installed by nagios, remove it as it is outward facing
        'nagios-selinux',
        'nagios-plugins-load',
        'nagios-plugins-disk',
        'nagios-plugins-ping',
        'nagios-plugins-snmp',
        'net-snmp',
    ])

    ctx.logger.info('Removing nagiosrest')
    stop_service('nagiosrest-gunicorn')
    disable_service('nagiosrest-gunicorn')
    run(['rm', '/usr/lib/systemd/system/nagiosrest-gunicorn.service'],
        sudo=True)
    reload_systemd_configuration()

    ctx.logger.info('Removing leftover data, configuration, and scripts')
    for path in (
        '/etc/nagios',
        '/etc/httpd',
        '/usr/lib64/nagios',
        '/usr/local/www/nagiosrest',
        '/var/spool/nagios',
        '/var/log/nagios',
        '/etc/snmp',
        '/var/spool/incron/root',
    ):
        run(['rm', '-rf', path], sudo=True)


def _node_has_nagiosrest_properties(node):
    return 'nagiosrest_monitoring' in node.get('properties', {})


@operation
def reconcile_monitoring(ctx, only_deployments=None, only_tenants=None):
    if not only_deployments:
        only_deployments = []
    if not only_tenants:
        only_tenants = []
    ctx.logger.info('Getting tenant list')
    tenants = [
        tenant['name']
        for tenant in get_entities(
            entity_type='tenants',
            tenant='default_tenant',
            properties=['name'],
            logger=ctx.logger,
        )
    ]

    problem_deployments = {}
    targets = None
    for tenant in tenants:
        if only_tenants and tenant not in only_tenants:
            ctx.logger.info('Skipping tenant {tenant}'.format(
                tenant=tenant,
            ))
            continue
        ctx.logger.info('Checking deployments for tenant {tenant}'.format(
            tenant=tenant,
        ))
        targets = {}
        interesting_nodes = get_entities(
            entity_type='nodes',
            tenant=tenant,
            properties=['deployment_id', 'id'],
            logger=ctx.logger,
            include=_node_has_nagiosrest_properties,
        )
        ctx.logger.info(
            'Found {num} nodes with monitoring configuration'.format(
                num=len(interesting_nodes),
            )
        )
        notified_skipped_deployments = []
        for node in interesting_nodes:
            dep_id = node['deployment_id']
            if only_deployments and dep_id not in only_deployments:
                if dep_id not in notified_skipped_deployments:
                    ctx.logger.info('Skipping deployment {dep}'.format(
                        dep=dep_id,
                    ))
                    notified_skipped_deployments.append(dep_id)
                continue
            if dep_id not in targets:
                targets[dep_id] = []
            targets[dep_id].append(node['id'])

        if targets:
            for deployment, nodes in targets.items():
                ctx.logger.info(
                    'Starting monitoring for deployment {deployment}'.format(
                        deployment=deployment,
                    )
                )
                try:
                    run_workflow(
                        tenant=tenant,
                        deployment=deployment,
                        workflow_id='execute_operation',
                        parameters={
                            "node_ids": nodes,
                            "operation": (
                                "cloudify.interfaces.monitoring.start"
                            ),
                        },
                        allow_custom_parameters=False,
                        force=False,
                        logger=ctx.logger,
                    )
                except StartWorkflowFailed as err:
                    ctx.logger.error(
                        '{deployment} failed to start workflow: {err}'.format(
                            deployment=deployment,
                            err=text_type(err),
                        )
                    )
                    if tenant not in problem_deployments:
                        problem_deployments[tenant] = []
                    problem_deployments[tenant].append(deployment)

    if targets:
        ctx.logger.info('All monitored instances not listed as problems '
                        'should be re-added to '
                        'nagios within a short time. See individual '
                        'deployments for execution states. '
                        'Problem messages state: '
                        'Tenant <name> had problems starting workflows, '
                        'and list which deployments had these problems. '
                        'If any of these appear you can re-run just those '
                        'deployments by using the only_deployments '
                        'argument.')

        if problem_deployments:
            for tenant in problem_deployments:
                ctx.logger.warn(
                    'Tenant {tenant} had problems starting workflows for '
                    'deployments: {deps}'.format(
                        tenant=tenant,
                        deps=','.join(problem_deployments[tenant]),
                    )
                )
        else:
            ctx.logger.info('No problems were reported starting workflows.')
    else:
        ctx.logger.warn('Nothing needed to be done. Either the combination '
                        'of tenant and deployment filtering left no targets '
                        'or there are no monitored deployments using the '
                        'nagiosrest plugin on the cloudify manager.')


@operation
def start_nagiosrest(ctx):
    ctx.logger.info('Enabling and starting nagios and httpd services')
    services = ['httpd', 'nagiosrest-gunicorn']
    for service in services:
        enable_service(service)
        start_service(service)
