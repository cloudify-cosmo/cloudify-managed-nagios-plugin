import os
from setuptools import setup
from setuptools import find_packages


def read(rel_path):
    here = os.path.abspath(os.path.dirname(__file__))
    with open(os.path.join(here, rel_path), 'r') as fp:
        return fp.read()


def get_resources():
    paths = []
    for path, _, filenames in os.walk('managed_nagios_plugin/resources'):
        # Strip the leading 'managed_nagios_plugin'
        basepath = path.split('/', 1)[1]
        for filename in filenames:
            paths.append(os.path.join(basepath, filename))
    return paths


def get_version(rel_file='plugin.yaml'):
    lines = read(rel_file)
    for line in lines.splitlines():
        if 'package_version' in line:
            split_line = line.split(':')
            line_no_space = split_line[-1].replace(' ', '')
            line_no_quotes = line_no_space.replace('\'', '')
            return line_no_quotes.strip('\n')
    raise RuntimeError('Unable to find version string.')


setup(
    name='cloudify-managed-nagios-plugin',
    version=get_version(),
    packages=[
        'managed_nagios_plugin',
        'managed_nagios_plugin.check',
        'managed_nagios_plugin.mib',
        'managed_nagios_plugin.nagios',
        'managed_nagios_plugin.snmp_trap',
        'managed_nagios_plugin.target_type',
    ],
    install_requires=['cloudify-common>=5.0.5',
                      'Jinja2>=2.7.2',
                      'future'],
    package_data={'managed_nagios_plugin': get_resources()},
)
