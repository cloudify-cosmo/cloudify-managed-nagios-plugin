from . import utils


def test_heal_unreachable_node():
    tenant = 'test_base_heal_unreachable_node'
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
        utils.get_examples_blueprint_path('nagios-base.yaml'),
        utils.get_nagios_inputs(config),
        client,
    )
    utils.install_blueprint(
        utils.get_examples_blueprint_path('baseinstance.yaml'),
        utils.get_monitored_vms_inputs(config),
        'baseinstance',
        client,
    )

    utils.execute_arbitrary_command(
        'baseinstance',
        'sudo shutdown -h -t 3 &',
        client,
    )

    # Confirm the expected workflow runs
    utils.wait_for_execution_on_deployment('heal',
                                           'baseinstance',
                                           client,
                                           max_wait_for_start=240)

    utils.remove_deployment('baseinstance', client)
    utils.delete_blueprint('baseinstance', client)

    utils.remove_nagios(client)
    utils.delete_plugins(installed_plugins, client)
    utils.remove_config_secrets(client)

    main_client.tenants.delete(tenant)


def test_reconcile_monitored_nodes():
    tenant = 'test_base_reconcile_monitored_nodes'
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
        utils.get_examples_blueprint_path('nagios-base.yaml'),
        utils.get_nagios_inputs(config),
        client,
    )
    utils.install_blueprint(
        utils.get_examples_blueprint_path('baseinstance.yaml'),
        utils.get_monitored_vms_inputs(config),
        'baseinstance',
        client,
    )

    # We power off the node first. Nagios should be stopped before healing
    # can start.
    # If this is not correct then by the time the nagios heal is finished the
    # Node should also have healed and therefore the test will fail when later
    # waiting for the execution
    utils.execute_arbitrary_command(
        'baseinstance',
        'sudo shutdown -h -t 10 &',
        client,
    )

    utils.execute(
        'nagios',
        'heal',
        client,
        parameters={
            'node_instance_id': utils.get_first_node_instance(
                'nagios', 'nagios', client,
            ),
        },
    )
    utils.delete_nagios_secrets(client)
    utils.update_nagios_secrets(client)

    utils.execute(
        'nagios',
        'execute_operation',
        client,
        parameters={
            'node_ids': ['nagios'],
            'operation': 'cloudify.interfaces.reconcile.monitoring',
            'allow_kwargs_override': True,
        },
    )

    # Confirm the expected workflow runs
    utils.wait_for_execution_on_deployment('heal',
                                           'baseinstance',
                                           client,
                                           max_wait_for_start=120)

    utils.remove_deployment('baseinstance', client)
    utils.delete_blueprint('baseinstance', client)

    utils.remove_nagios(client)
    utils.delete_plugins(installed_plugins, client)
    utils.remove_config_secrets(client)

    main_client.tenants.delete(tenant)
