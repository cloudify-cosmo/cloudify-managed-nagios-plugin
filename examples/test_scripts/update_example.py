import os
import time
import json
import retrying

from fabric import Connection
from subprocess import check_output
from tempfile import NamedTemporaryFile


def get_json_result(command: str):
    command = command + ' --json'
    text = check_output(command.split())
    return json.loads(text)


def get_node(node_id: str, dep_id: str):
    return get_json_result('cfy nodes get {} -d {}'.format(node_id, dep_id))


def upload_blueprint(blueprint_path: str, blueprint_name=None):
    if blueprint_name:
        return check_output('cfy blueprints upload -b {} {}'.format(
            blueprint_name, blueprint_path).split())
    else:
        return check_output('cfy blueprints upload {}'.format(
            blueprint_path).split())


def create_deployment(blueprint_id: str, deployment_name: str, inputs=None):
    if inputs:
        return check_output('cfy deployments create -b {} -i {} {}'.format(
            blueprint_id, inputs, deployment_name).split())
    else:
        return check_output('cfy deployments create -b {} {}'.format(
            blueprint_id, deployment_name).split())


def execute_workflow(deployment_id: str, workflow: str, params=None):
    if params:
        return check_output('cfy executions start -d {} -p {} {}'.format(
            deployment_id, params, workflow).split())
    else:
        return check_output('cfy executions start -d {} {}'.format(
            deployment_id, workflow).split())


def get_output_value(deployment_id: str, filed_name: str) -> str:
    output_json = get_json_result("cfy deployments outputs {}".format(
        deployment_id))
    return output_json[filed_name]['value']


def add_output_secret(deployment_id: str, filed_name: str, secret_name: str):
    secret = get_output_value(deployment_id, filed_name)
    return check_output("cfy secrets create -s {} {}".format(
        secret, secret_name).split())


def add_key_secret(deployment_id: str, filed_name: str, secret_name: str):
    secret = get_output_value(deployment_id, filed_name)
    with open("temp.txt", "xt") as f:
        f.write("{}".format(secret))
        f.close()
    val = check_output("cfy secrets create -f temp.txt {}".format(
        secret_name).split())
    os.remove("temp.txt")
    return val


def update_deployment(blueprint_id: str, deployment_id: str, extra_flags=" "):
    return check_output('cfy deployments update -b {} {} {}'.format(
        blueprint_id, deployment_id, extra_flags).split())


def create_key_file(deployment_id: str,
                    filed_name: str,
                    key_file_name: str) -> str:
    key = get_output_value(deployment_id, filed_name)
    with open(key_file_name, "xt") as f:
        f.write("{}".format(key))
        f.close()
    return check_output("chmod 600 {}".format(key_file_name).split())


def delete_key_file(key_file_name: str) -> str:
    os.remove(key_file_name)


def alter_cloudifytestinteger(deployment_id: str,
                              filed_name: str,
                              key_file_name: str):
    create_key_file(deployment_id, filed_name, key_file_name)
    ip = get_output_value(deployment_id, "public_address")
    c = Connection(
        host=ip,
        user="centos",
        connect_kwargs={
            "key_filename": key_file_name
        },
    )
    c.run("echo 10 > /tmp/cloudifytestinteger")
    c.close()
    delete_key_file(key_file_name)


def get_node_instance(node_id: str, dep_id: str) -> str:
    return get_json_result('cfy nodes get {} -d {}'.format(
        node_id, dep_id))['instances'][0]


def third_nagios_blueprint_update(node_id, deployment_id, blueprint_id):
    node = get_node_instance(node_id, deployment_id)
    extra_flags = " --force-reinstall -r {} --skip-drift-check".format(node)
    return update_deployment(blueprint_id, deployment_id, extra_flags)


def trigger_heal(deployment_id, workflow_id):
    params_dict = {"node_ids": ["nagios"],
                   "operation": "cloudify.interfaces.reconcile.monitoring",
                   "allow_kwargs_override": True}
    with NamedTemporaryFile() as outfile:
        outfile.write(json.dumps(params_dict).encode())
        outfile.flush()
        command = 'cfy executions start {} -d {} -p {}'.format(workflow_id,
                                                               deployment_id,
                                                               outfile.name)
        check_output(command.split())


@retrying.retry(wait_fixed=2000, stop_max_attempt_number=120)
def validate_heal(deployment_id):
    a = get_json_result("cfy executions list --json")
    assert (a[-1]['workflow_id'] in ['heal'] and \
            a[-1]['status'] in ['started'] and \
            a[-1]['deployment_id'] == deployment_id)
    print("healing, logs will be fetched once heal is done")
    return check_output("cfy events list --tail -e {}".format(
        a[-1]['id']).split())


if __name__ == '__main__':
    ### create the nagios machine
    upload_blueprint("blueprints/nagios-update-1.yaml", "nagios")
    create_deployment("nagios", "nagios", "nagios-blueprint-inputs.yaml")
    execute_workflow("nagios", "install")

    ### add secrets
    add_output_secret("nagios", "internal_address", "nagiosrest_address")
    add_output_secret("nagios", "nagios_web_username", "nagiosrest_user")
    add_output_secret("nagios", "nagios_web_password", "nagiosrest_pass")
    add_key_secret("nagios", "nagios_ssl_certificate",
                   "nagiosrest_certificate")

    ### add 2nd nagios update blueprint and run update
    upload_blueprint("blueprints/nagios-update-2.yaml", "nagiosupdate-2")
    update_deployment("nagiosupdate-2", "nagios", "--skip-drift-check")

    ### deploy monitored vm
    upload_blueprint("blueprints/base-update.yaml", "baseupdate")
    create_deployment("baseupdate", "baseupdate",
                      "nagios-blueprint-inputs.yaml")
    execute_workflow("baseupdate", "install")

    ### change monitored file
    alter_cloudifytestinteger("baseupdate", "key_content", "cert.pem")

    ### add 3rd nagios update blueprint and run update
    upload_blueprint("blueprints/nagios-update-3.yaml", "nagiosupdate-3")
    third_nagios_blueprint_update("base_update_instance", "nagios",
                                  "nagiosupdate-3")

    ### trigger the heal and validate it
    trigger_heal("nagios", "execute_operation")
    validate_heal("baseupdate")
