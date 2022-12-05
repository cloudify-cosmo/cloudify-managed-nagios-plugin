# Preparation
See README for necessary preparation steps.
It is recommended that each set of examples be run only after cleaning up any previous examples.

# Update examples
All examples in this section require a deployed nagios server
This can be accomplished using:
`helper_scripts/deploy_nagios update-1`
# Cleaning up:
When you wish to remove nagios, you should clear all test nodes and then run the following command.
It is recommended that this is done after uninstalling all of these examples and before trying other examples.
```
helper_scripts/remove_nagios
cfy blueprints delete nagios
cfy blueprints delete nagiosupdate-2
```

#1 Adding a new target type example
WARNING: Both update examples are designed to be run one after the other
This demonstrates adding a new target type to nagios
We can't have a monitored node yet because we have no target types
So we'll first add a target type, by uploading a blueprint with one we want:

`cfy blueprints upload -b nagiosupdate-2 blueprints/nagios-update-2.yaml`

And now we'll add the target type by updating the deployment
As we're only adding a target type, rather than changing anything associated with an
existing one, we don't need to do anything else with the nagios deployment

`cfy deployments update -b nagiosupdate-2 nagios --skip-drift-check`

Now we can deploy a monitored instance

`cfy install -b baseupdate -d baseupdate -i nagios-blueprint-inputs.yaml blueprints/base-update.yaml`

And we'll set the monitored value
```
touch cert.pem
cfy deployment outputs baseupdate | sed -ne '/-----BEGIN RSA/,$ p' | sed 's/.*Value: //' | awk '{ print }' >> cert.pem
chmod 600 cert.pem
ssh -o StrictHostKeyChecking=no centos@$(cfy deployment outputs baseupdate | grep -A2 "public_address" | grep Value | awk '{ print $2 }') -i cert.pem echo 10 '>' /tmp/cloudifytestinteger
```
But there will be no reaction because the threshold is incorrect
You should now proceed to the second example to update the threshold

# 2 Updating existing check thresholds
WARNING: You MUST run the previous example before this one.
This demonstrates updating a check for an already existing target type, e.g. to adapt
to changing requirements.
Now that we've realised that the threshold is wrong, we'll need to update the check:

`cfy blueprints upload -b nagiosupdate-3 blueprints/nagios-update-3.yaml`

Next we need to update the deployment. Because the target type aggregates checks, the
deployment update will not automatically reinstall the specific target type, so we must
tell it to do this:

`cfy deployments update nagios -b nagiosupdate-3 --force-reinstall -r $(cfy node-instances list | grep base_update_instance | awk '{ print $2 }') --skip-drift-check`

After the target type is updated, it will have lost the associated targets so we must reconcile
(see BASE_EXAMPLES for a reconcile example):

`cfy executions start -d nagios -p '{"node_ids": ["nagios"],"operation": "cloudify.interfaces.reconcile.monitoring","allow_kwargs_override": true}' execute_operation`

And shortly, the monitoring should detect that the threshold is exceeded and heal

`for i in {1..60}; do if ! cfy executions list | grep heal | grep started | grep baseupdate ; then sleep 2; else break; fi; done; cfy events list --tail -e $(cfy executions list | grep heal | grep started | awk '{ print $2 }')`

Cleaning up
`cfy uninstall baseupdate`

Don't forget to run the nagios cleanup before you try another example


#all steps:
```
helper_scripts/deploy_nagios update-1

cfy blueprints upload -b nagiosupdate-2 blueprints/nagios-update-2.yaml

cfy deployments update -b nagiosupdate-2 nagios --skip-drift-check

cfy install -b baseupdate -d baseupdate -i nagios-blueprint-inputs.yaml blueprints/base-update.yaml

touch cert.pem

cfy deployment outputs baseupdate | sed -ne '/-----BEGIN RSA/,$ p' | sed 's/.*Value: //' | awk '{ print }' >> cert.pem

chmod 600 cert.pem

ssh -o StrictHostKeyChecking=no centos@$(cfy deployment outputs baseupdate | grep -A2 "public_address" | grep Value | awk '{ print $2 }') -i cert.pem echo 10 '>' /tmp/cloudifytestinteger

cfy blueprints upload -b nagiosupdate-3 blueprints/nagios-update-3.yaml

cfy deployments update nagios -b nagiosupdate-3 --force-reinstall -r $(cfy node-instances list | grep base_update_instance | awk '{ print $2 }') --skip-drift-check

cfy executions start -d nagios -p '{"node_ids": ["nagios"],"operation": "cloudify.interfaces.reconcile.monitoring","allow_kwargs_override": true}' execute_operation

for i in {1..60}; do if ! cfy executions list | grep heal | grep started | grep baseupdate ; then sleep 2; else break; fi; done; cfy events list --tail -e $(cfy executions list | grep heal | grep started | awk '{ print $2 }')
```