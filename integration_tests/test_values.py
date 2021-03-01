import time

from . import utils


def test_heal_on_threshold_exceeded():
    tenant = 'test_value_breach_heal'
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
        utils.get_examples_blueprint_path('nagios-values.yaml'),
        utils.get_nagios_inputs(config),
        client,
    )
    utils.install_blueprint(
        utils.get_examples_blueprint_path('basevalue.yaml'),
        utils.get_monitored_vms_inputs(config),
        'basevalue',
        client,
    )

    utils.execute_arbitrary_command(
        'basevalue',
        'echo 42 > /tmp/cloudifytestinteger',
        client,
    )

    # Confirm the expected workflow runs
    utils.wait_for_execution_on_deployment('heal',
                                           'basevalue',
                                           client)

    utils.remove_deployment('basevalue', client)
    utils.delete_blueprint('basevalue', client)

    utils.remove_nagios(client)
    utils.delete_plugins(installed_plugins, client)
    utils.remove_config_secrets(client)

    main_client.tenants.delete(tenant)


def test_heal_on_rate_threshold_exceeded():
    tenant = 'test_value_rate_breach_heal'
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
        utils.get_examples_blueprint_path('nagios-values.yaml'),
        utils.get_nagios_inputs(config),
        client,
    )
    utils.install_blueprint(
        utils.get_examples_blueprint_path('basevalue.yaml'),
        utils.get_monitored_vms_inputs(config),
        'basevalue',
        client,
    )

    utils.execute_arbitrary_command(
        'basevalue',
        'echo {time_now}:10 > /tmp/cloudifytestcounter'.format(
            time_now=int(time.time()),
        ),
        client,
    )

    # Confirm the expected workflow runs
    utils.wait_for_execution_on_deployment('heal',
                                           'basevalue',
                                           client)

    utils.remove_deployment('basevalue', client)
    utils.delete_blueprint('basevalue', client)

    utils.remove_nagios(client)
    utils.delete_plugins(installed_plugins, client)
    utils.remove_config_secrets(client)

    main_client.tenants.delete(tenant)
