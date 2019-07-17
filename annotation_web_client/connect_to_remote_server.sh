#!/bin/bash
# This script attempts to read the name of the host node currently running the remote server and then ssh to it,
# forwarding a connection to the server port so that it can be accessed localhost.

current_user=$(whoami)
user=${1:-${current_user}}
echo "Connecting as ${user}."

# Try to read the hostname of the web server from the remote hostname file
# This exploits the fact that the file system is available from the login server
HOSTNAME_FILE="/home/srivbane/shared/caringbridge/data/projects/qual-health-journeys/instance/webclient_hostname_${user}.txt"
msi_hostname=$(ssh ${user}@login.msi.umn.edu "cat ${HOSTNAME_FILE}")

# Connect to the discovered hostname on MSI Mesabi
msi_full_hostname="${msi_hostname}.mesabi.msi.umn.edu" ;
port="${2:-5000}"
echo "Forwarding to port ${port} on ${msi_full_hostname}." ;

login_node="10.31.47.5"
ssh -t ${user}@login.msi.umn.edu -L ${port}:localhost:${port} \
    "ssh -t ${login_node} -L ${port}:localhost:${port} 'ssh -t ${msi_full_hostname} -L ${port}:localhost:${port}' " ;

# The original connection went to the compute node straight from the login node, but it seems like that may
# not be possible following the August 2018 CentOS 7 update on MSI.
#ssh -t ${user}@login.msi.umn.edu -L ${port}:localhost:${port} \
#    "ssh -t ${msi_full_hostname} -L ${port}:localhost:${port} 'cd /home/srivbane/shared/caringbridge/data/projects/qual-health-journeys; bash' " ;


echo "Terminated connection to remote server."
