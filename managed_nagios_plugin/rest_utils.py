import json
import time

import requests

import nagios_utils as nagios


MANAGER_CREDS_PATH = '/etc/nagios/cloudify_manager.json'
MANAGER_CONFIG_PATH = '/etc/nagios/notify_plugin.cfg'
MANAGER_CERT_PATH = '/etc/nagios/notify_plugin.crt'
EXECUTION_IN_PROGRESS_STATES = ['pending', 'started']


def get_manager_details(logger):
    manager_config = {}
    logger.debug('Loading manager credentials')
    with open(MANAGER_CREDS_PATH) as config_handle:
        manager_config = json.load(config_handle)
    logger.debug('Loading manager config')
    with open(MANAGER_CONFIG_PATH) as config_handle:
        manager_config.update(json.load(config_handle))

    if not manager_config.get('cluster'):
        manager_config['cluster'] = manager_config['rest_host']

    logger.debug('Generating base URLs for manager(s)')
    base_urls = []
    for host in manager_config['cluster']:
        base_urls.append('https://{address}:{port}'.format(
            address=host,
            port=manager_config['rest_port'],
        ))
    logger.debug('Manager URL(s): {base_urls}'.format(
        base_urls=', '.join(base_urls),
    ))

    username = manager_config['username']
    logger.debug('Using username {user}'.format(user=username))
    password = manager_config['password']

    return base_urls, username, password


def get_instance_details(instance_id):
    tenant, deployment = nagios.get_tenant_and_deployment_for_instance(
        instance_id,
    )
    return tenant, deployment


def run_workflow_for_instance(instance_id, workflow_id, parameters,
                              allow_custom_parameters, force, logger,
                              tenant=None, deployment=None):
    logger.debug(
        'Running workflow for instance {instance}. '
        'Getting instance details.'.format(
            instance=instance_id,
        )
    )
    if not tenant or not deployment:
        tenant, deployment = get_instance_details(instance_id)
    return run_workflow(tenant, deployment, workflow_id, parameters,
                        allow_custom_parameters, force, logger)


def run_workflow(tenant, deployment, workflow_id, parameters,
                 allow_custom_parameters, force, logger):
    logger.info(
        'Running workflow {workflow} on deployment {deployment} for tenant '
        '{tenant}'.format(
            workflow=workflow_id,
            deployment=deployment,
            tenant=tenant,
        )
    )
    request_data = json.dumps({
        'deployment_id': deployment,
        'workflow_id': workflow_id,
        'parameters': parameters,
        'allow_custom_parameters': allow_custom_parameters,
        'force': force,
        'dry_run': False,
    })
    logger.debug('Workflow details: {details}'.format(
        details=request_data,
    ))

    try:
        result = make_request(
            path='/api/v3.1/executions',
            tenant=tenant,
            request_data=request_data,
            request_parameters=None,
            method=requests.post,
            logger=logger,
        )
    except ManagerRequestFailed as err:
        logger.error('Starting workflow failed: {error}'.format(
            error=str(err),
        ))
        raise StartWorkflowFailed(str(err))

    logger.debug('Retrieving ID from result {result}'.format(
        result=result,
    ))
    return tenant, result['id']


def get_execution(tenant, execution_id, logger):
    logger.debug(
        'Retrieving execution {execution} for tenant {tenant}'.format(
            execution=execution_id,
            tenant=tenant,
        )
    )
    try:
        return make_request(
            path='/api/v3.1/executions/{execution_id}'.format(
                execution_id=execution_id,
            ),
            tenant=tenant,
            request_data=None,
            request_parameters=None,
            method=requests.get,
            logger=logger,
        )
    except ManagerRequestFailed as err:
        logger.error('Failed to retrieve execution: {error}'.format(
            error=str(err),
        ))
        raise GetExecutionError(str(err))


def wait_for_execution_success(tenant, execution_id, logger,
                               max_checks=180, check_interval=10):
    logger.debug('Waiting for execution {exc_id}'.format(
        exc_id=execution_id,
    ))
    execution = None
    check = 0
    while check < max_checks:
        logger.debug('Check {num} of {max}'.format(num=check, max=max_checks))
        execution = get_execution(tenant, execution_id, logger)
        logger.debug('Execution state was: {exc}'.format(exc=execution))
        if execution['status'] not in EXECUTION_IN_PROGRESS_STATES:
            logger.debug('Execution is no longer in progress')
            break
        logger.debug('Waiting {interval} for next check'.format(
            interval=check_interval,
        ))
        time.sleep(check_interval)
        check += 1

    if execution['status'] != 'terminated':
        logger.error(
            'Execution state was not terminated. Final execution state was: '
            '{state}, with error output: {error}'.format(
                state=execution['status'],
                error=execution.get('error'),
            )
        )
        logger.debug('Full execution state was: {exc}'.format(exc=execution))
        raise ExecutionDidNotSucceed(
            execution['error'] if execution['status'] == 'failed'
            else 'Final state was {state}'.format(
                state=execution['status'],
            )
        )

    logger.debug('Execution complete, returning')
    return execution


def _get_all(entity):
    return True


def get_entities(entity_type, tenant, properties, logger,
                 include=_get_all):
    logger.debug(
        'Getting entities of type {entity_type}'.format(
            entity_type=entity_type,
        )
    )
    if properties:
        logger.debug('Filtering for {properties}'.format(
            properties=', '.join(properties),
        ))

    results = []
    finished = False
    offset = 0
    size = 1000
    while not finished:
        params = {'_offset': offset, '_size': size}
        logger.debug('Getting {size} results'.format(size=size))
        entities = make_request(
            path='/api/v3.1/{entity_type}'.format(
                entity_type=entity_type,
            ),
            tenant=tenant,
            request_data=None,
            request_parameters=params,
            method=requests.get,
            logger=logger,
        ).get('items', [])
        logger.debug('Got {amount} results'.format(amount=len(entities)))
        if entities:
            logger.debug('Processing entities')
            for entity in entities:
                if not include(entity):
                    continue
                if properties:
                    remove = [
                        prop for prop in entity
                        if prop not in properties
                    ]
                    for item in remove:
                        entity.pop(item)
                results.append(entity)
            offset += size
            logger.debug('Incrementing offset to {new_offset}'.format(
                new_offset=offset,
            ))
        else:
            logger.debug('No more results, returning gathered entities')
            finished = True
    return results


def not_active_manager(result):
    if result.status_code != 400:
        return False
    try:
        return result.json().get('error_code') in (
            'not_cluster_master',
            'removed_from_cluster',
        )
    except ValueError:
        # If the error structure is unexpected, it's not a cluster issue
        return False


class StartWorkflowFailed(Exception):
    pass


class GetExecutionError(Exception):
    pass


class ExecutionDidNotSucceed(Exception):
    pass


class ManagerRequestFailed(Exception):
    pass


class NoHealthyManagers(Exception):
    pass


class BadManagerPath(Exception):
    pass


def make_request(path, tenant, request_data, request_parameters,
                 method, logger):
    base_urls, username, password = get_manager_details(logger)
    logger.debug(
        'Making request with base rest args: base_urls: {base_urls}; '
        'username: {username}; password: {password}; tenant: {tenant}; '
        'path: {path}'.format(
            base_urls=base_urls,
            username=username,
            password='*********',
            tenant=tenant,
            path=path,
        )
    )
    request_headers = {
        'Tenant': tenant,
        'Content-type': 'application/json',
    }
    if not path.startswith('/'):
        message = (
            'Paths for manager should start with a /. '
            'Requested path was {path}'.format(
                path=path,
            )
        )
        logger.error(message)
        raise BadManagerPath(message)
    for base_url in base_urls:
        url = base_url + path
        logger.debug(
            'Making authenticated {call} call to "{url}" with headers: '
            '{headers}; data: {data}, and using certificate '
            '{cert_path}'.format(
                url=url,
                call=method.__name__,
                headers=request_headers,
                data=request_data,
                cert_path=MANAGER_CERT_PATH,
            )
        )
        try:
            result = method(
                url=url,
                headers=request_headers,
                auth=(username, password),
                data=request_data,
                params=request_parameters,
                verify=MANAGER_CERT_PATH,
            )
        except requests.exceptions.ConnectionError:
            # Manager down
            logger.warn('This manager appears to be down, trying next URL')
            continue

        logger.debug('Received response: {result}'.format(result=result))
        if not_active_manager(result):
            logger.warn('Target manager is a replica, trying next URL')
            continue

        if result.status_code < 300:
            logger.debug('Returning healthy response')
            return result.json()
        else:
            message = (
                'Request failed with status code {status}, '
                'and reason: {reason}'.format(
                    status=result.status_code,
                    reason=result.json()['message'],
                )
            )
            logger.error(message)
            raise ManagerRequestFailed(message)

    logger.error('No healthy managers reached')
    raise NoHealthyManagers(
        'No healthy managers were reachable.'
    )
