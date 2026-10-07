#!/bin/sh
# Запускается из каталога релиза. Registry password приходит исключительно stdin.
set -eu
task_registry_config=$(mktemp -d /tmp/ecom-registry.XXXXXX)
trap 'sudo rm -rf "$task_registry_config"' EXIT
sudo docker --config "$task_registry_config" login "$1" --username "$2" --password-stdin
sudo docker --config "$task_registry_config" compose --env-file "$3" --env-file release.env \
  -f mlops/deploy/docker-compose.yml pull
sudo docker --config "$task_registry_config" compose --env-file "$3" --env-file release.env \
  -f mlops/deploy/docker-compose.yml up -d --wait --wait-timeout 180
