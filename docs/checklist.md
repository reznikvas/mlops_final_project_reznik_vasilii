# Соответствие заданию

Проверено 05–06.10.2026. Полный отчёт: [report.md](report.md).
`OK` означает фактически выполненную проверку, а не наличие конфигурации.

| Требование | Файл / действие | Проверка и результат |
|---|---|---|
| uv, зависимости | pyproject.toml, uv.lock, requirements.txt | OK: Python 3.12.13, uv sync --frozen |
| Исходная подготовка и обучение | отдельная копия исходных скриптов | OK: [original-baseline.json](evidence/original-baseline.json) |
| Качество кода | ruff, black --check, mypy, pytest | OK: 29 тестов, 29 типизированных Python-файлов; [логи](evidence/) |
| API :32000 | src/main.py, src/schema.py | OK: health, docs, predict, 404, 422; [HTTP](evidence/local-api.json) |
| Нет модели / повреждённый артефакт | tests/test_main.py, tests/test_storage.py | OK: 503, проверки SHA256 и версии |
| Полный датасет, без будущих признаков | src/data.py, src/features.py | OK: 4 CSV, 20 275 902 строки свойств; [manifest](evidence/processed-manifest.json) |
| Все использованные CSV/Parquet в S3 | scripts/upload_raw.py, src/storage.py | OK: raw, финальные и промежуточные processed-версии |
| Воспроизводимость | устойчивый порядок, seed, версии, SHA256 | OK: локальные и Airflow Parquet побайтово одинаковы, повтор DAG совпадает; [доказательство](evidence/reproducibility.json) |
| Airflow S3 → S3 | mlops/airflow/ | OK: реальные успешные DAG runs; [список](evidence/airflow-runs.json), [скриншот](evidence/airflow.png) |
| ClearML и выбор модели | mlops/clearml/clearml_pipeline.py | OK: два pipeline, 12 завершённых задач; [статусы](evidence/clearml-tasks.json), [скриншот](evidence/clearml.png) |
| Модель в S3, test только для оценки | src/training.py | OK: [manifest](evidence/model-manifest.json), [PR/калибровка](evidence/offline-quality.png) |
| Docker, доставка образа по SSH | Dockerfile, mlops/deploy/docker-compose.yml | OK: одинаковые архив, rootfs, runtime config; [сравнение](evidence/image-transfer.json) |
| API :8000, модель отдельно из S3 | model-init, API на ВМ | OK: [загрузка](evidence/model-init.txt), [HTTP](evidence/vm-api.json), [внешний запрос](evidence/vm-direct-api.json) |
| Перезапуск и восстановление | scripts/check_alert.py | OK: остановка, запуск, health=200, та же модель |
| Prometheus, Grafana, Loki | mlops/deploy/, mlops/grafana/ | OK: реальные ряды, прогнозы в Loki, 8 панелей; [проверка](evidence/monitoring.json), [дашборд](evidence/grafana.png) |
| Алерты | alerts.yml, scripts/check_alert.py | OK: EcomUnavailable firing → resolved; [протокол](evidence/alert-recovery.json) |
| GitLab CI/CD | .gitlab-ci.yml | OK: pipeline 11202 и все 8 jobs, включая deploy 66164 и deploy_k8s 66165, — success; [статусы](evidence/gitlab-ci.json), [скриншот](evidence/gitlab-ci.png) |
| Runner / Registry | rootless BuildKit, Skopeo | OK: Runner с тегом k8s; образ опубликован и скачан на ВМ по [digest](evidence/registry-image.json) |
| Документация | README.md, docs/ | Инструкции, ограничения, реальные JSON/логи/скриншоты |
| Секреты вне Git | .gitignore, приватные .secrets/ | OK: [аудит](evidence/publication-audit-20261006.json); известные секреты не найдены, ссылки документации целы |
| Сохранение вне временной ВМ | S3, .artifacts/backups/ | OK: новые изолированные volumes, 5 DAG runs, 12 задач, Fernet, SHA256 артефактов; [restore](evidence/backup-restore.json) |
| Kubernetes | mlops/deploy/k8s/ | OK: native Deployment/Service, init S3, GET/POST V2, health; [ресурсы](evidence/k8s-resources.json), [HTTP](evidence/k8s-api.json), [8080](evidence/k8s-port8080.json) |
| Мониторинг Kubernetes | mlops/grafana/chart/ | OK: Helm, Prometheus/Grafana/Loki/Alloy; [проверка](evidence/k8s-monitoring.json), [дашборд](evidence/k8s-grafana.png) |
| Восстановление Kubernetes | scripts/check_k8s_alert.py | OK: firing → новый Pod, повторный S3-init → resolved; [протокол](evidence/k8s-recovery.json) |
| Правила 5xx/latency/availability | mlops/deploy/alerts-test.yml | OK: promtool firing/resolved на синтетических рядах, CI test_alerts; [лог](evidence/alert-rules-tests.txt) |

Код опубликован в GitLab, образ — в Container Registry.
Все шесть стадий CI/CD успешны. Отдельный SSH-ключ CI настроен с ограничениями;
[проверены вход и запрет forwarding](evidence/ci-ssh-key.json).
После возобновления ВМ выполнено
[восстановление Airflow и доставки логов](evidence/recovery-after-renewal.json).
