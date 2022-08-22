# We are putting the pass_persist script in /tmp, which means we have to make selinux permissive
# This is NOT suitable for production use, where it should go in a more appropriate location that won't upset selinux
ctx download-resource scripts/cloudifytestpasspersist /tmp/cloudifytestpasspersist
sudo chown root. /tmp/cloudifytestpasspersist
sudo chmod 550 /tmp/cloudifytestpasspersist
sudo setenforce 0

sudo yum install -y net-snmp-utils net-snmp
sudo systemctl stop snmpd
echo "syslocation Unknown
syscontact Root <root@localhost>
dontLogTCPWrappersConnects yes
view CloudifyMonitoringView included .1.3.6.1.4.1.2021
view CloudifyMonitoringView included .1.3.6.1.4.1.52312.0.2
rouser cloudify_monitoring priv -V CloudifyMonitoringView
pass_persist .1.3.6.1.4.1.52312.0 /tmp/cloudifytestpasspersist" | sudo tee /etc/snmp/snmpd.conf
echo "createUser cloudify_monitoring SHA snmpnagiostestauth AES snmpnagiostestpriv" | sudo tee -a /var/lib/net-snmp/snmpd.conf
sudo systemctl start snmpd
sudo systemctl enable snmpd
