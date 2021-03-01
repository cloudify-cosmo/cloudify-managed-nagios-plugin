import hashlib
import os

from managed_nagios_plugin.cloudify_utils import (
    get_relationship_target,
)
from managed_nagios_plugin.constants import (
    BASE_OBJECTS_DIR,
)
from managed_nagios_plugin.utils import (
    deploy_configuration_file,
    make_config_subdir,
)


def get_check_configuration_destination(target_type, name):
    return 'checks/{target_type}/{name}.cfg'.format(
        target_type=hashlib.md5(target_type.encode('utf-8')).hexdigest(),
        name=hashlib.md5(name.encode('utf-8')).hexdigest(),
    )


def get_check_basedir(target_type):
    return os.path.join(BASE_OBJECTS_DIR, 'checks',
                        hashlib.md5(target_type.encode('utf-8')).hexdigest())


def create_check(logger, check_type, target_type, name, params):
    check_path = get_check_configuration_destination(target_type, name)
    check_basedir = os.path.dirname(check_path)
    make_config_subdir(check_basedir, sudo=True)

    deploy_configuration_file(
        logger,
        source='resources/{check_type}.template'.format(
            check_type=check_type,
        ),
        destination=check_path,
        template_params=params,
        reload_service=False,
        sudo=True,
    )


def get_target_type(ctx):
    target = get_relationship_target(
        ctx,
        target_relation_type='check_for_target_type',
        no_target_error=(
            'Checks must be connected to a TargetType with relationship type '
            '{target_relation_type}'
        ),
    )
    return target.node.properties['name']
