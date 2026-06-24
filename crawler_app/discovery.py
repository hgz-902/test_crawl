from __future__ import annotations

import importlib
import inspect
import pkgutil

from crawler_app.base import BaseCrawler


# discover 크롤러 목록 값을 계산해 반환한다.
def discover_crawlers(package_name: str = "crawlers") -> list[BaseCrawler]:
    package = importlib.import_module(package_name)
    crawlers: list[BaseCrawler] = []

    for module_info in pkgutil.iter_modules(package.__path__, prefix=f"{package_name}."):
        module = importlib.import_module(module_info.name)
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj is BaseCrawler or not issubclass(obj, BaseCrawler):
                continue
            if inspect.isabstract(obj):
                continue
            crawlers.append(obj())

    crawlers.sort(key=lambda crawler: crawler.name)
    return crawlers
