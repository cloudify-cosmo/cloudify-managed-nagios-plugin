from builtins import range
import time

from . import utils


def test_trap_not_triggered_constraints():
    tenant = 'test_trap_not_triggering_constraints'
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
        utils.get_examples_blueprint_path('nagios-traps.yaml'),
        utils.get_nagios_inputs(config),
        client,
    )
    utils.install_blueprint(
        utils.get_examples_blueprint_path('basetrap.yaml'),
        utils.get_monitored_vms_inputs(config),
        'basetrap',
        client,
    )

    # Send the trap
    utils.execute_arbitrary_command(
        'basetrap',
        'snmptrap -v2c -c testcommunity {ip} "" {oid}'.format(
            ip=utils.get_nagios_internal_ip(client),
            oid='.1.3.6.1.4.1.52312.0.0.1',
        ),
        client,
    )

    # We should see a log entry stating that there was no reaction within 5
    # seconds
    saw_no_reaction = False
    for check in range(5):
        result = utils.execute_arbitrary_command(
            'nagios',
            'sudo tail -n10 /var/log/nagios/notify_cloudify.log '
            '| grep "No reaction"',
            client,
        )
        if result['status'] == 0:
            saw_no_reaction = True
            break
        time.sleep(1)
    assert saw_no_reaction

    utils.remove_deployment('basetrap', client)
    utils.delete_blueprint('basetrap', client)

    utils.remove_nagios(client)
    utils.delete_plugins(installed_plugins, client)
    utils.remove_config_secrets(client)

    main_client.tenants.delete(tenant)


def test_trap_triggers_scale_down():
    tenant = 'test_trap_triggers_scale_down'
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
        utils.get_examples_blueprint_path('nagios-traps.yaml'),
        utils.get_nagios_inputs(config),
        client,
    )
    utils.install_blueprint(
        utils.get_examples_blueprint_path('basetrap.yaml'),
        utils.get_monitored_vms_inputs(config),
        'basetrap',
        client,
    )

    utils.execute(
        'basetrap',
        'scale',
        client,
        parameters={
            'scalable_entity_name': 'base_trap_host',
            'delta': '+1',
            'scale_compute': True,
        },
    )

    # Send the trap
    utils.execute_arbitrary_command(
        'basetrap',
        'snmptrap -v2c -c testcommunity {ip} "" {oid}'.format(
            ip=utils.get_nagios_internal_ip(client),
            oid='.1.3.6.1.4.1.52312.0.0.1',
        ),
        client,
    )

    # Confirm the expected workflow runs
    utils.wait_for_execution_on_deployment('scale',
                                           'basetrap',
                                           client)

    utils.remove_deployment('basetrap', client)
    utils.delete_blueprint('basetrap', client)

    utils.remove_nagios(client)
    utils.delete_plugins(installed_plugins, client)
    utils.remove_config_secrets(client)

    main_client.tenants.delete(tenant)


def test_external_trap_triggers_heal():
    tenant = 'test_external_trap_triggers_heal'
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
        utils.get_examples_blueprint_path('nagios-traps.yaml'),
        utils.get_nagios_inputs(config),
        client,
    )
    utils.install_blueprint(
        utils.get_examples_blueprint_path('basetrap.yaml'),
        utils.get_monitored_vms_inputs(config),
        'basetrap',
        client,
    )

    # Send the trap
    utils.execute_arbitrary_command(
        'nagios',
        'snmptrap -v2c -c testcommunity {ip} "" {oid} '
        '.1.3.6.1.4.1.52312.0.1.1 s "Test message" '
        '.1.3.6.1.4.1.52312.0.1.2 s "The address is {node_address}"'.format(
            ip='localhost',
            oid='.1.3.6.1.4.1.52312.0.0.2',
            node_address=utils.get_first_node_instance_ip(
                node='base_trap_host',
                deployment='basetrap',
                client=client,
            ),
        ),
        client,
    )

    # Confirm the expected workflow runs
    utils.wait_for_execution_on_deployment('heal',
                                           'basetrap',
                                           client)

    utils.remove_deployment('basetrap', client)
    utils.delete_blueprint('basetrap', client)

    utils.remove_nagios(client)
    utils.delete_plugins(installed_plugins, client)
    utils.remove_config_secrets(client)

    main_client.tenants.delete(tenant)
