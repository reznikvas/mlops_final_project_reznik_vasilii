#!/bin/sh
# Закреплённые CLI для Kubernetes 1.32; контрольные суммы официальных релизов.
set -eu
TOOLS_DIR=${TOOLS_DIR:-.artifacts/bin}
mkdir -p "$TOOLS_DIR"
task_tmp=$(mktemp -d)
trap 'rm -rf "$task_tmp"' EXIT
curl -fsSL --retry 3 https://dl.k8s.io/release/v1.32.1/bin/linux/amd64/kubectl -o "$task_tmp/kubectl"
curl -fsSL --retry 3 https://dl.k8s.io/release/v1.32.1/bin/linux/amd64/kubectl.sha256 -o "$task_tmp/kubectl.sha256"
printf '%s  %s\n' "$(cat "$task_tmp/kubectl.sha256")" "$task_tmp/kubectl" | sha256sum -c -
cp "$task_tmp/kubectl" "$TOOLS_DIR/kubectl"
curl -fsSL --retry 3 https://get.helm.sh/helm-v3.18.6-linux-amd64.tar.gz -o "$task_tmp/helm.tgz"
curl -fsSL --retry 3 https://get.helm.sh/helm-v3.18.6-linux-amd64.tar.gz.sha256sum -o "$task_tmp/helm.sha256"
printf '%s  %s\n' "$(cut -d ' ' -f1 "$task_tmp/helm.sha256")" "$task_tmp/helm.tgz" | sha256sum -c -
tar -xzf "$task_tmp/helm.tgz" -C "$task_tmp"
cp "$task_tmp/linux-amd64/helm" "$TOOLS_DIR/helm"
chmod 755 "$TOOLS_DIR/kubectl" "$TOOLS_DIR/helm"
