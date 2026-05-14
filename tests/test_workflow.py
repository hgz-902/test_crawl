from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from crawler_app.workflow import (
    BoardRepeatSpec,
    BoardLoopSpec,
    WorkflowConfigError,
    WorkflowExecution,
    _config_click_loop_step_indexes,
    _config_filter_terms,
    _config_primary_loop_step_index,
    _config_primary_loop_mode,
    _config_search_terms,
    _download_multiple_step,
    _download_loop_step,
    _download_step,
    _board_repeat_step_index,
    _finalize_workflow_execution,
    _apply_workflow_result_filters,
    _resolve_item_count_for_term,
    _resolve_board_items,
    _resolve_board_loop_items,
    _resolve_board_loop_item_numbers,
    _resolve_step_xpath,
    _render_template_value,
    _save_extract_outputs,
    _select_board_item_scope,
    _build_board_loop_spec,
    _attach_dialog_handler,
    _run_nested_click_loops,
    _run_nested_pagination_click_loops,
    _run_one_item,
    _run_step,
    preview_workflow_config,
    run_workflow_config,
    load_workflow_config,
    normalize_workflow_config,
    validate_workflow_config,
)
from crawler_app.google_news_rss import parse_google_news_rss_items, save_google_news_rss_items
from crawler_app.naver_news_api import fetch_naver_news_api_items, parse_naver_news_api_items


def temporary_project_output_dir() -> tempfile.TemporaryDirectory[str]:
    base_dir = Path(__file__).resolve().parent.parent / "outputs" / ".test"
    base_dir.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=base_dir)


class FakeResponse:
    def __init__(self, *, body: bytes, headers: dict[str, str] | None = None, ok: bool = True, status: int = 200) -> None:
        self._body = body
        self.headers = headers or {}
        self.ok = ok
        self.status = status

    def body(self) -> bytes:
        return self._body


class FakeRequest:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, int | None]] = []

    def get(self, url: str, timeout: int | None = None) -> FakeResponse:
        self.calls.append((url, timeout))
        return self.response


class FakeNaverResponse:
    def __init__(
        self,
        *,
        body: bytes,
        url: str,
        headers: dict[str, str] | None = None,
        status_code: int = 200,
    ) -> None:
        self.content = body
        self.url = url
        self.headers = headers or {"Content-Type": "application/json; charset=utf-8"}
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeNaverSession:
    def __init__(self, response: FakeNaverResponse) -> None:
        self.response = response
        self.headers: dict[str, str] = {}
        self.trust_env = True
        self.calls: list[tuple[str, int | float | None]] = []

    def get(self, url: str, timeout: int | float | None = None) -> FakeNaverResponse:
        self.calls.append((url, timeout))
        return self.response


class FakeDownload:
    def __init__(self, suggested_filename: str, content: bytes = b"downloaded") -> None:
        self.suggested_filename = suggested_filename
        self.content = content
        self.saved_to: str | None = None

    def save_as(self, path: str) -> None:
        self.saved_to = path
        Path(path).write_bytes(self.content)


class FakeDownloadContext:
    def __init__(self, download: FakeDownload) -> None:
        self.download = download

    def __enter__(self) -> "FakeDownloadContext":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    @property
    def value(self) -> FakeDownload:
        return self.download


class FakeLocator:
    def __init__(
        self,
        href: str,
        target: str | None = None,
        exclude_match: bool = False,
        evaluate_result: bool = False,
    ) -> None:
        self.href = href
        self.target = target
        self.clicked = False
        self.text = "sample text"
        self.typed_value: str | None = None
        self.exclude_match = exclude_match
        self.evaluate_result = evaluate_result

    def get_attribute(self, attr: str) -> str | None:
        if attr == "href":
            return self.href
        if attr == "target":
            return self.target
        return None

    def click(self, timeout: int | None = None) -> None:
        self.clicked = True

    def wait_for(self, state: str | None = None, timeout: int | None = None) -> None:
        return None

    def type_text(self, value: str, timeout: int | None = None) -> None:
        self.typed_value = value

    def inner_text(self) -> str:
        return self.text

    def inner_html(self) -> str:
        return f"<div>{self.text}</div>"

    def locator(self, selector: str) -> "FakeLocatorGroup":
        return FakeLocatorGroup([FakeLocator(self.href, self.target)]) if self.exclude_match else FakeLocatorGroup([])

    def evaluate(self, expr: str, xpath: str | None = None, **kwargs) -> bool:
        return self.evaluate_result


class FakeLocatorGroup:
    def __init__(self, locators: list[FakeLocator]) -> None:
        self.locators = locators

    def count(self) -> int:
        return len(self.locators)

    def nth(self, index: int) -> FakeLocator:
        return self.locators[index]


class FakeDialog:
    def __init__(self) -> None:
        self.accept_count = 0
        self.dismiss_count = 0

    def accept(self) -> None:
        self.accept_count += 1

    def dismiss(self) -> None:
        self.dismiss_count += 1


class FakeDialogPage:
    def __init__(self) -> None:
        self.handlers: dict[str, object] = {}

    def on(self, event_name: str, handler) -> None:
        self.handlers[event_name] = handler

    def emit_dialog(self, dialog: FakeDialog) -> None:
        handler = self.handlers["dialog"]
        handler(dialog)


class FakePage:
    def __init__(
        self,
        request: FakeRequest,
        download: FakeDownload,
        url: str = "https://example.com/current",
        popup_page: "FakePopupPage" | None = None,
    ) -> None:
        self.context = type("Ctx", (), {"request": request})()
        self._download = download
        self.url = url
        self._popup_page = popup_page or FakePopupPage()
        self.handlers: dict[str, object] = {}

    def expect_download(self, timeout: int | None = None) -> FakeDownloadContext:
        return FakeDownloadContext(self._download)

    def expect_popup(self, timeout: int | None = None) -> "FakePopupContext":
        return FakePopupContext(self._popup_page)

    def on(self, event_name: str, handler) -> None:
        self.handlers[event_name] = handler


class FakePopupPage:
    def __init__(self, url: str = "https://example.com/popup") -> None:
        self.url = url
        self.handlers: dict[str, object] = {}
        self.waited_for: str | None = None

    def on(self, event_name: str, handler) -> None:
        self.handlers[event_name] = handler

    def wait_for_load_state(self, state: str, timeout: int | None = None) -> None:
        self.waited_for = state


class FakePopupContext:
    def __init__(self, popup_page: FakePopupPage) -> None:
        self.popup_page = popup_page

    def __enter__(self) -> "FakePopupContext":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    @property
    def value(self) -> FakePopupPage:
        return self.popup_page


class FakeBoardNode:
    def __init__(self, tag: str, children: dict[str, list["FakeBoardNode"]] | None = None) -> None:
        self.tag = tag
        self.children = children or {}

    def evaluate(self, expr: str) -> str:
        return self.tag

    def locator(self, selector: str) -> "FakeBoardCollection":
        if selector.startswith("xpath=./"):
            path = selector[len("xpath=./") :]
            tag = path.split("/", 1)[0]
            return FakeBoardCollection(self.children.get(tag, []))
        if selector.startswith("xpath=.//*"):
            descendants: list[FakeBoardNode] = []
            for items in self.children.values():
                descendants.extend(items)
            return FakeBoardCollection(descendants)
        raise AssertionError(f"Unexpected selector: {selector}")


class FakeBoardCollection:
    def __init__(self, nodes: list[FakeBoardNode]) -> None:
        self.nodes = nodes

    def count(self) -> int:
        return len(self.nodes)

    @property
    def first(self) -> "FakeBoardCollection":
        return FakeBoardCollection(self.nodes[:1])

    def nth(self, index: int) -> "FakeBoardCollection":
        return FakeBoardCollection([self.nodes[index]])

    def evaluate(self, expr: str) -> str:
        return self.nodes[0].evaluate(expr)

    def locator(self, selector: str) -> "FakeBoardCollection":
        return self.nodes[0].locator(selector)


class FakeBoardPage:
    def __init__(self, selectors: dict[str, FakeBoardCollection]) -> None:
        self.selectors = selectors

    def locator(self, selector: str) -> FakeBoardCollection:
        return self.selectors[selector]


class FakeLoopLocator:
    def __init__(self, count: int, exclude_match: bool = False) -> None:
        self._count = count
        self._exclude_match = exclude_match

    def count(self) -> int:
        return self._count

    @property
    def first(self) -> "FakeLoopLocator":
        return FakeLoopLocator(1, exclude_match=self._exclude_match)

    def locator(self, selector: str) -> "FakeLoopLocator":
        return FakeLoopLocator(1 if self._exclude_match else 0)


class FakeLoopPage:
    def __init__(self, counts: dict[str, int], excluded_selectors: set[str] | None = None) -> None:
        self.counts = counts
        self.excluded_selectors = excluded_selectors or set()
        self.url = "https://example.com/current"
        self.goto_calls: list[str] = []

    def goto(self, url: str, wait_until: str | None = None, timeout: int | None = None) -> None:
        self.url = url
        self.goto_calls.append(url)

    def close(self) -> None:
        return None

    def locator(self, selector: str) -> FakeLoopLocator:
        return FakeLoopLocator(self.counts.get(selector, 0), exclude_match=selector in self.excluded_selectors)


class FakeBrowser:
    def __init__(self, page: FakeLoopPage) -> None:
        self.page = page

    def new_page(self, accept_downloads: bool = True) -> FakeLoopPage:
        return self.page


class FakeStepLoopLocatorGroup:
    def __init__(self, locators: list[FakeLocator]) -> None:
        self.locators = locators

    def count(self) -> int:
        return len(self.locators)

    @property
    def first(self) -> FakeLocator:
        return self.locators[0]

    def nth(self, index: int) -> FakeLocator:
        return self.locators[index]


class FakeStepLoopPage:
    def __init__(self, selectors: dict[str, list[FakeLocator]], popup_page: FakePopupPage | None = None) -> None:
        self.selectors = selectors
        self.context = type("Ctx", (), {"request": FakeRequest(FakeResponse(body=b""))})()
        self.url = "https://example.com/current"
        self._popup_page = popup_page or FakePopupPage()
        self.handlers: dict[str, object] = {}

    def locator(self, selector: str) -> FakeStepLoopLocatorGroup:
        return FakeStepLoopLocatorGroup(self.selectors.get(selector, []))

    def expect_popup(self, timeout: int | None = None) -> FakePopupContext:
        return FakePopupContext(self._popup_page)

    def on(self, event_name: str, handler) -> None:
        self.handlers[event_name] = handler

    def close(self) -> None:
        return None


class WorkflowDownloadTests(unittest.TestCase):
    def test_resolve_board_items_treats_tbody_as_tr_items(self) -> None:
        rows = [FakeBoardNode("tr"), FakeBoardNode("tr"), FakeBoardNode("tr")]
        tbody = FakeBoardNode("tbody", {"tr": rows})
        page = FakeBoardPage({"xpath=//*[@id='content_body']/div/table/tbody": FakeBoardCollection([tbody])})

        count, repeat_spec = _resolve_board_items(page, "//*[@id='content_body']/div/table/tbody", None, "")

        self.assertEqual(count, 3)
        self.assertIsNone(repeat_spec.item_xpath)
        self.assertEqual(repeat_spec.item_tag, "tr")

        scope, scope_spec = _select_board_item_scope(page, "//*[@id='content_body']/div/table/tbody", 1)
        self.assertEqual(scope.count(), 1)
        self.assertEqual(scope.evaluate("(el) => el.tagName.toLowerCase()"), "tr")
        self.assertIsNone(scope_spec.item_xpath)
        self.assertEqual(scope_spec.item_tag, "tr")

    def test_resolve_board_items_treats_ul_as_li_items(self) -> None:
        items = [FakeBoardNode("li"), FakeBoardNode("li")]
        ul = FakeBoardNode("ul", {"li": items})
        page = FakeBoardPage({"xpath=//*[@id='board']/ul": FakeBoardCollection([ul])})

        count, repeat_spec = _resolve_board_items(page, "//*[@id='board']/ul", None, "")

        self.assertEqual(count, 2)
        self.assertIsNone(repeat_spec.item_xpath)
        self.assertEqual(repeat_spec.item_tag, "li")

    def test_resolve_board_items_uses_first_step_xpath_for_generic_repeat_tags(self) -> None:
        cards = [FakeBoardNode("card"), FakeBoardNode("card"), FakeBoardNode("card")]
        page = FakeBoardPage({"xpath=//*[@id='board']/section/card": FakeBoardCollection(cards)})

        count, repeat_spec = _resolve_board_items(
            page,
            "//*[@id='board']/section",
            None,
            "//*[@id='board']/section/card[1]/a",
        )

        self.assertEqual(count, 3)
        self.assertEqual(repeat_spec.item_xpath, "//*[@id='board']/section/card")
        self.assertEqual(repeat_spec.item_tag, "card")

        scope, scope_spec = _select_board_item_scope(
            page,
            "//*[@id='board']/section",
            1,
            board_repeat_spec=repeat_spec,
        )
        self.assertEqual(scope.count(), 1)
        self.assertEqual(scope_spec.item_xpath, "//*[@id='board']/section/card")
        self.assertEqual(scope_spec.item_tag, "card")

    def test_build_board_loop_spec_from_two_anchors(self) -> None:
        spec = _build_board_loop_spec(
            "//*[@id='board']/ul/li[1]/a",
            "//*[@id='board']/ul/li[2]/a",
        )

        self.assertIsNotNone(spec)
        self.assertEqual(spec.anchor_xpath_1, "//*[@id='board']/ul/li[1]/a")
        self.assertEqual(spec.anchor_xpath_2, "//*[@id='board']/ul/li[2]/a")
        self.assertEqual(spec.root_xpath, "//*[@id='board']/ul")
        self.assertEqual(spec.item_segment_template, "li[{item_number}]")
        self.assertEqual(spec.item_tag, "li")
        self.assertEqual(spec.start_index, 1)
        self.assertEqual(spec.render_item_root_xpath(1), "//*[@id='board']/ul/li[1]")
        self.assertEqual(spec.render_anchor_xpath(3), "//*[@id='board']/ul/li[3]/a")

    def test_resolve_board_loop_items_counts_until_first_missing(self) -> None:
        spec = BoardLoopSpec(
            anchor_xpath_1="//*[@id='board']/ul/li[1]/a",
            anchor_xpath_2="//*[@id='board']/ul/li[2]/a",
            root_xpath="//*[@id='board']/ul",
            item_segment_template="li[{item_number}]",
            item_tag="li",
            suffix_segments=("a",),
            start_index=1,
        )
        page = FakeLoopPage(
            {
                "xpath=//*[@id='board']/ul/li[1]/a": 1,
                "xpath=//*[@id='board']/ul/li[2]/a": 1,
                "xpath=//*[@id='board']/ul/li[3]/a": 1,
                "xpath=//*[@id='board']/ul/li[4]/a": 0,
            }
        )

        self.assertEqual(_resolve_board_loop_items(page, spec), 3)

    def test_resolve_board_loop_item_numbers_skips_excluded_rows(self) -> None:
        spec = BoardLoopSpec(
            anchor_xpath_1="//*[@id='board']/ul/li[1]/a",
            anchor_xpath_2="//*[@id='board']/ul/li[2]/a",
            root_xpath="//*[@id='board']/ul",
            item_segment_template="li[{item_number}]",
            item_tag="li",
            suffix_segments=("a",),
            start_index=1,
        )
        page = FakeLoopPage(
            {
                "xpath=//*[@id='board']/ul/li[1]": 1,
                "xpath=//*[@id='board']/ul/li[2]": 1,
                "xpath=//*[@id='board']/ul/li[3]": 1,
                "xpath=//*[@id='board']/ul/li[4]": 1,
                "xpath=//*[@id='board']/ul/li[5]": 1,
                "xpath=//*[@id='board']/ul/li[1]/a": 1,
                "xpath=//*[@id='board']/ul/li[2]/a": 1,
                "xpath=//*[@id='board']/ul/li[3]/a": 1,
                "xpath=//*[@id='board']/ul/li[4]/a": 1,
                "xpath=//*[@id='board']/ul/li[5]/a": 0,
            },
            excluded_selectors={
                "xpath=//*[@id='board']/ul/li[1]",
                "xpath=//*[@id='board']/ul/li[2]",
            },
        )

        self.assertEqual(_resolve_board_loop_item_numbers(page, spec, exclude_xpath=".//span[contains(., '공지')]"), [3, 4])
        self.assertEqual(_resolve_board_loop_items(page, spec, exclude_xpath=".//span[contains(., '공지')]"), 2)

    def test_resolve_item_count_for_term_returns_zero_when_no_matches(self) -> None:
        spec = BoardLoopSpec(
            anchor_xpath_1="//*[@id='board']/ul/li[1]/a",
            anchor_xpath_2="//*[@id='board']/ul/li[2]/a",
            root_xpath="//*[@id='board']/ul",
            item_segment_template="li[{item_number}]",
            item_tag="li",
            suffix_segments=("a",),
            start_index=1,
        )
        browser = FakeBrowser(
            FakeLoopPage(
                {
                    "xpath=//*[@id='board']/ul/li[1]/a": 0,
                }
            )
        )

        count = _resolve_item_count_for_term(
            browser=browser,
            config={
                "start_url": "https://example.com",
                "board": {},
                "steps": [{"name": "search", "xpath": "//input", "action": "click"}],
            },
            search_term="climate",
            search_term_index=0,
            search_term_count=1,
            output_dir=Path(tempfile.gettempdir()),
            timeout_ms=1000,
            step_wait_ms=1000,
            parse_pause_seconds=0,
            primary_loop_step_index=None,
            primary_loop_spec=spec,
            board_repeat_spec=None,
            configured_repeat=False,
        )

        self.assertEqual(count, 0)

    def test_run_one_item_renders_search_term_into_start_url(self) -> None:
        page = FakeLoopPage({})
        browser = FakeBrowser(page)
        config = {
            "name": "google_news",
            "start_url": "https://www.google.com/search?q={search_term}&tbm=nws&hl=ko&gl=kr",
            "output_dir": "outputs/google",
            "steps": [],
        }

        record = _run_one_item(
            browser=browser,
            config=config,
            item_index=None,
            timeout_ms=1000,
            step_wait_ms=1000,
            search_term="climate change",
            search_term_index=0,
            search_term_count=1,
        )

        self.assertEqual(page.goto_calls[0], "https://www.google.com/search?q=climate+change&tbm=nws&hl=ko&gl=kr")
        self.assertEqual(record["start_url"], "https://www.google.com/search?q=climate+change&tbm=nws&hl=ko&gl=kr")

    def test_render_template_value_replaces_search_term(self) -> None:
        self.assertEqual(_render_template_value("news/{search_term}", "google"), "news/google")
        self.assertEqual(_render_template_value("news/{search_term}", None), "news/")
        self.assertEqual(
            _render_template_value("https://example.com?q={search_term}", "climate change", url_encode=True),
            "https://example.com?q=climate+change",
        )

    def test_resolve_step_xpath_honors_loop_start_index(self) -> None:
        self.assertEqual(
            _resolve_step_xpath(
                "//*[@id='board']/ul/li[3]/a",
                0,
                "li",
                "//*[@id='board']/ul",
                start_index=3,
            ),
            "//*[@id='board']/ul/li[3]/a",
        )

    def test_resolve_step_xpath_rewrites_board_item_index(self) -> None:
        self.assertEqual(
            _resolve_step_xpath("//*[@id='board']/table/tbody/tr[1]/td[2]/a", 2, "tr", "//*[@id='board']/table/tbody"),
            "//*[@id='board']/table/tbody/tr[3]/td[2]/a",
        )
        self.assertEqual(
            _resolve_step_xpath("//*[@id='board']/ul/li[1]/a", 0, "li", "//*[@id='board']/ul"),
            "//*[@id='board']/ul/li[1]/a",
        )

    def test_resolve_step_xpath_rewrites_matching_item_tag_not_container_index(self) -> None:
        self.assertEqual(
            _resolve_step_xpath(
                "//*[@id='container']/div/div/div/div[2]/ul/li[1]/a",
                3,
                "li",
                "//*[@id='container']/div/div/div/div[2]/ul",
            ),
            "//*[@id='container']/div/div/div/div[2]/ul/li[4]/a",
        )

    def test_build_board_loop_spec_from_trailing_numeric_suffix(self) -> None:
        spec = _build_board_loop_spec(
            "//*[@id='II-b-66_title_1']/div/div/div[2]/a",
            "//*[@id='II-b-66_title_2']/div/div/div[2]/a",
        )

        self.assertIsNotNone(spec)
        self.assertEqual(spec.anchor_xpath_1, "//*[@id='II-b-66_title_1']/div/div/div[2]/a")
        self.assertEqual(spec.anchor_xpath_2, "//*[@id='II-b-66_title_2']/div/div/div[2]/a")
        self.assertEqual(spec.root_xpath, "//")
        self.assertEqual(spec.item_segment_template, "*[@id='II-b-66_title_{item_number}']")
        self.assertIsNone(spec.item_tag)
        self.assertEqual(spec.start_index, 1)
        self.assertEqual(spec.render_item_root_xpath(1), "//*[@id='II-b-66_title_1']")
        self.assertEqual(spec.render_anchor_xpath(3), "//*[@id='II-b-66_title_3']/div/div/div[2]/a")

    def test_resolve_step_xpath_rewrites_trailing_numeric_suffix(self) -> None:
        spec = BoardLoopSpec(
            anchor_xpath_1="//*[@id='II-b-66_title_1']/div/div/div[2]/a",
            anchor_xpath_2="//*[@id='II-b-66_title_2']/div/div/div[2]/a",
            root_xpath="//",
            item_segment_template="*[@id='II-b-66_title_{item_number}']",
            item_tag=None,
            suffix_segments=("div", "div", "div[2]", "a"),
            start_index=1,
        )

        self.assertEqual(
            _resolve_step_xpath(
                "//*[@id='II-b-66_title_1']/div/div/div[2]/a",
                2,
                None,
                None,
                board_loop_spec=spec,
            ),
            "//*[@id='II-b-66_title_3']/div/div/div[2]/a",
        )

    def test_board_repeat_only_applies_to_first_step(self) -> None:
        repeat_spec = BoardRepeatSpec(item_xpath=None, item_tag="tr")

        self.assertEqual(_board_repeat_step_index(1, 0, repeat_spec), 0)
        self.assertIsNone(_board_repeat_step_index(2, 0, repeat_spec))
        self.assertIsNone(_board_repeat_step_index(1, None, repeat_spec))
        self.assertIsNone(_board_repeat_step_index(1, 0, None))

    def test_validate_workflow_config_requires_second_xpath_for_loop_steps(self) -> None:
        config = {
            "name": "sample",
            "start_url": "https://example.com",
            "output_dir": "outputs/sample",
            "steps": [
                {"name": "download", "xpath": "//a[1]", "action": "download", "loop": True},
            ],
        }

        with self.assertRaises(WorkflowConfigError):
            validate_workflow_config(config)

    def test_validate_workflow_config_allows_pagination_loop_for_click(self) -> None:
        config = {
            "name": "sample",
            "start_url": "https://example.com",
            "output_dir": "outputs/sample",
            "steps": [
                {
                    "name": "page",
                    "xpath": "//*[@id='frontBoardVo']/div[2]/a[{page_number}]",
                    "action": "click",
                    "loop": True,
                    "loop_mode": "pagination",
                    "pagination_mode": "page_number",
                },
                {"name": "download", "xpath": "//a[@href]", "action": "download"},
            ],
        }

        validate_workflow_config(config)

    def test_validate_workflow_config_rejects_pagination_loop_after_first_step(self) -> None:
        config = {
            "name": "sample",
            "start_url": "https://example.com",
            "output_dir": "outputs/sample",
            "steps": [
                {"name": "download", "xpath": "//a[@href]", "action": "download"},
                {
                    "name": "page",
                    "xpath": "//*[@id='frontBoardVo']/div[2]/a[{page_number}]",
                    "action": "click",
                    "loop": True,
                    "loop_mode": "pagination",
                    "pagination_mode": "page_number",
                },
            ],
        }

        with self.assertRaises(WorkflowConfigError):
            validate_workflow_config(config)

    def test_validate_workflow_config_rejects_pagination_loop_without_placeholder(self) -> None:
        config = {
            "name": "sample",
            "start_url": "https://example.com",
            "output_dir": "outputs/sample",
            "steps": [
                {
                    "name": "page",
                    "xpath": "//*[@id='frontBoardVo']/div[2]/a[2]",
                    "action": "click",
                    "loop": True,
                    "loop_mode": "pagination",
                    "pagination_mode": "page_number",
                },
                {"name": "download", "xpath": "//a[@href]", "action": "download"},
            ],
        }

        with self.assertRaises(WorkflowConfigError):
            validate_workflow_config(config)

    def test_validate_workflow_config_rejects_negative_loop_limit(self) -> None:
        config = {
            "name": "sample",
            "start_url": "https://example.com",
            "output_dir": "outputs/sample",
            "steps": [
                {
                    "name": "download",
                    "xpath": "//a[1]",
                    "xpath_2": "//a[2]",
                    "action": "download",
                    "loop": True,
                    "loop_limit": -1,
                },
            ],
        }

        with self.assertRaises(WorkflowConfigError):
            validate_workflow_config(config)

    def test_normalize_workflow_config_maps_submit_form_to_page_number(self) -> None:
        config = {
            "name": "sample",
            "start_url": "https://example.com",
            "output_dir": "outputs/sample",
            "steps": [
                {
                    "name": "page",
                    "xpath": "//*[@id='frontBoardVo']/div[2]/a[{page_number}]",
                    "action": "click",
                    "loop": True,
                    "loop_mode": "pagination",
                    "pagination_mode": "submit_form",
                }
            ],
        }

        normalized = normalize_workflow_config(config)
        self.assertEqual(normalized["steps"][0]["pagination_mode"], "page_number")

    def test_validate_workflow_config_rejects_negative_timeout_ms(self) -> None:
        config = {
            "name": "sample",
            "start_url": "https://example.com",
            "output_dir": "outputs/sample",
            "timeout_ms": -1,
            "steps": [
                {"name": "download", "xpath": "//a[1]", "action": "download"},
            ],
        }

        with self.assertRaises(WorkflowConfigError):
            validate_workflow_config(config)

    def test_validate_workflow_config_allows_first_step_loop_for_click(self) -> None:
        config = {
            "name": "sample",
            "start_url": "https://example.com",
            "output_dir": "outputs/sample",
            "steps": [
                {
                    "name": "open_detail",
                    "xpath": "//a[1]",
                    "xpath_2": "//a[2]",
                    "action": "click",
                    "loop": True,
                },
                {"name": "download", "xpath": "//a[@href]", "action": "download"},
            ],
        }

        validate_workflow_config(config)

    def test_validate_workflow_config_allows_second_step_loop_for_click(self) -> None:
        config = {
            "name": "sample",
            "start_url": "https://example.com",
            "output_dir": "outputs/sample",
            "steps": [
                {"name": "page", "xpath": "//a[1]", "xpath_2": "//a[2]", "action": "click", "loop": True},
                {
                    "name": "open_detail",
                    "xpath": "//li[1]/a",
                    "xpath_2": "//li[2]/a",
                    "action": "click",
                    "loop": True,
                },
                {"name": "download", "xpath": "//a[@href]", "action": "download"},
            ],
        }

        validate_workflow_config(config)

    def test_validate_workflow_config_rejects_fill_action(self) -> None:
        config = {
            "name": "sample",
            "start_url": "https://example.com",
            "output_dir": "outputs/sample",
            "steps": [
                {"name": "search", "xpath": "//input", "action": "fill"},
            ],
        }

        with self.assertRaises(WorkflowConfigError):
            validate_workflow_config(config)

    def test_validate_workflow_config_allows_google_rss_parser_step(self) -> None:
        config = {
            "name": "google",
            "start_url": "https://news.google.com/rss/search?q={search_term}&hl=ko&gl=KR&ceid=KR:ko",
            "output_dir": "outputs/google",
            "steps": [
                {
                    "name": "google_rss",
                    "action": "parser",
                    "attr": "google",
                }
            ],
        }

        validate_workflow_config(config)

    def test_validate_workflow_config_allows_google_rss_parser_step_with_loop_limit(self) -> None:
        config = {
            "name": "google",
            "start_url": "https://news.google.com/rss/search?q={search_term}&hl=ko&gl=KR&ceid=KR:ko",
            "output_dir": "outputs/google",
            "steps": [
                {
                    "name": "google_rss",
                    "action": "parser",
                    "attr": "google",
                    "loop_limit": 3,
                }
            ],
        }

        validate_workflow_config(config)

    def test_validate_workflow_config_rejects_google_rss_parser_non_google_url(self) -> None:
        config = {
            "name": "google",
            "start_url": "https://example.com/rss/search?q={search_term}",
            "output_dir": "outputs/google",
            "steps": [
                {
                    "name": "google_rss",
                    "action": "parser",
                    "attr": "google",
                }
            ],
        }

        with self.assertRaises(WorkflowConfigError):
            validate_workflow_config(config)

    def test_validate_workflow_config_rejects_output_dir_outside_project(self) -> None:
        config = {
            "name": "sample",
            "start_url": "https://example.com",
            "output_dir": "../outside",
            "steps": [
                {"name": "download", "xpath": "//a[1]", "action": "download"},
            ],
        }

        with self.assertRaises(WorkflowConfigError):
            validate_workflow_config(config)

    def test_validate_workflow_config_rejects_parser_xpath_fields(self) -> None:
        config = {
            "name": "google",
            "start_url": "https://news.google.com/rss/search?q={search_term}&hl=ko&gl=KR&ceid=KR:ko",
            "output_dir": "outputs/google",
            "steps": [
                {
                    "name": "google_rss",
                    "action": "parser",
                    "attr": "google",
                    "xpath": "//item",
                }
            ],
        }

        with self.assertRaises(WorkflowConfigError):
            validate_workflow_config(config)

    def test_parse_google_news_rss_items_extracts_expected_fields(self) -> None:
        items = parse_google_news_rss_items(
            """
            <rss version="2.0">
              <channel>
                <item>
                  <title>첫 기사</title>
                  <link>https://example.com/article-1</link>
                  <guid>guid-1</guid>
                  <pubDate>Tue, 29 Apr 2026 09:00:00 +0900</pubDate>
                  <source url="https://news.example.com">예시뉴스</source>
                  <description>요약 문장</description>
                </item>
              </channel>
            </rss>
            """.encode("utf-8")
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "첫 기사")
        self.assertEqual(items[0]["detail_url"], "https://example.com/article-1")
        self.assertEqual(items[0]["post_id"], "guid-1")
        self.assertEqual(items[0]["pubDate"], "Tue, 29 Apr 2026 09:00:00 +0900")
        self.assertEqual(items[0]["source"], "예시뉴스")
        self.assertEqual(items[0]["source_url"], "https://news.example.com")

    def test_parse_google_news_rss_items_sorts_by_pub_date_descending(self) -> None:
        items = parse_google_news_rss_items(
            """
            <rss version="2.0">
              <channel>
                <item>
                  <title>오래된 기사</title>
                  <link>https://example.com/article-1</link>
                  <guid>guid-1</guid>
                  <pubDate>Tue, 29 Apr 2026 09:00:00 +0900</pubDate>
                </item>
                <item>
                  <title>새 기사</title>
                  <link>https://example.com/article-2</link>
                  <guid>guid-2</guid>
                  <pubDate>Tue, 29 Apr 2026 10:00:00 +0900</pubDate>
                </item>
              </channel>
            </rss>
            """.encode("utf-8")
        )

        self.assertEqual([item["title"] for item in items], ["새 기사", "오래된 기사"])

    def test_parse_google_news_rss_items_normalizes_description_html(self) -> None:
        items = parse_google_news_rss_items(
            """
            <rss version="2.0">
              <channel>
                <item>
                  <title>첫 기사</title>
                  <link>https://example.com/article-1</link>
                  <guid>guid-1</guid>
                  <description><![CDATA[
                    <ol><li><a href="https://news.example.com/article">첫 문장 &amp; 핵심</a>
                    <font color="#6f6f6f">예시뉴스</font></li></ol>
                  ]]></description>
                </item>
              </channel>
            </rss>
            """.encode("utf-8")
        )

        self.assertEqual(items[0]["description"], "첫 문장 & 핵심")
        self.assertNotIn("<", items[0]["description"])
        self.assertNotIn("&amp;", items[0]["description"])

    def test_parse_naver_news_api_items_extracts_expected_fields(self) -> None:
        items = parse_naver_news_api_items(
            """
            {
              "items": [
                {
                  "title": "네이버 <b>뉴스</b>",
                  "originallink": "https://example.com/original",
                  "link": "https://n.news.naver.com/mnews/article/001/0001",
                  "description": "<b>요약</b> 문장",
                  "pubDate": "Tue, 29 Apr 2026 09:00:00 +0900"
                }
              ]
            }
            """.encode("utf-8")
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "네이버 뉴스")
        self.assertEqual(items[0]["originallink"], "https://example.com/original")
        self.assertEqual(items[0]["detail_url"], "https://n.news.naver.com/mnews/article/001/0001")
        self.assertEqual(items[0]["link"], "https://n.news.naver.com/mnews/article/001/0001")
        self.assertEqual(items[0]["description"], "요약 문장")
        self.assertEqual(items[0]["pubDate"], "Tue, 29 Apr 2026 09:00:00 +0900")

    def test_fetch_naver_news_api_items_uses_env_client_headers(self) -> None:
        response = FakeNaverResponse(
            body=b'{"items": []}',
            url="https://openapi.naver.com/v1/search/news.json?query=%EC%A3%BC%EC%8B%9D",
        )
        session = FakeNaverSession(response)

        with patch.dict(
            os.environ,
            {
                "NAVER_CLIENT_ID": "client-id",
                "NAVER_CLIENT_SECRET": "client-secret",
            },
            clear=False,
        ), patch("crawler_app.naver_news_api.requests.Session", return_value=session):
            items, final_url = fetch_naver_news_api_items(
                "https://openapi.naver.com/v1/search/news.json?query=%EC%A3%BC%EC%8B%9D"
            )

        self.assertEqual(items, [])
        self.assertEqual(final_url, response.url)
        self.assertEqual(session.headers["X-Naver-Client-Id"], "client-id")
        self.assertEqual(session.headers["X-Naver-Client-Secret"], "client-secret")
        self.assertEqual(session.calls[0][0], "https://openapi.naver.com/v1/search/news.json?query=%EC%A3%BC%EC%8B%9D")

    def test_validate_workflow_config_allows_naver_news_api_parser_step(self) -> None:
        config = {
            "name": "naver-news",
            "start_url": "https://openapi.naver.com/v1/search/news.json?query={search_term}&display=100&start=1&sort=date",
            "output_dir": "outputs/naver-news",
            "steps": [
                {
                    "name": "naver_news_api",
                    "action": "parser",
                    "attr": "naver",
                    "page_limit": 1,
                    "loop_limit": 20,
                }
            ],
        }

        validate_workflow_config(config)

    def test_validate_workflow_config_allows_bounded_naver_api_parser_options(self) -> None:
        config = {
            "name": "naver-news",
            "start_url": "https://openapi.naver.com/v1/search/news.json?query={search_term}&display=10&start=1&sort=date",
            "output_dir": "outputs/naver-news",
            "steps": [
                {
                    "name": "naver_news_api",
                    "action": "parser",
                    "attr": "naver",
                    "page_limit": 1,
                    "loop_limit": 20,
                }
            ],
        }

        validate_workflow_config(config)

    def test_normalize_workflow_config_removes_deprecated_naver_detail_options(self) -> None:
        config = {
            "name": "naver-news",
            "start_url": "https://openapi.naver.com/v1/search/news.json?query={search_term}&display=10&start=1&sort=date",
            "output_dir": "outputs/naver-news",
            "steps": [
                {
                    "name": "naver_news_api",
                    "action": "parser",
                    "attr": "naver",
                    "page_limit": 1,
                    "loop_limit": 20,
                    "display": 7,
                    "fetch_detail": True,
                    "detail_timeout_seconds": 5,
                    "detail_pause_seconds": 0.2,
                    "max_detail_chars": 20000,
                    "allowed_detail_domains": ["n.news.naver.com"],
                }
            ],
        }

        normalized = normalize_workflow_config(config)

        step = normalized["steps"][0]
        self.assertEqual(step["attr"], "naver")
        self.assertEqual(step["display"], 100)
        self.assertEqual(step["page_limit"], 1)
        self.assertIn("display=100", normalized["start_url"])
        self.assertIn("start=1", normalized["start_url"])
        self.assertNotIn("fetch_detail", step)
        self.assertNotIn("allowed_detail_domains", step)
        self.assertNotIn("detail_timeout_seconds", step)
        self.assertNotIn("detail_pause_seconds", step)
        self.assertNotIn("max_detail_chars", step)

    def test_validate_workflow_config_rejects_invalid_naver_page_limit(self) -> None:
        base_step = {
            "name": "naver_news_api",
            "action": "parser",
            "attr": "naver",
            "loop_limit": 20,
        }
        config = {
            "name": "naver-news",
            "start_url": "https://openapi.naver.com/v1/search/news.json?query={search_term}&display=10&start=1&sort=date",
            "output_dir": "outputs/naver-news",
            "steps": [{**base_step, "page_limit": "oops"}],
        }

        with self.assertRaises(WorkflowConfigError):
            validate_workflow_config(config)

    def test_validate_workflow_config_rejects_missing_naver_loop_limit(self) -> None:
        config = {
            "name": "naver-news",
            "start_url": "https://openapi.naver.com/v1/search/news.json?query={search_term}&display=100&start=1&sort=date",
            "output_dir": "outputs/naver-news",
            "steps": [
                {
                    "name": "naver_news_api",
                    "action": "parser",
                    "attr": "naver",
                    "page_limit": 1,
                }
            ],
        }

        with self.assertRaises(WorkflowConfigError):
            validate_workflow_config(config)

    def test_validate_workflow_config_rejects_too_broad_naver_limits(self) -> None:
        config = {
            "name": "naver-news",
            "start_url": "https://openapi.naver.com/v1/search/news.json?query={search_term}&display=100&start=1&sort=date",
            "output_dir": "outputs/naver-news",
            "steps": [
                {
                    "name": "naver_news_api",
                    "action": "parser",
                    "attr": "naver",
                    "page_limit": 11,
                    "loop_limit": 101,
                }
            ],
        }

        with self.assertRaises(WorkflowConfigError):
            validate_workflow_config(config)

    def test_validate_workflow_config_allows_daum_news_api_parser_step(self) -> None:
        config = {
            "name": "daum-news",
            "start_url": "https://dapi.kakao.com/v2/search/web?query={search_term}&sort=recency&page=1&size=50",
            "output_dir": "outputs/daum-news",
            "steps": [
                {
                    "name": "daum_news_api",
                    "action": "parser",
                    "attr": "daum",
                    "sort": "recency",
                    "page_limit": 2,
                    "loop_limit": 100,
                }
            ],
        }

        validate_workflow_config(config)

    def test_normalize_workflow_config_syncs_daum_count_to_url(self) -> None:
        config = {
            "name": "daum-news",
            "start_url": "https://dapi.kakao.com/v2/search/web?query={search_term}&sort=accuracy&page=3&size=10",
            "output_dir": "outputs/daum-news",
            "kakao_rest_api_key": "stale-key",
            "steps": [
                {
                    "name": "daum_news_api",
                    "action": "parser",
                    "attr": "daum",
                    "sort": "recency",
                    "page_limit": 1,
                    "loop_limit": 75,
                    "kakao_rest_api_key": "nested-stale-key",
                }
            ],
        }

        normalized = normalize_workflow_config(config)

        self.assertIn("sort=recency", normalized["start_url"])
        self.assertIn("page=1", normalized["start_url"])
        self.assertIn("size=50", normalized["start_url"])
        self.assertIn("query={search_term}+site%3Av.daum.net", normalized["start_url"])
        self.assertEqual(normalized["steps"][0]["page_limit"], 2)
        self.assertNotIn("kakao_rest_api_key", normalized)
        self.assertNotIn("kakao_rest_api_key", normalized["steps"][0])

    def test_validate_workflow_config_rejects_too_broad_daum_limits(self) -> None:
        config = {
            "name": "daum-news",
            "start_url": "https://dapi.kakao.com/v2/search/web?query={search_term}&sort=recency&page=1&size=50",
            "output_dir": "outputs/daum-news",
            "steps": [
                {
                    "name": "daum_news_api",
                    "action": "parser",
                    "attr": "daum",
                    "sort": "recency",
                    "page_limit": 3,
                    "loop_limit": 101,
                }
            ],
        }

        with self.assertRaises(WorkflowConfigError):
            validate_workflow_config(config)

    def test_run_workflow_config_parses_naver_news_api_without_playwright(self) -> None:
        config = {
            "name": "naver-news",
            "start_url": "https://openapi.naver.com/v1/search/news.json?query={search_term}&display=100&start=1&sort=date",
            "output_dir": "outputs/naver-news",
            "timeout_ms": 1000,
            "search_terms": ["주식"],
            "steps": [
                {
                    "name": "naver_news_api",
                    "action": "parser",
                    "attr": "naver",
                    "page_limit": 1,
                    "loop_limit": 20,
                }
            ],
        }
        api_items = [
            {
                "post_id": "https://n.news.naver.com/mnews/article/001/0001",
                "title": "네이버 뉴스",
                "detail_url": "https://n.news.naver.com/mnews/article/001/0001",
                "link": "https://n.news.naver.com/mnews/article/001/0001",
                "originallink": "https://example.com/original",
                "pubDate": "Tue, 29 Apr 2026 09:00:00 +0900",
                "description": "요약 문장",
            }
        ]

        with temporary_project_output_dir() as tmp_dir:
            config["output_dir"] = str(Path(tmp_dir) / "naver-news")
            with patch.dict(
                os.environ,
                {
                    "NAVER_CLIENT_ID": "client-id",
                    "NAVER_CLIENT_SECRET": "client-secret",
                },
                clear=False,
            ), patch(
                "crawler_app.workflow.fetch_naver_news_api_items",
                return_value=(api_items, "https://openapi.naver.com/v1/search/news.json?query=%EC%A3%BC%EC%8B%9D&display=100&start=1&sort=date"),
            ):
                execution = run_workflow_config(config)

            self.assertTrue(execution.success)
            self.assertEqual(execution.diagnostics["parser_name"], "naver")
            self.assertEqual(execution.diagnostics["parser_item_count"], 1)
            self.assertEqual(len(execution.records), 1)
            self.assertEqual(execution.records[0]["record_key"], "term001_item001")
            self.assertEqual(execution.records[0]["steps"][0]["action"], "parser")
            self.assertEqual(execution.records[0]["extracts"]["title"], "네이버 뉴스")
            naver_output_path = Path(execution.extracted_files[0])
            self.assertEqual(naver_output_path.name, "naver_news_api.json")
            self.assertEqual(naver_output_path.parent.parent.name, "items")
            self.assertEqual(naver_output_path.parent.name, f"{date.today():%Y%m%d}_1")
            self.assertNotIn("filter", naver_output_path.parts)
            naver_manifest_path = Path(execution.diagnostics["manifest_file"])
            self.assertEqual(naver_manifest_path.name, "workflow_records.json")
            self.assertEqual(naver_manifest_path.parent.parent.name, "runs")
            self.assertEqual(naver_manifest_path.parent.name, f"{date.today():%Y%m%d}_1")
            self.assertTrue(Path(execution.records[0]["output_file"]).exists())

    def test_run_workflow_config_keeps_naver_api_outputs_in_term_path_when_filtering(self) -> None:
        config = {
            "name": "naver-news",
            "start_url": "https://openapi.naver.com/v1/search/news.json?query={search_term}&display=100&start=1&sort=date",
            "output_dir": "outputs/naver-news",
            "timeout_ms": 1000,
            "search_terms": ["SK"],
            "filter_terms": ["SK"],
            "steps": [
                {
                    "name": "naver_news_api",
                    "action": "parser",
                    "attr": "naver",
                    "page_limit": 1,
                    "loop_limit": 20,
                }
            ],
        }
        api_items = [
            {"post_id": "1", "title": "SK 뉴스", "detail_url": "https://n.news.naver.com/1", "link": "https://n.news.naver.com/1"},
            {"post_id": "2", "title": "다른 뉴스", "detail_url": "https://n.news.naver.com/2", "link": "https://n.news.naver.com/2"},
        ]

        with temporary_project_output_dir() as tmp_dir:
            config["output_dir"] = str(Path(tmp_dir) / "naver-news")
            with patch(
                "crawler_app.workflow.fetch_naver_news_api_items",
                return_value=(api_items, "https://openapi.naver.com/v1/search/news.json?query=SK&display=100&start=1&sort=date"),
            ):
                execution = run_workflow_config(config)

            self.assertTrue(execution.success)
            self.assertEqual(len(execution.records), 1)
            self.assertEqual(execution.diagnostics["nonfilter_record_count"], 1)
            output_path = Path(execution.extracted_files[0])
            self.assertIn("001_SK", output_path.parts)
            self.assertIn("items", output_path.parts)
            self.assertNotIn("filter", output_path.parts)
            self.assertEqual(Path(execution.diagnostics["manifest_file"]).parent.parent.name, "runs")

    def test_run_workflow_config_parses_daum_news_api_without_playwright(self) -> None:
        config = {
            "name": "daum-news",
            "start_url": "https://dapi.kakao.com/v2/search/web?query={search_term}&sort=recency&page=1&size=50",
            "output_dir": "outputs/daum-news",
            "timeout_ms": 1000,
            "search_terms": ["SK"],
            "steps": [
                {
                    "name": "daum_news_api",
                    "action": "parser",
                    "attr": "daum",
                    "sort": "recency",
                    "page_limit": 1,
                    "loop_limit": 20,
                }
            ],
        }
        api_items = [
            {
                "post_id": "https://v.daum.net/v/202605140001",
                "title": "다음 뉴스",
                "detail_url": "https://v.daum.net/v/202605140001",
                "link": "https://v.daum.net/v/202605140001",
                "pubDate": "2026-05-14T09:00:00.000+09:00",
                "description": "요약 문장",
                "source_domain": "v.daum.net",
                "source_api": "kakao_daum_web_search",
            }
        ]

        with temporary_project_output_dir() as tmp_dir:
            config["output_dir"] = str(Path(tmp_dir) / "daum-news")
            with patch(
                "crawler_app.workflow.fetch_daum_news_api_items",
                return_value=(api_items, "https://dapi.kakao.com/v2/search/web?query=SK&sort=recency&page=1&size=50"),
            ):
                execution = run_workflow_config(config)

            self.assertTrue(execution.success)
            self.assertEqual(execution.diagnostics["parser_name"], "daum")
            self.assertEqual(execution.diagnostics["parser_item_count"], 1)
            self.assertEqual(len(execution.records), 1)
            self.assertEqual(execution.records[0]["steps"][0]["attr"], "daum")
            self.assertEqual(execution.records[0]["extracts"]["title"], "다음 뉴스")
            daum_output_path = Path(execution.extracted_files[0])
            self.assertEqual(daum_output_path.name, "daum_news_api.json")
            self.assertEqual(daum_output_path.parent.parent.name, "items")
            self.assertEqual(daum_output_path.parent.name, f"{date.today():%Y%m%d}_1")
            self.assertNotIn("filter", daum_output_path.parts)
            daum_manifest_path = Path(execution.diagnostics["manifest_file"])
            self.assertEqual(daum_manifest_path.name, "workflow_records.json")
            self.assertEqual(daum_manifest_path.parent.parent.name, "runs")
            self.assertEqual(daum_manifest_path.parent.name, f"{date.today():%Y%m%d}_1")
            self.assertTrue(Path(execution.records[0]["output_file"]).exists())

    def test_preview_workflow_config_skips_live_daum_api_calls(self) -> None:
        config = {
            "name": "daum-news",
            "start_url": "https://dapi.kakao.com/v2/search/web?query={search_term}&sort=recency&page=1&size=50",
            "output_dir": "outputs/daum-news",
            "timeout_ms": 1000,
            "search_terms": ["최태원", "SK"],
            "steps": [
                {
                    "name": "daum_news_api",
                    "action": "parser",
                    "attr": "daum",
                    "sort": "recency",
                    "page_limit": 1,
                    "loop_limit": 20,
                }
            ],
        }

        with patch("crawler_app.workflow.fetch_daum_news_api_items") as fetcher:
            preview = preview_workflow_config(config)

        fetcher.assert_not_called()
        self.assertTrue(preview["preview_skipped"])
        self.assertEqual(preview["parser_item_count"], 0)
        self.assertEqual(len(preview["search_term_runs"]), 2)

    def test_preview_workflow_config_skips_live_naver_api_calls(self) -> None:
        config = {
            "name": "naver-news",
            "start_url": "https://openapi.naver.com/v1/search/news.json?query={search_term}&display=100&start=1&sort=date",
            "output_dir": "outputs/naver-news",
            "timeout_ms": 1000,
            "search_terms": ["최태원", "SK"],
            "steps": [
                {
                    "name": "naver_news_api",
                    "action": "parser",
                    "attr": "naver",
                    "page_limit": 1,
                    "loop_limit": 20,
                }
            ],
        }

        with patch("crawler_app.workflow.fetch_naver_news_api_items") as fetcher:
            preview = preview_workflow_config(config)

        fetcher.assert_not_called()
        self.assertTrue(preview["preview_skipped"])
        self.assertEqual(preview["parser_item_count"], 0)
        self.assertEqual(len(preview["search_term_runs"]), 2)

    def test_run_workflow_config_parses_google_news_rss_without_playwright(self) -> None:
        config = {
            "name": "google",
            "start_url": "https://news.google.com/rss/search?q={search_term}&hl=ko&gl=KR&ceid=KR:ko",
            "output_dir": "outputs/google",
            "timeout_ms": 1000,
            "search_terms": ["SK이노베이션"],
            "steps": [
                {
                    "name": "google_rss",
                    "action": "parser",
                    "attr": "google",
                }
            ],
        }
        rss_items = [
            {
                "post_id": "guid-2",
                "title": "둘째 기사",
                "detail_url": "https://example.com/article-2",
                "link": "https://example.com/article-2",
                "pubDate": "Tue, 29 Apr 2026 10:00:00 +0900",
                "source": "예시뉴스",
                "source_url": "https://news.example.com",
                "description": "요약 문장 2",
                "guid": "guid-2",
            },
            {
                "post_id": "guid-1",
                "title": "첫 기사",
                "detail_url": "https://example.com/article-1",
                "link": "https://example.com/article-1",
                "pubDate": "Tue, 29 Apr 2026 09:00:00 +0900",
                "source": "예시뉴스",
                "source_url": "https://news.example.com",
                "description": "요약 문장",
                "guid": "guid-1",
            },
        ]

        with temporary_project_output_dir() as tmp_dir:
            config["output_dir"] = str(Path(tmp_dir) / "google")
            with patch(
                "crawler_app.workflow.fetch_google_news_rss_items",
                return_value=(rss_items, "https://news.google.com/rss/search?q=SK%EC%9D%B4%EB%85%B8%EB%B2%A0%EC%9D%B4%EC%85%98&hl=ko&gl=KR&ceid=KR:ko"),
            ):
                execution = run_workflow_config(config)

            self.assertTrue(execution.success)
            self.assertEqual(execution.diagnostics["parser_name"], "google")
            self.assertEqual(execution.diagnostics["parser_item_count"], 2)
            self.assertEqual(len(execution.records), 2)
            self.assertEqual(execution.records[0]["record_key"], "term001_item001")
            self.assertEqual(execution.records[0]["steps"][0]["action"], "parser")
            self.assertEqual(execution.records[0]["extracts"]["title"], "둘째 기사")
            self.assertEqual(len(execution.extracted_files), 1)
            saved_path = Path(execution.extracted_files[0])
            self.assertTrue(saved_path.exists())
            self.assertEqual(saved_path.parent.parent.name, "items")
            self.assertEqual(saved_path.parent.name, f"{date.today():%Y%m%d}_1")
            self.assertNotIn("filter", saved_path.parts)

    def test_run_workflow_config_parses_google_news_rss_without_search_terms_uses_indexed_dir(self) -> None:
        config = {
            "name": "google",
            "start_url": "https://news.google.com/rss/search?q={search_term}&hl=ko&gl=KR&ceid=KR:ko",
            "output_dir": "outputs/google",
            "timeout_ms": 1000,
            "steps": [
                {
                    "name": "google_rss",
                    "action": "parser",
                    "attr": "google",
                }
            ],
        }
        rss_items = [
            {
                "post_id": "guid-1",
                "title": "첫 기사",
                "detail_url": "https://example.com/article-1",
                "link": "https://example.com/article-1",
                "pubDate": "Tue, 29 Apr 2026 09:00:00 +0900",
                "source": "예시뉴스",
                "source_url": "https://news.example.com",
                "description": "요약 문장",
                "guid": "guid-1",
            }
        ]

        with temporary_project_output_dir() as tmp_dir:
            config["output_dir"] = str(Path(tmp_dir) / "google")
            with patch(
                "crawler_app.workflow.fetch_google_news_rss_items",
                return_value=(rss_items, "https://news.google.com/rss/search?q=&hl=ko&gl=KR&ceid=KR:ko"),
            ):
                execution = run_workflow_config(config)

            self.assertTrue(execution.success)
            saved_path = Path(execution.extracted_files[0])
            self.assertNotIn("filter", saved_path.parts)
            self.assertEqual(saved_path.parent.parent.name, "items")
            self.assertIn("001_default", saved_path.parts)
            self.assertEqual(saved_path.name, "google_news_rss.json")
            self.assertEqual(saved_path.parent.name, f"{date.today():%Y%m%d}_1")
            saved_payload = json.loads(saved_path.read_text(encoding="utf-8"))
            self.assertEqual(saved_payload["item_files"], ["item_0001.json"])
            self.assertTrue((saved_path.parent / "item_0001.json").exists())
            self.assertEqual(execution.records[0]["record_key"], "term001_item001")

    def test_run_workflow_config_limits_google_news_rss_items_with_loop_limit(self) -> None:
        config = {
            "name": "google",
            "start_url": "https://news.google.com/rss/search?q={search_term}&hl=ko&gl=KR&ceid=KR:ko",
            "output_dir": "outputs/google",
            "timeout_ms": 1000,
            "search_terms": ["SK이노베이션"],
            "steps": [
                {
                    "name": "google_rss",
                    "action": "parser",
                    "attr": "google",
                    "loop_limit": 1,
                }
            ],
        }
        rss_items = [
            {
                "post_id": "guid-2",
                "title": "둘째 기사",
                "detail_url": "https://example.com/article-2",
                "link": "https://example.com/article-2",
                "pubDate": "Tue, 29 Apr 2026 10:00:00 +0900",
                "source": "예시뉴스",
                "source_url": "https://news.example.com",
                "description": "요약 문장 2",
                "guid": "guid-2",
            },
            {
                "post_id": "guid-1",
                "title": "첫 기사",
                "detail_url": "https://example.com/article-1",
                "link": "https://example.com/article-1",
                "pubDate": "Tue, 29 Apr 2026 09:00:00 +0900",
                "source": "예시뉴스",
                "source_url": "https://news.example.com",
                "description": "요약 문장",
                "guid": "guid-1",
            },
        ]

        with temporary_project_output_dir() as tmp_dir:
            config["output_dir"] = str(Path(tmp_dir) / "google")
            with patch(
                "crawler_app.workflow.fetch_google_news_rss_items",
                return_value=(rss_items, "https://news.google.com/rss/search?q=SK%EC%9D%B4%EB%85%B8%EB%B2%A0%EC%9D%B4%EC%85%98&hl=ko&gl=KR&ceid=KR:ko"),
            ):
                execution = run_workflow_config(config)

            self.assertTrue(execution.success)
            self.assertEqual(execution.diagnostics["parser_item_count"], 1)
            self.assertEqual(len(execution.records), 1)
            self.assertEqual(execution.records[0]["record_key"], "term001_item001")
            self.assertEqual(execution.records[0]["extracts"]["title"], "둘째 기사")
            saved_path = Path(execution.extracted_files[0])
            saved_payload = json.loads(saved_path.read_text(encoding="utf-8"))
            self.assertEqual(saved_payload["item_count"], 1)
            self.assertEqual(saved_payload["item_files"], ["item_0001.json"])
            self.assertTrue((saved_path.parent / "item_0001.json").exists())
            saved_item = json.loads((saved_path.parent / "item_0001.json").read_text(encoding="utf-8"))
            self.assertEqual(saved_item["title"], "둘째 기사")
            self.assertNotIn("filter", saved_path.parts)

    def test_save_google_news_rss_items_allocates_next_daily_run_directory(self) -> None:
        with temporary_project_output_dir() as tmp_dir:
            output_dir = Path(tmp_dir) / "google" / "002_SK"
            today = date.today().strftime("%Y%m%d")
            (output_dir / "items" / f"{today}_1").mkdir(parents=True)
            (output_dir / "items" / f"{today}_2").mkdir(parents=True)

            manifest = save_google_news_rss_items(
                output_dir,
                search_term="SK",
                rss_url="https://news.google.com/rss/search?q=SK",
                final_url="https://news.google.com/rss/search?q=SK",
                items=[{"post_id": "1", "title": "A"}],
            )

            self.assertEqual(manifest.parent, output_dir / "items" / f"{today}_3")
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(payload["item_files"], ["item_0001.json"])
            self.assertTrue((manifest.parent / "item_0001.json").exists())

    def test_run_workflow_config_filters_google_news_rss_items(self) -> None:
        config = {
            "name": "google",
            "start_url": "https://news.google.com/rss/search?q={search_term}&hl=ko&gl=KR&ceid=KR:ko",
            "output_dir": "outputs/google",
            "timeout_ms": 1000,
            "search_terms": ["SK이노베이션"],
            "filter_terms": ["SK"],
            "steps": [
                {
                    "name": "google_rss",
                    "action": "parser",
                    "attr": "google",
                }
            ],
        }
        rss_items = [
            {
                "post_id": "guid-1",
                "title": "SK이노베이션, 1분기 실적 발표",
                "detail_url": "https://example.com/article-1",
                "link": "https://example.com/article-1",
                "pubDate": "Tue, 29 Apr 2026 09:00:00 +0900",
                "source": "예시뉴스",
                "source_url": "https://news.example.com",
                "description": "요약 문장",
                "guid": "guid-1",
            },
            {
                "post_id": "guid-2",
                "title": "정유 업황 점검",
                "detail_url": "https://example.com/article-2",
                "link": "https://example.com/article-2",
                "pubDate": "Tue, 29 Apr 2026 10:00:00 +0900",
                "source": "예시뉴스",
                "source_url": "https://news.example.com",
                "description": "요약 문장 2",
                "guid": "guid-2",
            },
        ]

        with temporary_project_output_dir() as tmp_dir:
            config["output_dir"] = str(Path(tmp_dir) / "google")
            with patch(
                "crawler_app.workflow.fetch_google_news_rss_items",
                return_value=(rss_items, "https://news.google.com/rss/search?q=SK%EC%9D%B4%EB%85%B8%EB%B2%A0%EC%9D%B4%EC%85%98&hl=ko&gl=KR&ceid=KR:ko"),
            ):
                execution = run_workflow_config(config)

            self.assertTrue(execution.success)
            self.assertEqual(len(execution.records), 1)
            self.assertEqual(execution.diagnostics["matched_record_count"], 1)
            self.assertEqual(execution.diagnostics["nonfilter_record_count"], 1)
            matched_path = Path(execution.diagnostics["matched_output_files"][0])
            nonfilter_path = Path(execution.diagnostics["nonfilter_records_file"])
            self.assertTrue(matched_path.exists())
            self.assertTrue(nonfilter_path.exists())
            self.assertIn("filter", matched_path.parts)
            self.assertIn("nonfilter", nonfilter_path.parts)
            self.assertEqual(execution.records[0]["record_key"], "term001_item001")
            self.assertTrue(Path(execution.records[0]["output_file"]).exists())

            matched_manifest = json.loads(matched_path.read_text(encoding="utf-8"))
            matched_item = json.loads((matched_path.parent / matched_manifest["item_files"][0]).read_text(encoding="utf-8"))
            nonfilter_payload = json.loads(nonfilter_path.read_text(encoding="utf-8"))
            self.assertEqual(matched_item["title"], "SK이노베이션, 1분기 실적 발표")
            self.assertEqual(nonfilter_payload["records"][0]["extracts"]["title"], "정유 업황 점검")

    def test_preview_workflow_config_reports_parser_item_count(self) -> None:
        config = {
            "name": "google",
            "start_url": "https://news.google.com/rss/search?q={search_term}&hl=ko&gl=KR&ceid=KR:ko",
            "output_dir": "outputs/google",
            "search_terms": ["최태원"],
            "steps": [
                {
                    "name": "google_rss",
                    "action": "parser",
                    "attr": "google",
                }
            ],
        }

        with patch(
            "crawler_app.workflow.fetch_google_news_rss_items",
            return_value=(
                [
                    {
                        "post_id": "guid-1",
                        "title": "첫 기사",
                        "detail_url": "https://example.com/article-1",
                        "link": "https://example.com/article-1",
                        "pubDate": "Tue, 29 Apr 2026 09:00:00 +0900",
                        "source": "예시뉴스",
                        "source_url": "https://news.example.com",
                        "description": "요약 문장",
                        "guid": "guid-1",
                    }
                ],
                "https://news.google.com/rss/search?q=%EC%B5%9C%ED%83%9C%EC%9B%90&hl=ko&gl=KR&ceid=KR:ko",
            ),
        ):
            preview = preview_workflow_config(config)

        self.assertEqual(preview["parser_name"], "google")
        self.assertEqual(preview["parser_item_count"], 1)
        self.assertEqual(preview["step_counts"][0]["count"], 1)

    def test_preview_workflow_config_limits_parser_item_count(self) -> None:
        config = {
            "name": "google",
            "start_url": "https://news.google.com/rss/search?q={search_term}&hl=ko&gl=KR&ceid=KR:ko",
            "output_dir": "outputs/google",
            "search_terms": ["최태원"],
            "steps": [
                {
                    "name": "google_rss",
                    "action": "parser",
                    "attr": "google",
                    "loop_limit": 2,
                }
            ],
        }

        with patch(
            "crawler_app.workflow.fetch_google_news_rss_items",
            return_value=(
                [
                    {
                        "post_id": "guid-1",
                        "title": "첫 기사",
                        "detail_url": "https://example.com/article-1",
                        "link": "https://example.com/article-1",
                        "pubDate": "Tue, 29 Apr 2026 09:00:00 +0900",
                        "source": "예시뉴스",
                        "source_url": "https://news.example.com",
                        "description": "요약 문장",
                        "guid": "guid-1",
                    },
                    {
                        "post_id": "guid-2",
                        "title": "둘째 기사",
                        "detail_url": "https://example.com/article-2",
                        "link": "https://example.com/article-2",
                        "pubDate": "Tue, 29 Apr 2026 10:00:00 +0900",
                        "source": "예시뉴스",
                        "source_url": "https://news.example.com",
                        "description": "요약 문장 2",
                        "guid": "guid-2",
                    },
                ],
                "https://news.google.com/rss/search?q=%EC%B5%9C%ED%83%9C%EC%9B%90&hl=ko&gl=KR&ceid=KR:ko",
            ),
        ):
            preview = preview_workflow_config(config)

        self.assertEqual(preview["parser_item_count"], 2)
        self.assertEqual(preview["step_counts"][0]["loop_limit"], 2)
        self.assertEqual(preview["step_counts"][0]["count"], 2)

    def test_normalize_workflow_config_converts_legacy_click_goto_to_goto_action(self) -> None:
        config = {
            "name": "sample",
            "start_url": "https://example.com",
            "output_dir": "outputs/sample",
            "steps": [
                {
                    "name": "open",
                    "xpath": "//a[1]",
                    "action": "click",
                    "open_mode": "goto",
                    "attr": "src",
                }
            ],
        }

        normalized = normalize_workflow_config(config)

        self.assertEqual(normalized["steps"][0]["action"], "goto")
        self.assertEqual(normalized["steps"][0]["attr"], "src")
        self.assertNotIn("open_mode", normalized["steps"][0])

    def test_normalize_workflow_config_drops_click_attr_values(self) -> None:
        config = {
            "name": "sample",
            "start_url": "https://example.com",
            "output_dir": "outputs/sample",
            "steps": [
                {
                    "name": "open",
                    "xpath": "//a[1]",
                    "action": "click",
                    "open_mode": "same_tab",
                    "attr": "href",
                }
            ],
        }

        normalized = normalize_workflow_config(config)

        self.assertEqual(normalized["steps"][0]["action"], "click")
        self.assertEqual(normalized["steps"][0]["open_mode"], "same_tab")
        self.assertNotIn("attr", normalized["steps"][0])

    def test_run_step_click_skips_excluded_locator_candidates(self) -> None:
        page = FakeStepLoopPage({"xpath=//a": [FakeLocator("/notice", exclude_match=True), FakeLocator("/detail")]})
        step = {
            "name": "open",
            "xpath": "//a",
            "action": "click",
            "exclude_xpath": ".//span[contains(., '공지')]",
        }

        log, _ = _run_step(
            page=page,
            scope=None,
            step=step,
            step_index=1,
            output_dir=Path(tempfile.gettempdir()),
            timeout_ms=1000,
            step_wait_ms=1000,
            item_index=None,
            search_term=None,
            search_term_index=None,
            search_term_count=None,
            primary_loop_step_index=None,
            parse_pause_seconds=0,
        )

        self.assertTrue(log["success"])
        self.assertEqual(log["matched_count"], 1)
        self.assertFalse(page.selectors["xpath=//a"][0].clicked)
        self.assertTrue(page.selectors["xpath=//a"][1].clicked)

    def test_run_step_click_supports_absolute_exclude_xpath(self) -> None:
        page = FakeStepLoopPage({"xpath=//a": [FakeLocator("/notice", evaluate_result=True), FakeLocator("/detail")]})
        step = {
            "name": "open",
            "xpath": "//a",
            "action": "click",
            "exclude_xpath": "//*[@id='frontBoardVo']/div[1]/table/tbody/tr[1]/td[1]/em",
        }

        log, _ = _run_step(
            page=page,
            scope=None,
            step=step,
            step_index=1,
            output_dir=Path(tempfile.gettempdir()),
            timeout_ms=1000,
            step_wait_ms=1000,
            item_index=None,
            search_term=None,
            search_term_index=None,
            search_term_count=None,
            primary_loop_step_index=None,
            parse_pause_seconds=0,
        )

        self.assertTrue(log["success"])
        self.assertEqual(log["matched_count"], 1)
        self.assertFalse(page.selectors["xpath=//a"][0].clicked)
        self.assertTrue(page.selectors["xpath=//a"][1].clicked)

    def test_load_workflow_config_normalizes_legacy_click_goto_to_href_when_attr_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sample.json"
            path.write_text(
                """
                {
                  "name": "sample",
                  "start_url": "https://example.com",
                  "output_dir": "outputs/sample",
                  "steps": [
                    {
                      "name": "open",
                      "xpath": "//a[1]",
                      "action": "click",
                      "open_mode": "goto"
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )

            loaded = load_workflow_config(path)

            self.assertEqual(loaded["steps"][0]["action"], "goto")
            self.assertEqual(loaded["steps"][0]["attr"], "href")
            self.assertNotIn("open_mode", loaded["steps"][0])

    def test_load_workflow_config_preserves_notes_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sample.json"
            path.write_text(
                """
                {
                  "name": "sample",
                  "notes": "상세페이지와 목록 xpath가 동일해서 본문 전용 selector 사용",
                  "start_url": "https://example.com",
                  "output_dir": "outputs/sample",
                  "steps": [
                    {
                      "name": "open",
                      "xpath": "//a[1]",
                      "action": "click"
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )

            loaded = load_workflow_config(path)

            self.assertEqual(
                loaded["notes"],
                "상세페이지와 목록 xpath가 동일해서 본문 전용 selector 사용",
            )

    def test_config_search_terms_normalizes_blank_entries(self) -> None:
        config = {"search_terms": ["  climate  ", "", None, "energy"]}

        self.assertEqual(_config_search_terms(config), ["climate", "energy"])

    def test_config_filter_terms_normalizes_blank_entries(self) -> None:
        config = {"filter_terms": ["  SK  ", "", None, "유가"]}

        self.assertEqual(_config_filter_terms(config), ["SK", "유가"])

    def test_apply_workflow_result_filters_splits_records_and_writes_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "sample"
            execution = WorkflowExecution(
                config_name="sample",
                output_dir=output_dir,
                records=[
                    {
                        "search_term": "sample",
                        "search_term_index": 0,
                        "item_index": 0,
                        "steps": [],
                        "extracts": {"title": "SK이노베이션 실적", "source": "뉴스"},
                        "downloaded_files": [str(output_dir / "downloads" / "a.pdf")],
                        "extracted_files": [str(output_dir / "texts" / "a.txt")],
                    },
                    {
                        "search_term": "sample",
                        "search_term_index": 0,
                        "item_index": 1,
                        "steps": [],
                        "extracts": {"title": "정유 업황 점검", "source": "뉴스"},
                        "downloaded_files": [str(output_dir / "downloads" / "b.pdf")],
                        "extracted_files": [str(output_dir / "texts" / "b.txt")],
                    },
                ],
            )
            config = {
                "name": "sample",
                "output_dir": str(execution.output_dir),
                "filter_terms": ["SK"],
                "steps": [{"name": "open", "xpath": "//a[1]", "action": "click"}],
            }

            _apply_workflow_result_filters(execution, config)

            self.assertEqual(len(execution.records), 1)
            self.assertEqual(execution.diagnostics["raw_record_count"], 2)
            self.assertEqual(execution.diagnostics["matched_record_count"], 1)
            self.assertEqual(execution.diagnostics["nonfilter_record_count"], 1)
            self.assertEqual(execution.downloaded_files, [str(output_dir / "filter" / "downloads" / "a.pdf")])
            self.assertEqual(execution.extracted_files, [str(output_dir / "filter" / "texts" / "a.txt")])
            self.assertIn("filter", Path(execution.diagnostics["matched_records_file"]).parts)
            self.assertIn("nonfilter", Path(execution.diagnostics["nonfilter_records_file"]).parts)
            self.assertTrue(Path(execution.diagnostics["matched_records_file"]).exists())
            self.assertTrue(Path(execution.diagnostics["nonfilter_records_file"]).exists())

    def test_config_primary_loop_step_index_uses_first_loop_step_anywhere(self) -> None:
        config = {
            "steps": [
                {"name": "search", "xpath": "//input", "action": "click"},
                {"name": "open", "xpath": "//a[1]", "xpath_2": "//a[2]", "action": "click", "loop": True},
                {"name": "download", "xpath": "//a[@href]", "action": "download", "loop": True, "xpath_2": "//a[@href]"},
            ]
        }

        self.assertEqual(_config_primary_loop_step_index(config), 2)

    def test_config_primary_loop_mode_detects_pagination(self) -> None:
        config = {
            "steps": [
                {"name": "page", "xpath": "//*[@id='frontBoardVo']/div[2]/a[{page_number}]", "action": "click", "loop": True, "loop_mode": "pagination", "pagination_mode": "page_number"},
                {"name": "download", "xpath": "//a[@href]", "action": "download"},
            ]
        }

        self.assertEqual(_config_primary_loop_mode(config), "pagination")

    def test_config_click_loop_step_indexes_uses_first_two_click_loops(self) -> None:
        config = {
            "steps": [
                {"name": "page", "xpath": "//a[1]", "xpath_2": "//a[2]", "action": "click", "loop": True},
                {"name": "item", "xpath": "//li[1]/a", "xpath_2": "//li[2]/a", "action": "click", "loop": True},
                {"name": "download", "xpath": "//a[@href]", "action": "download", "loop": True, "xpath_2": "//a[@href]"},
            ]
        }

        self.assertEqual(_config_click_loop_step_indexes(config), (1, 2))

    def test_run_nested_click_loops_prepends_page_loop_step_to_record_steps(self) -> None:
        config = {
            "start_url": "https://example.com/start",
            "output_dir": "outputs/test",
            "steps": [
                {
                    "name": "page",
                    "xpath": "//*[@id='board']/ul/li[1]/a",
                    "xpath_2": "//*[@id='board']/ul/li[2]/a",
                    "action": "click",
                    "loop": True,
                },
                {
                    "name": "item",
                    "xpath": "//*[@id='board']/ul/li[1]/a",
                    "xpath_2": "//*[@id='board']/ul/li[2]/a",
                    "action": "click",
                    "loop": True,
                },
            ],
        }
        page_step_log = {
            "index": 1,
            "name": "page",
            "url_before": "https://example.com/start",
            "url_after": "https://example.com/listing",
            "matched_count": 3,
            "success": True,
            "error": None,
        }
        item_record = {
            "item_index": 0,
            "search_term": None,
            "search_term_index": 0,
            "search_term_count": 1,
            "success": True,
            "steps": [
                {
                    "index": 2,
                    "name": "item",
                    "url_before": "https://example.com/listing",
                    "url_after": "https://example.com/detail",
                    "matched_count": 1,
                    "success": True,
                    "error": None,
                }
            ],
            "extracts": {},
            "downloaded_files": [],
            "extracted_files": [],
            "error": None,
            "start_url": "https://example.com/start",
            "final_url": "https://example.com/detail",
        }

        class FakeNestedBrowser:
            def new_page(self, accept_downloads: bool = True) -> FakeLoopPage:
                return FakeLoopPage({})

        step_page = FakeLoopPage({})
        with patch("crawler_app.workflow._resolve_page_loop_count", return_value=1), patch(
            "crawler_app.workflow._resolve_board_loop_item_numbers", return_value=[1]
        ), patch("crawler_app.workflow._run_step", return_value=(page_step_log, step_page)), patch(
            "crawler_app.workflow._run_one_item", return_value=item_record
        ):
            records = _run_nested_click_loops(
                browser=FakeNestedBrowser(),
                config=config,
                search_term=None,
                search_term_index=0,
                search_term_count=1,
                output_dir=Path(tempfile.gettempdir()),
                timeout_ms=1000,
                step_wait_ms=1000,
                parse_pause_seconds=0,
                page_loop_step_index=1,
                item_loop_step_index=2,
            )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["steps"][0], page_step_log)
        self.assertEqual(records[0]["steps"][1]["index"], 2)

    def test_run_nested_pagination_click_loops_processes_each_page_and_item(self) -> None:
        config = {
            "start_url": "https://crckorea.kr/?menuno=229&display=Y",
            "output_dir": "outputs/crkorea",
            "steps": [
                {
                    "name": "페이징",
                    "xpath": "//*[@id='frontBoardVo']/div[2]/a[11]",
                    "action": "click",
                    "loop": True,
                    "loop_mode": "pagination",
                    "pagination_mode": "next_button",
                },
                {
                    "name": "상세열기",
                    "xpath": "/html/body/section[3]/div/section/form/div[1]/table/tbody/tr[1]/td[3]/a",
                    "xpath_2": "/html/body/section[3]/div/section/form/div[1]/table/tbody/tr[2]/td[3]/a",
                    "action": "click",
                    "loop": True,
                    "wait_state": "attached",
                },
                {
                    "name": "본문다운로드",
                    "xpath": "//*[@id='report']",
                    "action": "extract",
                    "attr": "text",
                    "wait_state": "attached",
                },
            ],
        }
        page_step_logs: list[dict[str, object]] = []
        item_calls: list[tuple[int, str, int, int]] = []
        pages = [FakeLoopPage({}), FakeLoopPage({})]

        def fake_new_page(browser: object) -> FakeLoopPage:
            return pages.pop(0)

        def fake_run_step(
            page: FakeLoopPage,
            scope: object,
            step: dict[str, object],
            step_index: int,
            output_dir: Path,
            timeout_ms: int,
            step_wait_ms: int,
            item_index: int | None,
            **kwargs,
        ) -> tuple[dict[str, object], FakeLoopPage]:
            page_number = int(kwargs.get("board_page_number") or ((item_index or 0) + 1))
            page.url = f"https://crkorea.kr/index.html?menuno=229&page={page_number}"
            log = {
                "index": step_index,
                "name": step["name"],
                "item_index": item_index,
                "success": True,
                "error": None,
                "open_mode": "auto",
                "matched_count": 1,
                "url_before": "https://crckorea.kr/?menuno=229&display=Y",
                "url_after": page.url,
                "downloaded_files": [],
                "steps": [],
                "pagination_target_page": page_number if step.get("loop") else None,
            }
            page_step_logs.append(log)
            return log, page

        def fake_run_one_item(
            browser: object,
            config_arg: dict[str, object],
            item_index: int | None,
            timeout_ms: int,
            step_wait_ms: int,
            **kwargs,
        ) -> dict[str, object]:
            start_url = str(kwargs["start_url_override"])
            board_item_number = int(kwargs["board_item_number"])
            start_step_index = int(kwargs["start_step_index"])
            item_calls.append((item_index or 0, start_url, start_step_index, board_item_number))
            return {
                "item_index": item_index,
                "search_term": None,
                "search_term_index": 0,
                "search_term_count": 1,
                "success": True,
                "steps": [
                    {
                        "index": 2,
                        "name": "상세열기",
                        "success": True,
                        "error": None,
                    }
                ],
                "extracts": {},
                "downloaded_files": [],
                "extracted_files": [],
                "error": None,
                "start_url": start_url,
                "final_url": f"{start_url}/detail/{board_item_number}",
            }

        with patch("crawler_app.workflow._new_workflow_page", side_effect=fake_new_page), patch(
            "crawler_app.workflow._resolve_item_numbers_for_term", return_value=[1, 2]
        ), patch("crawler_app.workflow._resolve_board_loop_item_numbers", return_value=[1, 2]), patch(
            "crawler_app.workflow._run_step", side_effect=fake_run_step
        ), patch("crawler_app.workflow._run_one_item", side_effect=fake_run_one_item):
            records = _run_nested_pagination_click_loops(
                browser=object(),
                config=config,
                search_term=None,
                search_term_index=0,
                search_term_count=1,
                output_dir=Path(tempfile.gettempdir()),
                timeout_ms=1000,
                step_wait_ms=1000,
                parse_pause_seconds=0,
                page_loop_step_index=1,
                item_loop_step_index=2,
            )

        self.assertEqual(len(records), 4)
        self.assertEqual(item_calls[0], (0, "https://crkorea.kr/index.html?menuno=229&page=1", 2, 1))
        self.assertEqual(item_calls[-1], (1, "https://crkorea.kr/index.html?menuno=229&page=2", 2, 2))
        self.assertEqual(records[0]["steps"][0]["pagination_target_page"], 1)
        self.assertEqual(records[2]["steps"][0]["pagination_target_page"], 2)
        self.assertEqual(records[0]["steps"][1]["index"], 2)
        self.assertEqual(records[0]["start_url"], "https://crkorea.kr/index.html?menuno=229&page=1")

    def test_finalize_workflow_execution_marks_empty_loop_as_error(self) -> None:
        config = {
            "name": "중국세관",
            "steps": [
                {"name": "open_detail", "xpath": "//a[1]", "xpath_2": "//a[2]", "action": "click", "loop": True}
            ],
        }
        execution = WorkflowExecution(config_name="중국세관", output_dir=Path(tempfile.gettempdir()))

        _finalize_workflow_execution(execution, config)

        self.assertEqual(execution.error, "No items matched configured loop for 중국세관.")
        self.assertEqual(execution.diagnostics["error_type"], "NoItemsMatchedError")
        self.assertEqual(execution.diagnostics["error"], "No items matched configured loop for 중국세관.")

    def test_attach_dialog_handler_accepts_multiple_dialogs(self) -> None:
        page = FakeDialogPage()
        dialog_one = FakeDialog()
        dialog_two = FakeDialog()

        _attach_dialog_handler(page)
        page.emit_dialog(dialog_one)
        page.emit_dialog(dialog_two)

        self.assertEqual(dialog_one.accept_count, 1)
        self.assertEqual(dialog_two.accept_count, 1)
        self.assertEqual(dialog_one.dismiss_count, 0)
        self.assertEqual(dialog_two.dismiss_count, 0)

    def test_run_step_click_popup_switches_to_popup_page(self) -> None:
        popup_page = FakePopupPage(url="https://example.com/detail")
        page = FakeStepLoopPage({"xpath=//a": [FakeLocator("/detail", target="_blank")]}, popup_page=popup_page)
        step = {"name": "open", "xpath": "//a", "action": "click", "open_mode": "popup"}

        log, active_page = _run_step(
            page=page,
            scope=None,
            step=step,
            step_index=1,
            output_dir=Path(tempfile.gettempdir()),
            timeout_ms=1000,
            step_wait_ms=1000,
            item_index=None,
            search_term=None,
            search_term_index=None,
            search_term_count=None,
            primary_loop_step_index=None,
            parse_pause_seconds=0,
        )

        self.assertTrue(log["success"])
        self.assertIs(active_page, popup_page)
        self.assertEqual(log["url_after"], "https://example.com/detail")
        self.assertEqual(popup_page.waited_for, "domcontentloaded")

    def test_download_uses_request_when_href_is_real_url(self) -> None:
        response = FakeResponse(
            body=b"pdf-bytes",
            headers={"Content-Disposition": 'attachment; filename="sample.pdf"'},
        )
        request = FakeRequest(response)
        page = FakePage(request, FakeDownload("unused.pdf"))
        locator = FakeLocator("https://example.com/sample.pdf")

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = _download_step(
                page=page,
                locator=locator,
                step={"attr": "href"},
                output_dir=Path(tmp_dir),
                timeout_ms=1000,
            )

            self.assertTrue(result.exists())
            self.assertEqual(result.read_bytes(), b"pdf-bytes")
            self.assertEqual(request.calls, [("https://example.com/sample.pdf", 1000)])
            self.assertFalse(locator.clicked)
            self.assertTrue(result.name.startswith("record_step01_download_"))

    def test_download_switches_to_click_for_javascript_href(self) -> None:
        response = FakeResponse(body=b"should-not-be-used")
        request = FakeRequest(response)

        class StrictRequest(FakeRequest):
            def get(self, url: str, timeout: int | None = None) -> FakeResponse:
                raise AssertionError("request.get should not be called for javascript href")

        request = StrictRequest(response)
        download = FakeDownload("attached-file.pdf", b"download-bytes")
        page = FakePage(request, download)
        locator = FakeLocator("javascript:ajaxFileDownLoad('322492','2');")

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = _download_step(
                page=page,
                locator=locator,
                step={"attr": "href"},
                output_dir=Path(tmp_dir),
                timeout_ms=1000,
            )

            self.assertTrue(locator.clicked)
            self.assertTrue(result.exists())
            self.assertEqual(result.read_bytes(), b"download-bytes")
            self.assertEqual(download.saved_to, str(result))
            self.assertTrue(result.name.startswith("record_step01_download_"))

    def test_download_multiple_step_downloads_each_unique_href(self) -> None:
        response = FakeResponse(
            body=b"pdf-bytes",
            headers={"Content-Disposition": 'attachment; filename="sample.pdf"'},
        )
        request = FakeRequest(response)
        page = FakePage(request, FakeDownload("unused.pdf"))
        locators = FakeLocatorGroup(
            [
                FakeLocator("https://example.com/a.pdf"),
                FakeLocator("https://example.com/b.pdf"),
            ]
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            results = _download_multiple_step(
                page=page,
                locator_group=locators,
                step={"attr": "href"},
                output_dir=Path(tmp_dir),
                timeout_ms=1000,
            )

            self.assertEqual(len(results), 2)
            self.assertTrue(all(path.exists() for path in results))
            self.assertEqual(
                request.calls,
                [
                    ("https://example.com/a.pdf", 1000),
                ("https://example.com/b.pdf", 1000),
                ],
            )

    def test_download_loop_step_downloads_each_anchor_until_missing(self) -> None:
        loop_spec = BoardLoopSpec(
            anchor_xpath_1="//*[@id='board']/ul/li[1]/a",
            anchor_xpath_2="//*[@id='board']/ul/li[2]/a",
            root_xpath="//*[@id='board']/ul",
            item_segment_template="li[{item_number}]",
            item_tag="li",
            suffix_segments=("a",),
            start_index=1,
        )
        page = FakeStepLoopPage(
            {
                "xpath=//*[@id='board']/ul/li[1]/a": [FakeLocator("https://example.com/a.pdf")],
                "xpath=//*[@id='board']/ul/li[2]/a": [FakeLocator("https://example.com/b.pdf")],
                "xpath=//*[@id='board']/ul/li[3]/a": [FakeLocator("https://example.com/c.pdf")],
                "xpath=//*[@id='board']/ul/li[4]/a": [],
            }
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = _download_loop_step(
                page=page,
                step={"attr": "href"},
                output_dir=Path(tmp_dir),
                timeout_ms=1000,
                loop_spec=loop_spec,
            )

            self.assertEqual(len(result), 3)
            self.assertTrue(all(path.exists() for path in result))

    def test_download_loop_step_honors_loop_limit(self) -> None:
        loop_spec = BoardLoopSpec(
            anchor_xpath_1="//*[@id='board']/ul/li[1]/a",
            anchor_xpath_2="//*[@id='board']/ul/li[2]/a",
            root_xpath="//*[@id='board']/ul",
            item_segment_template="li[{item_number}]",
            item_tag="li",
            suffix_segments=("a",),
            start_index=1,
        )
        page = FakeStepLoopPage(
            {
                "xpath=//*[@id='board']/ul/li[1]/a": [FakeLocator("https://example.com/a.pdf")],
                "xpath=//*[@id='board']/ul/li[2]/a": [FakeLocator("https://example.com/b.pdf")],
                "xpath=//*[@id='board']/ul/li[3]/a": [FakeLocator("https://example.com/c.pdf")],
                "xpath=//*[@id='board']/ul/li[4]/a": [],
            }
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = _download_loop_step(
                page=page,
                step={"attr": "href", "loop_limit": 2},
                output_dir=Path(tmp_dir),
                timeout_ms=1000,
                loop_spec=loop_spec,
            )

            self.assertEqual(len(result), 2)
            self.assertTrue(all(path.exists() for path in result))

    def test_save_extract_outputs_writes_txt_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = _save_extract_outputs(
                output_dir=Path(tmp_dir),
                item_index=0,
                step_index=1,
                step={"name": "extract_body"},
                value="hello world",
                page_title="기후에너지환경부 보도자료",
                is_html=False,
            )

            self.assertEqual(len(paths), 1)
            path = paths[0]
            self.assertTrue(path.exists())
            self.assertEqual(path.suffix, ".txt")
            self.assertEqual(path.read_text(encoding="utf-8"), "hello world")
            self.assertTrue(path.name.startswith("record_item_1_extract_body_"))
            self.assertIn("기후에너지환경부 보도자료", path.name)

    def test_save_extract_outputs_writes_html_and_text_for_html_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = _save_extract_outputs(
                output_dir=Path(tmp_dir),
                item_index=0,
                step_index=1,
                step={"name": "extract_body"},
                value="<div><p>Hello</p></div>",
                page_title="기후에너지환경부 보도자료",
                is_html=True,
            )

            self.assertEqual(len(paths), 2)
            self.assertEqual(paths[0].suffix, ".txt")
            self.assertEqual(paths[1].suffix, ".html")
            self.assertEqual(paths[0].read_text(encoding="utf-8"), "Hello")
            self.assertEqual(paths[1].read_text(encoding="utf-8"), "<div><p>Hello</p></div>")
            self.assertTrue(paths[0].name.startswith("record_item_1_extract_body_"))
            self.assertIn("기후에너지환경부 보도자료", paths[0].name)

    def test_save_extract_outputs_falls_back_without_page_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = _save_extract_outputs(
                output_dir=Path(tmp_dir),
                item_index=None,
                step_index=3,
                step={"name": "parse"},
                value="hello world",
                page_title="",
                is_html=False,
            )

            self.assertEqual(len(paths), 1)
            self.assertEqual(paths[0].name, "record_single_parse.txt")


if __name__ == "__main__":
    unittest.main()
