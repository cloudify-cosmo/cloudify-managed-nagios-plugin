from builtins import range
import time

from . import utils


def test_scale_down_on_mean_threshold_breach():
    tenant = 'test_aggregate_mean_breach_scale_down'
    config = utils.load_config()
    main_client = utils.get_rest_client_using_config(
        config,
        tenant='default_tenant',
    )

    main_client.tenants.create(tenant)
    client = utils.get_rest_client_using_config(
        config,
        tenant=tenant,
    )

    utils.upload_config_secrets(config, client)
    installed_plugins = utils.upload_required_plugins(client)

    utils.deploy_nagios(
        utils.get_examples_blueprint_path('nagios-aggregates.yaml'),
        utils.get_nagios_inputs(config),
        client,
    )
    utils.install_blueprint(
        utils.get_examples_blueprint_path('baseaggregate.yaml'),
        utils.get_monitored_vms_inputs(config),
        'baseaggregate',
        client,
    )

    utils.execute_arbitrary_command(
        'baseaggregate',
        'echo 42 > /tmp/cloudifytestinteger',
        client,
    )

    # Confirm the expected workflow runs
    utils.wait_for_execution_on_deployment('scale',
                                           'baseaggregate',
                                           client)

    utils.remove_deployment('baseaggregate', client)
    utils.delete_blueprint('baseaggregate', client)

    utils.remove_nagios(client)
    utils.delete_plugins(installed_plugins, client)
    utils.remove_config_secrets(client)

    main_client.tenants.delete(tenant)


def test_abort_on_unreachable():
    tenant = 'test_aggregate_abort_on_unreachable'
    config = utils.load_config()
    main_client = utils.get_rest_client_using_config(
        config,
        tenant='default_tenant',
    )

    main_client.tenants.create(tenant)
    client = utils.get_rest_client_using_config(
        config,
        tenant=tenant,
    )

    utils.upload_config_secrets(config, client)
    installed_plugins = utils.upload_required_plugins(client)

    utils.deploy_nagios(
        utils.get_examples_blueprint_path('nagios-aggregates.yaml'),
        utils.get_nagios_inputs(config),
        client,
    )
    utils.install_blueprint(
        utils.get_examples_blueprint_path('baseaggregate.yaml'),
        utils.get_monitored_vms_inputs(config),
        'baseaggregate',
        client,
    )

    # Turn off SNMP on a node
    utils.execute_arbitrary_command(
        'baseaggregate',
        'sudo service snmpd stop',
        client,
        utils.get_first_node_instance('base_aggregate_host',
                                      'baseaggregate',
                                      client)
    )

    # We should see an UNKNOWN check state within 60 seconds
    saw_unknown_state = False
    for check in range(60):
        result = utils.execute_arbitrary_command(
            'nagios',
            'sudo tail -n10 /var/log/nagios/check_snmp_aggregate.log '
            '| grep UNKNOWN',
            client,
        )
        if result['status'] == 0:
            saw_unknown_state = True
            break
        time.sleep(1)
    assert saw_unknown_state

    utils.remove_deployment('baseaggregate', client)
    utils.delete_blueprint('baseaggregate', client)

    utils.remove_nagios(client)
    utils.delete_plugins(installed_plugins, client)
    utils.remove_config_secrets(client)

    main_client.tenants.delete(tenant)


def test_ignore_unreachable():
    tenant = 'test_aggregate_ignore_unreachable'
    config = utils.load_config()
    main_client = utils.get_rest_client_using_config(
        config,
        tenant='default_tenant',
    )

    main_client.tenants.create(tenant)
    client = utils.get_rest_client_using_config(
        config,
        tenant=tenant,
    )

    utils.upload_config_secrets(config, client)
    installed_plugins = utils.upload_required_plugins(client)

    utils.deploy_nagios(
        utils.get_examples_blueprint_path('nagios-aggregates.yaml'),
        utils.get_nagios_inputs(config),
        client,
    )
    utils.install_blueprint(
        utils.get_examples_blueprint_path('baseaggregate.yaml'),
        utils.get_monitored_vms_inputs(config),
        'baseaggregate',
        client,
    )

    # Turn off SNMP on a node
    utils.execute_arbitrary_command(
        'baseaggregate',
        'sudo service snmpd stop',
        client,
        utils.get_first_node_instance('base_aggregate_host',
                                      'baseaggregate',
                                      client)
    )

    # Then trigger a scale down
    utils.execute_arbitrary_command(
        'baseaggregate',
        'echo {time_now}:0 > /tmp/cloudifytestcounter'.format(
            time_now=int(time.time()),
        ),
        client,
    )

    # Confirm the expected workflow runs
    utils.wait_for_execution_on_deployment(
        'scale',
        'baseaggregate',
        client,
        max_wait_for_start=120,
    )

    utils.remove_deployment('baseaggregate', client)
    utils.delete_blueprint('baseaggregate', client)

    utils.remove_nagios(client)
    utils.delete_plugins(installed_plugins, client)
    utils.remove_config_secrets(client)

    main_client.tenants.delete(tenant)
