#!/bin/sh
# Доставка конкретной пары образ/модель; секреты не передаются аргументами SSH.
set -eu
case "$MODEL_VERSION" in *[!a-zA-Z0-9._-]*|'') exit 2;; esac
case "$MODEL_MANIFEST_KEY" in *[!a-zA-Z0-9/._-]*|'') exit 2;; esac
case "$APP_IMAGE" in *[!a-zA-Z0-9/:@._-]*|'') exit 2;; esac
task_release="ecom-release-$CI_COMMIT_SHA"
ssh "$DEPLOY_USER@$DEPLOY_HOST" "mkdir -p '$task_release'"
tar -cf - mlops/deploy mlops/grafana scripts/deploy_on_vm.sh | ssh "$DEPLOY_USER@$DEPLOY_HOST" "tar -xf - -C '$task_release'"
{
  printf 'APP_IMAGE=%s\nMODEL_VERSION=%s\nMODEL_MANIFEST_KEY=%s\n' "$APP_IMAGE" "$MODEL_VERSION" "$MODEL_MANIFEST_KEY"
  printf 'S3_ENV_FILE=/home/%s/ecom-secrets/s3.env\n' "$DEPLOY_USER"
} | ssh "$DEPLOY_USER@$DEPLOY_HOST" "cat > '$task_release/release.env'"
# Постоянные s3.env и monitoring.env создаются на ВМ отдельно, с chmod 600.
# Короткоживущий job token передаётся только stdin, временный Docker config удаляется.
printf '%s' "$CI_REGISTRY_PASSWORD" | ssh "$DEPLOY_USER@$DEPLOY_HOST" "cd '$task_release' && sh scripts/deploy_on_vm.sh '$CI_REGISTRY' '$CI_REGISTRY_USER' '/home/$DEPLOY_USER/ecom-secrets/monitoring.env'"
ssh "$DEPLOY_USER@$DEPLOY_HOST" 'curl --fail --retry 10 --retry-connrefused --retry-delay 3 http://127.0.0.1:8000/health'
ssh "$DEPLOY_USER@$DEPLOY_HOST" 'curl --fail "http://127.0.0.1:8000/predict_purchase?itemid=356475&hour=14&weekday=3"'
