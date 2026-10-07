"""ClearML pipeline: обучение, сравнение конфигураций и публикация модели."""

import argparse

from clearml.automation import PipelineDecorator


@PipelineDecorator.component(return_values=["processed_path"], cache=False, repo="")
def fetch_processed(manifest_key: str, root: str) -> str:
    from pathlib import Path

    from src.storage import download_manifest

    destination = Path(root) / "processed"
    download_manifest(manifest_key, destination)
    return str(destination)


@PipelineDecorator.component(return_values=["result_path"], cache=False, repo="")
def train_candidate(processed_path: str, root: str, index: int) -> str:
    from pathlib import Path

    from clearml import Task

    from src.training import fit_candidate

    destination = Path(root) / "experiments" / str(index)
    result = fit_candidate(Path(processed_path), destination, index)
    task: Task = Task.current_task()
    task.connect(result["params"], name="CatBoost")
    task.connect({"processed_version": result["processed_version"]}, name="Data")
    for metric, value in result["validation"].items():
        task.get_logger().report_scalar("validation", metric, value, iteration=0)
    return str(destination / "result.json")


@PipelineDecorator.component(return_values=["model_manifest"], cache=False, repo="")
def publish_winner(processed_path: str, root: str, results: list[str]) -> str:
    from pathlib import Path

    from clearml import Task

    from src.storage import PREFIX, upload_directory
    from src.training import select_best

    if len(results) != 3 or not all(Path(p).is_file() for p in results):
        raise ValueError("Нужны три завершённых эксперимента")
    directory = Path(root) / "model"
    manifest = select_best(Path(processed_path), Path(root) / "experiments", directory)
    key = upload_directory(directory, f"{PREFIX}/models/{manifest['version']}")
    task: Task = Task.current_task()
    task.connect({"model_manifest": key, "model_version": manifest["version"]})
    for metric, value in manifest["test"].items():
        task.get_logger().report_scalar("test", metric, value, iteration=0)
    task.upload_artifact("model_metadata", artifact_object=manifest)
    return key


@PipelineDecorator.pipeline(
    name="Ecom CatBoost selection",
    project="Reznik_Vasilii_project",
    version="1.0.0",
    repo="",
    abort_on_failure=True,
)
def pipeline(manifest_key: str, root: str) -> None:
    processed = fetch_processed(manifest_key, root)
    results = []
    for index in range(3):
        # str принудительно ожидает результат: обучение последовательно, 4 CPU.
        results.append(str(train_candidate(processed, root, index)))
    print(str(publish_winner(processed, root, results)))


if __name__ == "__main__":
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-manifest", required=True)
    parser.add_argument("--workdir", type=Path, default=Path(".artifacts/clearml"))
    args = parser.parse_args()
    PipelineDecorator.run_locally()
    pipeline(args.processed_manifest, str(args.workdir.resolve()))
