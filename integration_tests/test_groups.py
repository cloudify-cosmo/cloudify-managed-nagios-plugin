import time
import utils


def test_scale_down_on_group_threshold_breach():
    tenant = 'test_group_breach_scale_down'
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
        utils.get_examples_blueprint_path('nagios-groups.yaml'),
        utils.get_nagios_inputs(config),
        client,
    )
    utils.install_blueprint(
        utils.get_examples_blueprint_path('basegroup1.yaml'),
        utils.get_monitored_vms_inputs(config),
        'basegroup1',
        client,
    )
    utils.install_blueprint(
        utils.get_examples_blueprint_path('basegroup2.yaml'),
        utils.get_monitored_vms_inputs(config),
        'basegroup2',
        client,
    )

    utils.execute_arbitrary_command(
        'basegroup1',
        'echo 2 > /tmp/cloudifytestinteger',
        client,
    )
    utils.execute_arbitrary_command(
        'basegroup1',
        'echo {time_now}:2.0 > /tmp/cloudifytestcounter'.format(
            time_now=int(time.time()),
        ),
        client,
    )

    # Confirm the expected workflow runs
    utils.wait_for_execution_on_deployment('scale',
                                           'basegroup1',
                                           client)

    utils.remove_deployment('basegroup1', client)
    utils.delete_blueprint('basegroup1', client)
    utils.remove_deployment('basegroup2', client)
    utils.delete_blueprint('basegroup2', client)

    utils.remove_nagios(client)
    utils.delete_plugins(installed_plugins, client)
    utils.remove_config_secrets(client)

    main_client.tenants.delete(tenant)

def test_scale_up_on_group_threshold_breach():
    tenant = 'test_group_breach_scale_up'
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
        utils.get_examples_blueprint_path('nagios-groups.yaml'),
        utils.get_nagios_inputs(config),
        client,
    )
    utils.install_blueprint(
        utils.get_examples_blueprint_path('dummygroup.yaml'),
        utils.get_monitored_vms_inputs(config),
        'dummygroup',
        client,
    )

    # Confirm the expected workflow runs
    utils.wait_for_execution_on_deployment('scale',
                                           'dummygroup',
                                           client)

    utils.remove_deployment('dummygroup', client)
    utils.delete_blueprint('dummygroup', client)

    utils.remove_nagios(client)
    utils.delete_plugins(installed_plugins, client)
    utils.remove_config_secrets(client)

    main_client.tenants.delete(tenant)


def test_scale_down_on_metagroup_threshold_breach():
    tenant = 'test_metagroup_breach_scale_down'
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
        utils.get_examples_blueprint_path('nagios-groups.yaml'),
        utils.get_nagios_inputs(config),
        client,
    )
    utils.install_blueprint(
        utils.get_examples_blueprint_path('basemetagroup1.yaml'),
        utils.get_monitored_vms_inputs(config),
        'basemetagroup1',
        client,
    )
    utils.install_blueprint(
        utils.get_examples_blueprint_path('basemetagroup2.yaml'),
        utils.get_monitored_vms_inputs(config),
        'basemetagroup2',
        client,
    )

    utils.execute_arbitrary_command(
        'basemetagroup2',
        'echo {time_now}:0 > /tmp/cloudifytestcounter'.format(
            time_now=int(time.time()),
        ),
        client,
    )

    # Confirm the expected workflow runs
    utils.wait_for_execution_on_deployment('scale',
                                           'basemetagroup1',
                                           client)

    utils.remove_deployment('basemetagroup1', client)
    utils.delete_blueprint('basemetagroup1', client)
    utils.remove_deployment('basemetagroup2', client)
    utils.delete_blueprint('basemetagroup2', client)

    utils.remove_nagios(client)
    utils.delete_plugins(installed_plugins, client)
    utils.remove_config_secrets(client)

    main_client.tenants.delete(tenant)


def test_groups_do_not_collide():
    tenant = 'test_groups_do_not_collide'
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
        utils.get_examples_blueprint_path('nagios-groups-nocollide.yaml'),
        utils.get_nagios_inputs(config),
        client,
    )
    utils.install_blueprint(
        utils.get_examples_blueprint_path('basegroup-nocollide.yaml'),
        utils.get_monitored_vms_inputs(config),
        'basegroup-nocollide',
        client,
    )

    attempt = 0
    counter_result = 'no checks'
    # Until the dependent checks have run there will be a response indicating
    # that there are "no checks associated"
    while 'no checks' in counter_result:
        # Wait up to a 30 seconds (this should be about twice as long as is
        # needed)
        assert attempt < 10, 'Timed out waiting for counter check'
        time.sleep(3)
        counter_result = utils.execute_arbitrary_command(
            'nagios',
            'sudo /usr/lib64/nagios/plugins/check_group_aggregate '
            '--approach="arithmetic_mean" --tenant="{tenant}" '
            '--group-instance="crossdeploymentcountergroup" '
            '--unknown="ignore" '
            '--group-type="Test check group counter"'.format(
                tenant=tenant,
            ),
            client,
        )['output']
        attempt += 1
    # This should be a reasonably large number
    assert int(get_check_value(counter_result)) > 100000

    attempt = 0
    value_result = 'no checks'
    # Until the dependent checks have run there will be a response indicating
    # that there are "no checks associated"
    while 'no checks' in value_result:
        # Wait up to a 30 seconds (this should be about twice as long as is
        # needed)
        assert attempt < 10, 'Timed out waiting for value check'
        time.sleep(3)
        value_result = utils.execute_arbitrary_command(
            'nagios',
            'sudo /usr/lib64/nagios/plugins/check_group_aggregate '
            '--approach="arithmetic_mean" --tenant="{tenant}" '
            '--group-instance="crossdeploymentvaluegroup" --unknown="ignore" '
            '--group-type="Test check group value"'.format(
                tenant=tenant,
            ),
            client,
        )['output']
        attempt += 1
    assert int(get_check_value(value_result)) == 0

    utils.remove_deployment('basegroup-nocollide', client)
    utils.delete_blueprint('basegroup-nocollide', client)

    utils.remove_nagios(client)
    utils.delete_plugins(installed_plugins, client)
    utils.remove_config_secrets(client)

    main_client.tenants.delete(tenant)


def get_check_value(output):
    # Output should look like:
    # GROUP OK - 385188392.0 | <perfdata>
    output = output.split('|')[0]
    output = output.split('-')[1]
    return float(output.strip())
