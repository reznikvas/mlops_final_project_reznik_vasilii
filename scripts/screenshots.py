"""Скриншоты реальных интерфейсов через SSH-туннели, без страниц с секретами."""

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", choices=["api", "airflow", "grafana", "clearml"])
    parser.add_argument("--url", required=True)
    parser.add_argument("--password-file", type=Path)
    parser.add_argument("--storage-state", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={
                "width": 1440,
                "height": 1600 if args.service == "grafana" else 1100,
            },
            locale="en-US",
            storage_state=str(args.storage_state) if args.storage_state else None,
        )
        page.goto(args.url, wait_until="networkidle", timeout=60000)
        if args.service in ["airflow", "grafana"]:
            if args.password_file is None:
                raise ValueError("Требуется приватный файл пароля")
            password = args.password_file.read_text().strip()
            if args.service == "airflow":
                page.locator("#username").fill("admin")
                page.locator("#password").fill(password)
                page.locator('input[type="submit"]').click()
                page.wait_for_load_state("networkidle")
                page.goto(
                    args.url.rstrip("/") + "/dags/preprocessing_data/grid",
                    wait_until="networkidle",
                )
            else:
                page.locator('input[name="user"]').fill("admin")
                page.locator('input[name="password"]').fill(password)
                page.get_by_role("button", name="Log in", exact=True).click()
                page.wait_for_timeout(2000)
                if page.get_by_text("Skip", exact=True).count():
                    page.get_by_text("Skip", exact=True).click()
                page.goto(
                    args.url.rstrip("/") + "/d/ecom?from=now-30m&to=now",
                    wait_until="networkidle",
                )
                page.get_by_text("Доступность", exact=True).wait_for(timeout=60000)
                page.get_by_text("Логи прогнозов и ошибок", exact=True).wait_for(
                    timeout=60000
                )
                page.wait_for_timeout(10000)
        page.wait_for_timeout(3000)
        if args.service == "clearml":
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
        directory = Path("docs/evidence")
        directory.mkdir(exist_ok=True)
        page.screenshot(
            path=str(args.output or directory / f"{args.service}.png"),
            full_page=args.service != "grafana",
        )
        print("Скриншот сохранён:", args.service, "title:", page.title())
        browser.close()


if __name__ == "__main__":
    main()
