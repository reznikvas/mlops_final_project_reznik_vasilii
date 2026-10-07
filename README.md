# E-commerce: вероятность покупки

Сервис оценивает вероятность покупки товара тем же посетителем в течение 24 часов
после просмотра. Вход: `itemid`, час UTC, день недели (0 — понедельник).
Выход: `purchase_probability` из `CatBoostClassifier.predict_proba` и версия модели.
Это оценка по товару и времени, без персональных признаков посетителя.

Test AP **0,0243904**, baseline **0,0111961**. На ВМ и в Kubernetes проверены
инференс, мониторинг и восстановление. [Pipeline №11202](https://mlops.gitlab.yandexcloud.net/s87443/mlops_final_project_reznik_vasilii/-/pipelines/11202): 8 jobs **success**.

[Результаты и версии](docs/report.md) · [Чек-лист](docs/checklist.md) ·
[Эксплуатация](docs/operations.md) · [Kubernetes](docs/kubernetes.md) ·
[Репозиторий](docs/submission.md). Протоколы и скриншоты — в [docs/evidence](docs/evidence).

## Структура

| Каталог / файл | Назначение |
|---|---|
| `src/data.py`, `src/features.py` | Валидация, target, временное разбиение, единые признаки |
| `src/training.py` | Три конфигурации CatBoost, выбор по validation AP |
| `src/storage.py`, `src/loaded_models.py` | S3, SHA256, однократная загрузка модели |
| `src/main.py`, `src/schema.py`, `src/v2.py` | FastAPI, прежний API и HTTP V2, логи, метрики |
| `tests/` | Изолированные unit-тесты |
| `mlops/airflow/` | Airflow 2.11, DAG S3 → S3 |
| `mlops/clearml/` | Эксперименты и выбор модели в ClearML |
| `mlops/deploy/`, `mlops/grafana/` | Инференс, мониторинг и дашборд |
| `mlops/deploy/k8s/`, `mlops/grafana/chart/` | Kubernetes Deployment/Service и Helm-chart мониторинга |
| `scripts/` | Загрузка данных и модели, доставка из CI |

## Окружение и проверки

Python 3.12.13, uv; версии зависимостей закреплены в `uv.lock` и `requirements.txt`.
`requirements.txt` содержит runtime; инструменты качества — группа `dev` в lockfile.

```bash
uv venv --python 3.12.13 .venv
uv sync --frozen
# Альтернатива для runtime: uv pip install -r requirements.txt
uv run --no-sync ruff check .
uv run --no-sync black --check --workers 1 .
uv run --no-sync mypy
uv run --no-sync pytest
```

При отсутствии доступа к общему кэшу uv используется `UV_CACHE_DIR=.cache/uv`.
Unit-тесты не требуют S3, Airflow, ClearML или файла обученной модели.

## Данные и постановка

Четыре исходных файла RetailRocket: `events.csv`, `category_tree.csv`,
`item_properties_part1.csv`, `item_properties_part2.csv`. Две части свойств объединяются.
Сырые данные не хранятся в этом Git-репозитории.

Один уникальный просмотр — одна строка. Target = 1 при покупке того же товара
тем же посетителем **строго после** просмотра и в пределах 24 часов.
Последние 24 часа наблюдений исключены. `merge_asof` находит ближайшую покупку
без размножения строк.

Первые 20% временного диапазона — история для признаков; 20–60% — train,
60–80% — validation, 80–100% — test. Перед границами train/validation исключаются
24 часа, чтобы окна target не пересекали следующую выборку. Seed: 42.

Общий для обучения и API снимок фиксируется **до train**. Признаки: `views`,
`purchases`, `ctr`, `hour`, `weekday`, `categoryid`, `available`. Свойства выбираются
по timestamp из обеих частей; неизвестная категория/доступность — -1.
`ctr` — отношение исторических покупок к просмотрам, а не вероятность API.
Товары вне снимка исключены из offline-оценки и дают 404 в API; каталог не обновляется.

Три конфигурации сравниваются по validation **Average Precision** (AP): PR-метрика
подходит для редких покупок. Test используется только для финальной оценки
победителя: AP, log loss, Brier и калибровка. Baseline — частота покупок на train.

```bash
uv run python prepare_features.py --raw /путь/к/четырём/csv
uv run python train_model.py
uv run python main.py
curl -f http://127.0.0.1:32000/health
curl -f http://127.0.0.1:32000/docs
curl -f 'http://127.0.0.1:32000/predict_purchase?itemid=356475&hour=14&weekday=3'
```

## S3 и происхождение артефактов

Файл `.secrets/s3.env` содержит `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
`S3_BUCKET` (фактически выданный бакет), `S3_ENDPOINT_URL`, `AWS_DEFAULT_REGION`.
Права каталога 700, файлов 600. Префикс `Reznik_Vasilii_project` находится **внутри** бакета.

```bash
set -a
. .secrets/s3.env
set +a
uv run python -m scripts.upload_raw /путь/к/четырём/csv
uv run python prepare_features.py --raw-manifest "$RAW_MANIFEST_KEY" --upload
uv run python train_model.py --upload
```

Выведенный ключ manifest задаётся в `RAW_MANIFEST_KEY`. Под проектным префиксом:
`raw_data/<version>/`, `processed_data/<version>/`, `models/<version>/`.
Manifest публикуется последним: SHA256, схема, параметры, происхождение и границы
выборок. Версия processed зависит от входов, рецепта, кода и библиотек.
При скачивании проверяются SHA256; модель `ranker.pkl` и lookup загружаются одной
версией до готовности API. Pickle допустим только из доверенного проектного S3.

## Airflow

Airflow **2.11.0**, LocalExecutor, PostgreSQL.
Файл `.secrets/services.env` содержит: `AIRFLOW_DB_PASSWORD`, `AIRFLOW_FERNET_KEY`
(Fernet, 32 случайных байта в urlsafe base64), `AIRFLOW_WEB_SECRET`, `GRAFANA_PASSWORD`.

```bash
docker compose --env-file .secrets/services.env -f mlops/airflow/docker-compose.yaml up -d --build
docker compose --env-file .secrets/services.env -f mlops/airflow/docker-compose.yaml exec airflow airflow dags list
```

Интерфейс: `127.0.0.1:8082`; доступ к ВМ выполняется через SSH-туннель.
Standalone создаёт пользователя admin; пароль хранится внутри контейнера в
`/opt/airflow/standalone_admin_password.txt` и исключён из отчётов.
Для S3 требуется Connection `ecom_s3` (тип aws): login = Access Key, password = Secret Key,
extra = JSON с `endpoint_url` и `bucket`. Секрет шифруется Fernet в PostgreSQL.
Возможен `airflow connections import` из временного файла с правами 600;
перед импортом владельцем файла назначается UID 50000, после импорта файл удаляется.

```bash
docker compose --env-file .secrets/services.env -f mlops/airflow/docker-compose.yaml exec airflow \
  airflow dags trigger preprocessing_data --conf "{\"raw_manifest\":\"$RAW_MANIFEST_KEY\"}"
```

DAG: S3 raw → валидация → `src.data.prepare` → S3 processed и manifest.
XCom содержит ключ manifest. Один активный run; те же входы дают тот же префикс.

## ClearML

Адреса сервера и SDK credentials задаются в `~/clearml.conf` либо через переменные
`CLEARML_API_HOST`, `CLEARML_WEB_HOST`, `CLEARML_FILES_HOST`,
`CLEARML_API_ACCESS_KEY`, `CLEARML_API_SECRET_KEY`.

```bash
PYTHONPATH="$PWD" uv run python -m mlops.clearml.clearml_pipeline \
  --processed-manifest "$PROCESSED_MANIFEST_KEY"
```

`PROCESSED_MANIFEST_KEY` — manifest успешного Airflow run. Из одной processed-версии
обучаются три модели; победитель по validation AP оценивается на test и публикуется
в S3 с lookup и manifest. [Local mode](https://clear.ml/docs/latest/docs/references/sdk/automation_controller_pipelinedecorator/)
запускает шаги подпроцессами и регистрирует задачи на сервере; определение Git repo отключено.
Запуск проектного ClearML — в [инструкции эксплуатации](docs/operations.md).

## Docker и ВМ

```bash
DOCKER_BUILDKIT=1 docker build -t ecom-purchase:local .
```

Файл `.secrets/release.env` содержит `APP_IMAGE`, `MODEL_VERSION`, `MODEL_MANIFEST_KEY`,
`S3_ENV_FILE` (абсолютный путь удобнее). Пароль Grafana — в services.env.

```bash
docker compose --env-file .secrets/services.env --env-file .secrets/release.env \
  -f mlops/deploy/docker-compose.yml up -d --wait --wait-timeout 180
curl -f http://127.0.0.1:8000/health
curl -f 'http://127.0.0.1:8000/predict_purchase?itemid=356475&hour=14&weekday=3'
```

`model-init` скачивает модель в volume её версии. API работает без root и S3-ключей,
читает volume read-only, загружает модель один раз на процесс; до загрузки health = 503.
Доставка образа без Registry:

```bash
docker save ecom-purchase:local | gzip > .artifacts/ecom-image.tar.gz
scp .artifacts/ecom-image.tar.gz ubuntu@VM:/home/ubuntu/
ssh ubuntu@VM 'gzip -dc ~/ecom-image.tar.gz | sudo docker load'
```

Каталоги `mlops/deploy`, `mlops/grafana` и приватные env доставляются отдельно по SSH.
Секреты хранятся вне каталога релиза. Откат выполняется выбором предыдущей пары
`APP_IMAGE`/`MODEL_VERSION` и её manifest с повторным запуском `compose up`.
Срок жизни учебной ВМ — 5 часов. Возобновление ресурсов доступно в учебном тренажёре.

## Мониторинг и негативные проверки

`/metrics` экспортирует запросы/статусы, задержку, распределение вероятности и готовность.
Prometheus опрашивает API каждые 10 с; Grafana использует dashboard `ecom`.
Alloy отправляет stdout/stderr `ecom-api` в Loki: itemid, вероятность, версия модели;
для ошибок — тип и статус. Itemid не используется в labels метрик.

Интерфейсы привязаны к loopback ВМ: Grafana 3000, Prometheus 9090, Loki 3100.
Доступ через SSH `-L`. Пароль Grafana хранится в приватном env.
Алерты Prometheus: недоступность 30 с, доля 5xx >5% одну минуту, p95 >1 с две минуты.
Это эксплуатационные пороги, не критерии ML-качества. Внешняя рассылка не настроена.

```bash
curl -i 'http://127.0.0.1:8000/predict_purchase?itemid=-1&hour=14&weekday=3' # 422
curl -i 'http://127.0.0.1:8000/predict_purchase?itemid=999999999&hour=14&weekday=3' # 404
curl -f http://127.0.0.1:8000/metrics
```

Автоматическая сквозная проверка с SSH-туннелями из инструкции эксплуатации:

```bash
uv run python -m scripts.smoke --url http://127.0.0.1:32000
uv run python -m scripts.smoke --url http://127.0.0.1:18000 --output docs/evidence/vm-api.json
uv run python -m scripts.verify_monitoring --password-file .secrets/grafana_password
# Временно останавливает API ВМ; восстановление запускается в finally:
uv run python -m scripts.check_alert
```

Проверка мониторинга создаёт 120 прогнозов и проверяет метрики/логи.
`check_alert` через `.secrets/ssh_config`, хост `course-vm`, останавливает API,
ожидает firing, запускает API и проверяет health = 200 и resolved. Volumes сохраняются;
`down -v` не используется. Score distribution **не измеряет точность**: онлайн
AP/Brier требуют фактических покупок. Offline-качество хранится в manifest.

Для проверки правил алертинга на синтетических рядах:

```bash
docker run --rm --entrypoint promtool -v "$PWD/mlops/deploy:/checks:ro" \
  -w /checks prom/prometheus:v3.5.0 test rules alerts-test.yml
```

## CI/CD

Стадии: `lint`, `formating`, `test`, `build`, `save`, `deploy`; 8 jobs, включая
`test_alerts` и `deploy_k8s`. Black работает с `--check`.
BuildKit rootless публикует `build-<pipeline-id>` в Registry; artifact
`build-metadata.json` передаёт digest. Skopeo в `save` сохраняет тот же образ
под commit SHA (`--preserve-digests`). Manual deploy на основной ветке использует
immutable digest и выбранную версию модели. Образы, датасеты и модели не входят в Git.

В GitLab требуются masked/hidden Variables: `SSH_PRIVATE_KEY_B64`,
`SSH_KNOWN_HOSTS_B64` (проверенный host key), `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`.
Base64 нужен для совместимости маскирования многострочных значений.
Дополнительно задаются `S3_BUCKET`, `DEPLOY_USER`, `DEPLOY_HOST`, `MODEL_VERSION`, `MODEL_MANIFEST_KEY`.
Protected Variables требуют protected основной ветки. Registry credentials в save
предоставляет GitLab. На ВМ требуются файлы `~/ecom-secrets/s3.env`,
`~/ecom-secrets/monitoring.env` (с `GRAFANA_PASSWORD`).
Deploy передаёт `CI_REGISTRY_PASSWORD` через SSH stdin и удаляет временный Docker
config после завершения. S3-init на ВМ использует приватный env-файл.

Runner требует тег `k8s`; DinD недоступен. Сборка — [BuildKit rootless](https://docs.gitlab.com/ci/docker/using_buildkit/).
Для Kubernetes дополнительно используются protected Variables `KUBE_CONFIG_B64`,
`KUBE_NAMESPACE`, `GRAFANA_PASSWORD`; kubeconfig и пароль — masked/hidden.
