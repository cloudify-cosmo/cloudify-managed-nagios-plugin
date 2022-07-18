import os
from setuptools import setup


def get_resources():
    paths = []
    for path, _, filenames in os.walk('managed_nagios_plugin/resources'):
        # Strip the leading 'managed_nagios_plugin'
        basepath = path.split('/', 1)[1]
        for filename in filenames:
            paths.append(os.path.join(basepath, filename))
    return paths


setup(
    name='cloudify-managed-nagios-plugin',
    version='1.0.12',
    packages=[
        'managed_nagios_plugin',
        'managed_nagios_plugin.check',
        'managed_nagios_plugin.mib',
        'managed_nagios_plugin.nagios',
        'managed_nagios_plugin.snmp_trap',
        'managed_nagios_plugin.target_type',
    ],
    install_requires=['cloudify-common>=5.2',
                      'Jinja2>=2.7.2',
                      'future'],
    package_data={'managed_nagios_plugin': get_resources()},
)
