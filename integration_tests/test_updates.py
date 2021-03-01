import time

from . import utils


def test_adding_and_updating_target_types():
    tenant = 'test_adding_and_updating_target_types'
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
        utils.get_examples_blueprint_path('nagios-update-1.yaml'),
        utils.get_nagios_inputs(config),
        client,
    )

    # Confirm we currently have no target types
    nodes = [item['type'] for item in client.nodes.list(_include=['type'])]
    assert 'cloudify.nagios.nodes.TargetType' not in nodes

    # We don't yet have the target type we need, so let's add it
    client.blueprints.upload(
        path=utils.get_examples_blueprint_path('nagios-update-2.yaml'),
        entity_id='nagiosupdate2',
    )
    client.deployment_updates.update_with_existing_blueprint(
        deployment_id='nagios',
        blueprint_id='nagiosupdate2',
    )

    # Now that we have the target type we need, we can install our test node
    utils.install_blueprint(
        utils.get_examples_blueprint_path('baseupdate.yaml'),
        utils.get_monitored_vms_inputs(config),
        'baseupdate',
        client,
    )

    # Now we will set the test integer to return a higher value
    utils.execute_arbitrary_command(
        'baseupdate',
        'echo 10 > /tmp/cloudifytestinteger',
        client,
    )

    # Allow time for the heal to start running if there is a problem
    time.sleep(60)

    # ...and then update the check threshold so that the check can actually run
    client.blueprints.upload(
        path=utils.get_examples_blueprint_path('nagios-update-3.yaml'),
        entity_id='nagiosupdate3',
    )
    update = client.deployment_updates.update_with_existing_blueprint(
        deployment_id='nagios',
        blueprint_id='nagiosupdate3',
        reinstall_list=[utils.get_first_node_instance(
            'base_update_instance',
            'nagios',
            client,
        )],
    )
    utils.wait_for_execution(update['execution_id'], client)

    # Reconcile because updated target types have to be re-created
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
    # If the workflow already ran then it will already have healed so we won't
    # see it run again now.
    utils.wait_for_execution_on_deployment('heal',
                                           'baseupdate',
                                           client)

    utils.remove_deployment('baseupdate', client)
    utils.delete_blueprint('baseupdate', client)

    utils.remove_nagios(client)
    utils.delete_blueprint('nagiosupdate2', client)
    utils.delete_blueprint('nagiosupdate3', client)
    utils.delete_plugins(installed_plugins, client)
    utils.remove_config_secrets(client)

    main_client.tenants.delete(tenant)
