try:
    from ._compat import text_type
except:
    from _compat import text_type
import os
import pkgutil
import re
import subprocess
import tempfile
import time

import jinja2

try:
    from .constants import (
        OBJECT_DIR_PERMISSIONS,
        OBJECT_OWNERSHIP,
        OBJECT_PERMISSIONS,
        BASE_OBJECTS_DIR,
    )
except:
    from constants import (
        OBJECT_DIR_PERMISSIONS,
        OBJECT_OWNERSHIP,
        OBJECT_PERMISSIONS,
        BASE_OBJECTS_DIR,
    )

def _decode_if_bytes(input):
    if isinstance(input, bytes):
        return input.decode()
    else:
        return input


def yum_install(packages):
    _yum_action('install', packages)


def yum_remove(packages):
    _yum_action('remove', packages)


def _yum_action(action, packages):
    if isinstance(packages, text_type):
        packages = [packages]

    yum_install_command = ['yum', action, '-y']
    yum_install_command.extend(packages)
    run(yum_install_command, sudo=True)


def enable_service(name):
    enable_service_command = ['systemctl', 'enable', name]
    run(enable_service_command, sudo=True)


def disable_service(name):
    disable_service_command = ['systemctl', 'disable', name]
    run(disable_service_command, sudo=True)


def start_service(name):
    start_service_command = ['systemctl', 'start', name]
    run(start_service_command, sudo=True)


def stop_service(name):
    stop_service_command = ['systemctl', 'stop', name]
    run(stop_service_command, sudo=True)


def reload_systemd_configuration():
    run(['systemctl', 'daemon-reload'], sudo=True)


def trigger_nagios_reload(set_group=False):
    # We have the trigger file to avoid reloading too quickly when there are a
    # large amount of changes being made at once, as this can upset nagios.
    reload_trigger_file = '/tmp/nagios_reload_triggered'
    current_time = time.time()
    try:
        with open(reload_trigger_file) as trigger_handle:
            reload_time = float(trigger_handle.read().strip())
    except IOError:
        # The file doesn't exist, that's fine- we can reload nagios then!
        pass
    else:
        # In case the file is lingering from a killed process or similar we
        # check that the reload time is actually in the future
        delay_until_reload = reload_time - current_time
        if delay_until_reload >= 0:
            time.sleep(delay_until_reload + 1)
            # At this point, the other process should've restarted nagios
            # and cleaned up after itself. If it didn't, we'll assume it
            # died.
            if not os.path.exists(reload_trigger_file):
                # The other process cleaned up after itself so it is likely
                # that it also restarted nagios
                return
    # If we reach here then either something else wasn't already restarting
    # nagios, or something else was intending to but didn't
    delay = 15
    if os.path.exists(reload_trigger_file) and set_group:
        # We may not be able to open it if nagiosrest created it but died
        # before removing it
        run(['rm', reload_trigger_file], sudo=True)
    with open(reload_trigger_file, 'w') as trigger_handle:
        trigger_handle.write(text_type(current_time + delay))
    if set_group:
        # Allow nagios rest to delete this file
        run(['chgrp', 'nagios', reload_trigger_file], sudo=True)
        run(['chmod', '660', reload_trigger_file])
    time.sleep(delay)
    try:
        # try reload nagios service
        run(['systemctl', 'reload', 'nagios'], sudo=True)
    except subprocess.CalledProcessError:
        # this means reload failed so we try restart for 3 times
        for _ in range(3):
            try:
                run(['systemctl', 'restart', 'nagios'], sudo=True)
                # if it succeed no need for other trials
                break
            except subprocess.CalledProcessError:
                time.sleep(delay)
    # If we had to set the group then we may also not own the file
    run(['rm', reload_trigger_file], sudo=set_group)


def run(command, sudo=False):
    if sudo:
        command = ['sudo'] + command
    return subprocess.check_output(
        command, stderr=subprocess.STDOUT,
    )


def deploy_file(data, destination,
                ownership=OBJECT_OWNERSHIP,
                permissions=OBJECT_PERMISSIONS,
                sudo=False, template_params=None):
    data = _decode_if_bytes(data)

    if template_params:
        data = jinja2.Template(data).render(**template_params)

    tmpdir = tempfile.mkdtemp(prefix='managed_nagios')
    destination_filename = os.path.split(destination)[-1]
    tmp_file = os.path.join(tmpdir, destination_filename)
    with open(tmp_file, 'w') as tmp_handle:
        tmp_handle.write(data)

    relocate_file(tmp_file, destination, ownership, permissions,
                  sudo)


def relocate_file(source,
                  destination,
                  ownership=OBJECT_OWNERSHIP,
                  permissions=OBJECT_PERMISSIONS,
                  sudo=False):
    run(['mv', source, destination], sudo=sudo)
    run(['chmod', permissions, destination], sudo=sudo)

    if sudo:
        run(['chown', ownership, destination], sudo=True)
    # Apply appropriate selinux context
    run(['restorecon', destination], sudo=sudo)


def deploy_configuration_file(logger, source, destination,
                              template_params=None,
                              validate=True, reload_service=True,
                              sudo=False, use_pkg_data=True):
    destination = os.path.join(BASE_OBJECTS_DIR, destination)

    if use_pkg_data:
        source_data = pkgutil.get_data('managed_nagios_plugin', source)
    else:
        with open(source) as source_handle:
            source_data = source_handle.read()

    deploy_file(source_data, destination,
                OBJECT_OWNERSHIP, OBJECT_PERMISSIONS,
                sudo=sudo, template_params=template_params)

    if validate:
        validate_configuration(
            logger,
            rollback=['rm ', '-f', destination],
            sudo=sudo,
        )

    if reload_service:
        trigger_nagios_reload(set_group=sudo)


def remove_configuration_file(logger, configuration_path,
                              reload_service=True,
                              sudo=False, ignore_missing=False):
    conf_file_name = os.path.split(configuration_path)[-1]
    configuration_path = os.path.join(BASE_OBJECTS_DIR, configuration_path)

    tmpdir = tempfile.mkdtemp()
    temp_location = os.path.join(tmpdir, conf_file_name)

    validate = True
    try:
        run(['mv', configuration_path, temp_location], sudo=sudo)
    except subprocess.CalledProcessError as err:
        if 'No such file or directory' in text_type(err) and ignore_missing:
            validate = False

    if validate:
        validate_configuration(
            logger,
            rollback=['mv', temp_location, configuration_path],
            sudo=sudo,
        )

    # If the configuration is still healthy, we can finalise the deletion
    run(['rm', '-rf', tmpdir], sudo=sudo)

    if reload_service:
        trigger_nagios_reload(set_group=sudo)


def validate_configuration(logger, rollback, sudo=False):
    try:
        run(['nagios', '-v', '/etc/nagios/nagios.cfg'], sudo=sudo)
    except subprocess.CalledProcessError as err:
        logger.warn(
            'Validation failed with output: "{output}". Rolling back change '
            'with: {command}'.format(output=err.output, command=rollback)
        )
        # The new configuration doesn't seem to have worked, kill it and
        # let the error propagate
        run(rollback, sudo=sudo)
        raise


def make_config_subdir(path, sudo=False):
    absolute_path = os.path.join(BASE_OBJECTS_DIR, path)
    run(['mkdir', '-p', absolute_path], sudo=sudo)
    run(['chmod', OBJECT_DIR_PERMISSIONS, absolute_path], sudo=sudo)
    if sudo:
        # Can't change ownership without sudo
        run(['chown', OBJECT_OWNERSHIP, absolute_path], sudo=True)


def get_node_id(instance_id):
    if instance_id.startswith('tenant:'):
        # This is actually a node
        return instance_id.split('node:')[1]
    else:
        return instance_id.rsplit('_', 1)[0]


def download_and_deploy_file_from_blueprint(source,
                                            destination,
                                            ownership,
                                            permissions,
                                            ctx):
    tmp_path = tempfile.mkdtemp()
    tmp_file = os.path.join(tmp_path, 'file')
    ctx.download_resource(
        source,
        tmp_file,
    )

    ctx.logger.info('Moving {tmp} to {dst}'.format(
        tmp=tmp_file,
        dst=destination,
    ))
    relocate_file(
        source=tmp_file,
        ownership=ownership,
        permissions=permissions,
        destination=destination,
        sudo=True,
    )
    run(['rm', '-rf', tmp_path], sudo=True)


def generate_certs(key_path, cert_path, logger):
    raw_ips = _decode_if_bytes(run(['/usr/sbin/ip', 'addr', 'show']))
    logger.debug('Raw IP output: {raw}'.format(raw=raw_ips))
    # Find all inet and inet6 addresses (they are shown in cidr format so
    # there will be a trailing slash, e.g. inet 127.0.0.1/8)
    ip_finder = re.compile('inet6? ([^/]+)')

    ips = ip_finder.findall(raw_ips)
    logger.debug('Found IPs: {ips}'.format(ips=ips))
    ips = [
        ip.split('%')[0]  # Remove IPv6 scopes
        for ip in ips
    ]
    logger.debug('Removed IPv6 scopes: {ips}'.format(ips=ips))

    # Use the first IP as the common name
    # SANs should be more relied upon now anyway, as CNs are being deprecated
    cn = ips[0]
    logger.debug('Using CN: {cn}'.format(cn=cn))

    # Remove any duplicates from ips
    ips = set(ips)
    logger.debug('Deduplicated IPs: {ips}'.format(ips=ips))

    metadata_items = ['IP:{0},DNS:{0}'.format(x) for x in ips]
    cert_metadata = '{0},DNS:localhost'.format(
        ','.join(metadata_items))
    logger.debug('Using certificate metadata: {0}'.format(cert_metadata))

    deploy_file(
        pkgutil.get_data('managed_nagios_plugin',
                         'resources/base_configuration/cert_metadata'),
        '/etc/nagios/cert_metadata',
        ownership='root.nagios',
        permissions='440',
        sudo=True,
        template_params={
            'cn': cn,
            'metadata': cert_metadata,
        },
    )

    # We precreate the key with appropriately restrictive permissions because
    # openssl will otherwise happily expose the key to everyone on the system
    # if the default umask does
    run(['touch', key_path], sudo=True)
    run(['chown', 'root.root', key_path], sudo=True)
    run(['chmod', '400', key_path], sudo=True)

    run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048',
         '-keyout', key_path, '-out', cert_path,
         '-days', '36500', '-batch', '-nodes', '-subj',
         '/CN={0}'.format(cn), '-config', '/etc/nagios/cert_metadata'
         ], sudo=True)
