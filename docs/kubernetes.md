# Инференс и мониторинг в Kubernetes

Нативный Deployment/Service; KServe — альтернатива из задания.
Модель и processed-версия общие с вариантом на ВМ.

## Состав

- `mlops/deploy/k8s/deployment.yml`: init-контейнер скачивает модель и lookup из S3,
  проверяет SHA256 и версию. API читает общий `emptyDir` без доступа к S3 credentials.
- `service.yml`: ClusterIP `ecom:8000`; внешний доступ через port-forward.
- `mlops/grafana/chart`: Prometheus, Loki, Grafana, Alloy; без CRD и cluster-wide RBAC.
- `scripts/deploy_k8s.py`: проверка digest → Secrets → манифесты → rollout → Helm → V2 smoke.

Контейнеры работают без root и повышения привилегий. Только Alloy получает
ServiceAccount token и Role для чтения Pod/логов своего namespace; собирает логи API.
Secret `ecom-s3` доступен только init-контейнеру, `ecom-grafana` — Grafana.

Квота: requests 500m CPU / 4Gi, limits 2 CPU / 8Gi; используются 300m / 1664Mi
и 1700m / 3328Mi соответственно. Три PVC занимают 4Gi из 5Gi.
Prometheus хранит до 24 часов или 700MB. Одна реплика, Recreate с перерывом;
NodePort/LoadBalancer запрещены, доступ — port-forward.

## Локальное развёртывание

Kubeconfig: `.secrets/kubeconfig`, права 600, доступ к выданному namespace.
CLI: kubectl 1.32.1 для сервера 1.32.1, Helm 3.18.6; установщик проверяет SHA256.

```bash
sh scripts/install_k8s_tools.sh
export PATH="$PWD/.artifacts/bin:$PATH"
export KUBECONFIG="$PWD/.secrets/kubeconfig"
export KUBE_NAMESPACE="$(kubectl config view --minify -o 'jsonpath={.contexts[0].context.namespace}')"
set -a
. .secrets/s3.env
. .secrets/release.env
set +a
export GRAFANA_PASSWORD="$(cat .secrets/grafana_password)"
uv run --no-sync python -m scripts.deploy_k8s
unset GRAFANA_PASSWORD
```

`APP_IMAGE` — digest образа с V2; модель — `MODEL_VERSION`/`MODEL_MANIFEST_KEY`.
Manual job `deploy_k8s` получает digest от `save`, выполняет rollout и HTTP-проверки.
CI Variables перечислены в [README](../README.md#cicd).

## API V2

```bash
kubectl port-forward service/ecom 8080:8000
```

При занятом 8080 используется `28000:8000` с заменой URL. Контрольный запрос на 8080
проверен в изолированном сетевом пространстве Docker: [протокол](evidence/k8s-port8080.json).

В отдельном терминале:

```bash
curl -f http://127.0.0.1:8080/v2/health/live
curl -f http://127.0.0.1:8080/v2/health/ready
curl -f http://127.0.0.1:8080/v2/models/ecom/ready
curl -f http://127.0.0.1:8080/v2/models/ecom
curl -f http://127.0.0.1:8080/v2/models/ecom/infer
curl -f http://127.0.0.1:8080/v2/models/ecom/infer \
  -H 'Content-Type: application/json' \
  -d '{"id":"example","inputs":[{"name":"features","datatype":"INT64","shape":[1,3],"data":[356475,14,3]}]}'
uv run --no-sync python -m scripts.smoke_v2 --url http://127.0.0.1:8080 \
  --output docs/evidence/k8s-api.json
```

Вход: один тензор `features`, INT64, `[N,3]`, 1 ≤ N ≤ 256; строки содержат
`itemid, hour UTC, weekday`. Выход: `purchase_probability`, FP64, `[N,1]`.
Переданный `id` возвращается в ответе. Проверяются форма, длина, типы, диапазоны и имя модели.
Ошибки с полем `error`: 400 — ввод, 404 — модель/товар, 503 — модель не готова.

[HTTP V2](https://kserve.github.io/website/docs/concepts/architecture/data-plane/v2-protocol)
использует POST. GET — расширение для примера задания: по умолчанию `356475,14,3`,
либо `itemid`, `hour`, `weekday` из query. Оба метода вызывают одну модель.
Доступны health, metadata, inference; gRPC, binary и выбор версии в URL не реализованы.
Обслуживается одна версия; `/predict_purchase`, `/health`, `/docs`, `/metrics` сохранены.

## Мониторинг

Каждая команда выполняется в отдельном терминале с тем же kubeconfig/namespace:

```bash
kubectl port-forward service/ecom-monitoring-prometheus 29090:9090
kubectl port-forward service/ecom-monitoring-loki 23100:3100
kubectl port-forward service/ecom-monitoring-grafana 23000:3000
```

```bash
uv run --no-sync python -m scripts.verify_monitoring \
  --api http://127.0.0.1:8080 --prometheus http://127.0.0.1:29090 \
  --loki http://127.0.0.1:23100 --grafana http://127.0.0.1:23000 \
  --password-file .secrets/grafana_password --output docs/evidence/k8s-monitoring.json
```

Дашборд: `http://127.0.0.1:23000/d/ecom`; пароль — `.secrets/grafana_password`.
Конфиги dashboard/alerts/Loki копируются из варианта на ВМ в `mlops/grafana/chart/files`;
их соответствие проверяет CI job `test_alerts`.

Проверка алерта: scale 0 → firing `EcomUnavailable` → scale 1 → readiness/resolved.
После замены Pod нужен новый port-forward API и повтор smoke; PVC сохраняются.

```bash
uv run --no-sync python -m scripts.check_k8s_alert
```

Недоступность, 5xx и p95 дополнительно проверяет `promtool` в `test_alerts`.
Namespace имеет ограниченный срок жизни. Качество модели и границы проверки —
в [отчёте](report.md#ограничения).
