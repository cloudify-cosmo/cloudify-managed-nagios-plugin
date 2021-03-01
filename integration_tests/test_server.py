from managed_nagios_plugin._compat import text_type
import os
import ssl

from . import utils


INSECURE_PROTOCOLS = {
    'sslv3': {
        'proto': ssl.PROTOCOL_SSLv3,
        'error': 'alert handshake failure',
    },
    'tlsv1': {
        'proto': ssl.PROTOCOL_TLSv1,
        'error': 'alert protocol version',
    },
}


def test_pre_created_certificate():
    tenant = 'test_server_pre_created_certificate'
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
        utils.get_examples_blueprint_path('nagios-precert.yaml'),
        utils.get_nagios_inputs(config),
        client,
    )

    cert_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'examples', 'blueprints', 'ssl', 'example.crt',
    )
    with open(cert_path) as cert_handle:
        expected_cert = cert_handle.read()

    # Check the deployment output has the correct certificate
    outputs = client.deployments.outputs.get('nagios')['outputs']
    assert expected_cert == outputs['nagios_ssl_certificate']

    check_no_insecure_ssl_protos(outputs['external_address'])

    # Check the cert provided by the nagios httpd service matches
    server_cert = ssl.get_server_certificate(
        (outputs['external_address'], 443),
        # This will select the highest supported SSL/TLS version
        ssl.PROTOCOL_SSLv23,
    )
    assert expected_cert == server_cert

    utils.remove_nagios(client)
    utils.delete_plugins(installed_plugins, client)
    utils.remove_config_secrets(client)

    main_client.tenants.delete(tenant)


def test_generated_certificate():
    tenant = 'test_server_generated_certificate'
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
        utils.get_examples_blueprint_path('nagios-gencert.yaml'),
        utils.get_nagios_inputs(config),
        client,
    )

    # Get the certificate from the deployments output
    outputs = client.deployments.outputs.get('nagios')['outputs']
    expected_cert = outputs['nagios_ssl_certificate']

    check_no_insecure_ssl_protos(outputs['external_address'])

    # Check the cert provided by the nagios httpd service matches
    server_cert = ssl.get_server_certificate(
        (outputs['external_address'], 443),
        # This will select the highest supported SSL/TLS version
        ssl.PROTOCOL_SSLv23,
    )
    assert expected_cert == server_cert

    utils.remove_nagios(client)
    utils.delete_plugins(installed_plugins, client)
    utils.remove_config_secrets(client)

    main_client.tenants.delete(tenant)


def check_no_insecure_ssl_protos(address):
    for proto_name, protocol in INSECURE_PROTOCOLS.items():
        try:
            ssl.get_server_certificate((address, 443), protocol['proto'])
            raise AssertionError(
                'An insecure SSL protocol was allowed for connection: '
                '{proto_name}'.format(proto_name=proto_name)
            )
        except ssl.SSLError as err:
            assert protocol['error'] in text_type(err)
