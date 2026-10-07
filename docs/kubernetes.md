# Инференс и мониторинг в Kubernetes

Используется нативный вариант Deployment/Service. KServe — альтернативный способ
развёртывания из задания; установка его контроллера не требуется.
Модель и processed-версия общие с вариантом на ВМ. Обучение для Kubernetes не меняется.

## Состав

- `mlops/deploy/k8s/deployment.yml`: init-контейнер скачивает модель и lookup из S3,
  проверяет SHA256 и версию. API читает общий `emptyDir` без доступа к S3 credentials.
- `service.yml`: ClusterIP `ecom:8000`; внешний доступ через port-forward.
- `mlops/grafana/chart`: Helm-chart Prometheus, Loki, Grafana и Alloy без CRD,
  cluster-wide RBAC и privileged-контейнеров. Alloy читает логи только Pod API
  в текущем namespace через Kubernetes API.
- `scripts/deploy_k8s.py`: проверка digest, создание Secrets из окружения, применение
  манифестов, ожидание rollout, установка Helm-chart, фактические V2 smoke-проверки.

Все контейнеры работают без root и повышения привилегий. ServiceAccount token
смонтирован только в Alloy, с Role для чтения Pod и их логов. Secret `ecom-s3`
передаётся только init-контейнеру; `ecom-grafana` содержит пароль интерфейса.
Образ задаётся по digest, модель — парой `MODEL_VERSION`/`MODEL_MANIFEST_KEY`.

Квота учебного namespace: requests 500m CPU / 4Gi RAM, limits 2 CPU / 8Gi RAM;
NodePort и LoadBalancer запрещены. Запрошено суммарно 300m CPU и 1664Mi RAM,
лимиты — 1700m CPU и 3328Mi RAM. Init-контейнер не работает одновременно с API.
Мониторинг использует три PVC суммарно 4Gi из доступных 5Gi. Prometheus хранит
до 24 часов или 700MB данных. Развёртывание одной реплики использует Recreate:
обновление допускает короткий перерыв и не требует ресурса второй реплики.

## Локальное развёртывание

Kubeconfig хранится в `.secrets/kubeconfig`, права 600. Нужен доступ только
к выданному namespace. Совместимые CLI устанавливаются в каталог проекта:

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

`APP_IMAGE` должен указывать на образ с API V2. Текущая развёрнутая пара фиксируется
в доказательствах проверки. CLI закреплены: kubectl 1.32.1 для сервера 1.32.1,
Helm 3.18.6; загрузки проверяются по SHA256 официальных релизов.

В GitLab требуются protected Variables `KUBE_CONFIG_B64`, `KUBE_NAMESPACE`,
`GRAFANA_PASSWORD`; kubeconfig и пароль — masked/hidden. S3 и модель используют
существующие Variables. Manual job `deploy_k8s` получает digest от `save`, выполняет
rollout и HTTP-проверки. Job `deploy` сохраняет самостоятельный вариант на ВМ.

## API V2

```bash
kubectl port-forward service/ecom 8080:8000
```

Если порт 8080 занят, используется `28000:8000` с соответствующей заменой URL.
В локальном окружении порт 8080 занят другим сервисом.
Запрос на 8080 проверен через port-forward в изолированном
сетевом пространстве Docker: [протокол](evidence/k8s-port8080.json).

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
`id` возвращается в ответе, если передан. Проверяются форма, длина, типы, диапазоны
и имя модели. Ошибки V2 имеют поле `error`: 400 для неверного запроса,
404 для неизвестных модели/товара, 503 для неготовой модели.

[HTTP V2](https://kserve.github.io/website/docs/concepts/architecture/data-plane/v2-protocol)
предусматривает POST для инференса. GET `/v2/models/ecom/infer` — дополнительная
совместимость с примером задания: без параметров обрабатывается контрольная строка
`356475,14,3`; параметры `itemid`, `hour`, `weekday` могут быть заданы в query.
Оба метода используют одну модель; GET является расширением стандартного HTTP V2.
Реализованы HTTP health, metadata и inference; gRPC, бинарные расширения и выбор
версии модели в URL не реализованы. Одновременно обслуживается одна версия.
Прежние `/predict_purchase`, `/health`, `/docs`, `/metrics` сохраняются.

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

Дашборд `http://127.0.0.1:23000/d/ecom` показывает доступность, RPS, latency,
ошибки, распределение вероятностей и логи. Пароль находится в приватном файле.
Конфиги dashboard/alerts/Loki в chart соответствуют варианту на ВМ; после изменения
исходных конфигов требуется обновление копий в `mlops/grafana/chart/files`.

Для контролируемой проверки недоступности Deployment временно масштабируется в 0,
после firing `EcomUnavailable` возвращается в 1. Port-forward API после замены Pod
запускается заново. Обязательна проверка readiness, прогноза и снятия алерта.
Удаление PVC не требуется. Loki и Prometheus сохраняют историю на PVC.

```bash
uv run --no-sync python -m scripts.check_k8s_alert
```

Дополнительно `mlops/deploy/alerts-test.yml` проверяет firing/resolved для
недоступности, 5xx и высокой задержки на синтетических временных рядах.
Проверка выполняется `promtool` в CI job `test_alerts`.

## Границы проверки

Онлайн-точность не вычисляется без фактических покупок. Offline AP/log loss/Brier
сохраняются в manifest модели. Kubernetes не устраняет ограничения исторического
датасета и фиксированного каталога. Namespace и доступы имеют ограниченный срок жизни.
Возобновление ресурсов доступно в учебном тренажёре. Секреты, kubeconfig и модель
не входят в Git.
