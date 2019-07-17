#!/bin/bash
# This script starts the client using the built-in flask webserver
# It takes a single optional argument: the port to run the server on

if [ ! -d "./instance" ]; then
    echo "Expected instance directory does not exist.";
    exit 1;
fi

HOST=$(hostname)
USER=$(whoami)
HOST_FILENAME="instance/webclient_hostname_${USER}.txt"
echo ${HOST} > ${HOST_FILENAME}
echo "Host information cached to '${HOST_FILENAME}'."

port=${1:-5000}
echo "Will execute on port ${port}."

export FLASK_APP="annotation_web_client"
export FLASK_ENV="development"
export FLASK_RUN_PORT=${port}
flask run --port ${port}
