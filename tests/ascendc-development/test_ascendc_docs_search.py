#!/usr/bin/env python3
"""Offline regression tests for the Ascend documentation search client."""

from __future__ import annotations

import importlib.util
import io
import json
import pathlib
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "plugins"
    / "ascendc-development"
    / "skills"
    / "ascendc-docs-search"
    / "scripts"
    / "search_ascend_docs.py"
)
SPEC = importlib.util.spec_from_file_location("search_ascend_docs", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load {SCRIPT}")
SEARCH = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SEARCH
SPEC.loader.exec_module(SEARCH)


class SearchAscendDocsTest(unittest.TestCase):
    def test_resource_limits_are_explicit_and_bounded(self) -> None:
        self.assertEqual(SEARCH.SEARCH_PAGE_SIZE, 10)
        self.assertEqual(SEARCH.MAX_SEARCH_PAGES, 10)
        self.assertEqual(SEARCH.MAX_SEARCH_RESPONSE_BYTES, 1024 * 1024)
        self.assertEqual(SEARCH.MAX_DOCUMENT_RESPONSE_BYTES, 4 * 1024 * 1024)
        self.assertEqual(SEARCH.MAX_FULL_CONTENT_CHARS, 200_000)
        self.assertEqual(SEARCH.MAX_CODE_BLOCK_CHARS, 20_000)

    def test_document_request_uses_current_canonical_referer(self) -> None:
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.geturl.return_value = SEARCH.DOCUMENT_URL
        response.headers.get_content_charset.return_value = "utf-8"
        response.read.return_value = b"{}"
        with mock.patch.object(SEARCH.OFFICIAL_OPENER, "open", return_value=response) as opener:
            SEARCH._get(SEARCH.DOCUMENT_URL, 1)
        request = opener.call_args.args[0]
        self.assertEqual(request.get_header("Referer"), SEARCH.DOCUMENT_URL)

    def test_search_session_initializes_csrf_token(self) -> None:
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.geturl.return_value = SEARCH.SESSION_URL
        response.headers.get_content_charset.return_value = "utf-8"
        response.headers.get.return_value = "csrf-token"
        response.read.return_value = b'{"code":401,"success":false}'

        with mock.patch.object(SEARCH.OFFICIAL_OPENER, "open", return_value=response) as opener:
            token = SEARCH._initialize_search_session(1)

        request = opener.call_args.args[0]
        self.assertEqual(request.full_url, SEARCH.SESSION_URL)
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("Referer"), SEARCH.DOCUMENT_URL)
        self.assertEqual(token, "csrf-token")

    def test_search_session_requires_next_token(self) -> None:
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.geturl.return_value = SEARCH.SESSION_URL
        response.headers.get_content_charset.return_value = "utf-8"
        response.headers.get.return_value = None
        response.read.return_value = b'{"code":401,"success":false}'

        with mock.patch.object(SEARCH.OFFICIAL_OPENER, "open", return_value=response):
            with self.assertRaisesRegex(SEARCH.DocsSearchError, "session token"):
                SEARCH._initialize_search_session(1)

    def test_search_request_posts_json_with_csrf_token(self) -> None:
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.geturl.return_value = SEARCH.SEARCH_URL
        response.headers.get_content_charset.return_value = "utf-8"
        response.headers.get.return_value = "rotated-token"
        response.read.return_value = b'{"code":200,"data":{"data":[]}}'
        payload = {"keyword": "RGF0YUNvcHk", "lang": "zh", "pageNum": 1}

        with mock.patch.object(SEARCH.OFFICIAL_OPENER, "open", return_value=response) as opener:
            result = SEARCH._search_request(payload, "csrf-token", 1)

        request = opener.call_args.args[0]
        self.assertEqual(request.full_url, SEARCH.SEARCH_URL)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("X-csrf-token"), "csrf-token")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(json.loads(request.data), payload)
        self.assertEqual(result[3], "rotated-token")

    def test_body_read_timeout_is_a_document_error(self) -> None:
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.geturl.return_value = "https://www.hiascend.com/document/detail/example.html"
        response.headers.get_content_charset.return_value = "utf-8"
        response.read.side_effect = TimeoutError("timed out")
        with mock.patch.object(SEARCH.OFFICIAL_OPENER, "open", return_value=response):
            with self.assertRaisesRegex(SEARCH.DocsSearchError, "request timed out"):
                SEARCH._get("https://www.hiascend.com/document/detail/example.html", 1)

    def test_official_url_transforms_source_path_and_encodes_unicode(self) -> None:
        actual = SEARCH._official_url(
            "/source/zh/CANNCommunityEdition/910beta3/API/ascendcopapi/"
            "算子 API.html"
        )
        self.assertEqual(
            actual,
            "https://www.hiascend.com/document/detail/zh/"
            "CANNCommunityEdition/910beta3/API/ascendcopapi/"
            "%E7%AE%97%E5%AD%90%20API.html",
        )

    def test_official_url_rejects_other_hosts_userinfo_and_non_https_port(self) -> None:
        with self.assertRaises(SEARCH.DocsSearchError):
            SEARCH._official_url("https://example.com/document/detail/example.html")
        with self.assertRaises(SEARCH.DocsSearchError):
            SEARCH._official_url("https://user@www.hiascend.com/document/detail/example.html")
        with self.assertRaises(SEARCH.DocsSearchError):
            SEARCH._official_url("https://www.hiascend.com:444/document/detail/example.html")

        self.assertEqual(
            SEARCH._official_url("https://www.hiascend.com:443/document/detail/example.html"),
            "https://www.hiascend.com:443/document/detail/example.html",
        )

    def test_redirect_handler_rejects_cross_host_before_following(self) -> None:
        request = SEARCH.Request("https://www.hiascend.com/document/detail/start.html")
        handler = SEARCH.OfficialRedirectHandler()
        with self.assertRaises(SEARCH.DocsSearchError):
            handler.redirect_request(
                request,
                None,
                302,
                "Found",
                {},
                "https://example.com/untrusted.html",
            )

    def test_version_matching_distinguishes_final_beta_and_release_candidate(self) -> None:
        self.assertTrue(SEARCH._version_matches("9.0.0", "9.0"))
        self.assertTrue(SEARCH._version_matches("9.0", "9.0.0"))
        self.assertTrue(SEARCH._version_matches("9.1.0-beta.3", "9.1.0-BETA.3"))
        self.assertTrue(SEARCH._version_matches("9.1.0-beta.3", "CANN V9.1.0 beta 3"))
        self.assertTrue(SEARCH._version_matches("9.1.0-beta", "CANN 9.1.0 BETA"))
        self.assertTrue(SEARCH._version_matches("9.1.0-RC1", "9.1.0-rc1"))
        self.assertTrue(SEARCH._version_matches("9.1.0-RC", "9.1.0-rc"))
        self.assertFalse(SEARCH._version_matches("9.1.0-beta.3", "9.1.0"))
        self.assertFalse(SEARCH._version_matches("9.1.0-beta", "9.1.0"))
        self.assertFalse(SEARCH._version_matches("9.1.0-RC", "9.1.0"))
        self.assertFalse(SEARCH._version_matches("9.1.0", "9.1.0-beta.3"))
        self.assertFalse(SEARCH._version_matches("9.1.0-RC1", "9.1.0-RC2"))
        self.assertFalse(SEARCH._version_matches("9.0.1", "9.0"))

    def test_search_rejects_non_object_json_shapes(self) -> None:
        for payload in ([], {"success": True, "data": []}):
            with self.subTest(payload=payload):
                with (
                    mock.patch.object(
                        SEARCH, "_initialize_search_session", return_value="token"
                    ),
                    mock.patch.object(
                        SEARCH,
                        "_search_request",
                        return_value=(
                            json.dumps(payload).encode(),
                            "utf-8",
                            SEARCH.SEARCH_URL,
                            None,
                        ),
                    ),
                ):
                    with self.assertRaisesRegex(SEARCH.DocsSearchError, "unexpected data shape"):
                        SEARCH.search_documents(
                            "DataCopy",
                            lang="zh",
                            doc_type="DOC",
                            page=1,
                            max_results=1,
                            version=None,
                            timeout=1,
                        )

    def test_search_treats_successful_null_data_as_no_results(self) -> None:
        response = {"code": 200, "msg": "success", "data": None}
        with (
            mock.patch.object(SEARCH, "_initialize_search_session", return_value="token"),
            mock.patch.object(
                SEARCH,
                "_search_request",
                return_value=(
                    json.dumps(response).encode(),
                    "utf-8",
                    SEARCH.SEARCH_URL,
                    None,
                ),
            ),
        ):
            results = SEARCH.search_documents(
                "no matching document",
                lang="zh",
                doc_type="DOC",
                page=1,
                max_results=1,
                version=None,
                timeout=1,
            )

        self.assertEqual(results, [])

    def test_search_reports_unsupported_charset_as_structured_error(self) -> None:
        with (
            mock.patch.object(SEARCH, "_initialize_search_session", return_value="token"),
            mock.patch.object(
                SEARCH,
                "_search_request",
                return_value=(b"{}", "not-a-codec", SEARCH.SEARCH_URL, None),
            ),
        ):
            with self.assertRaisesRegex(SEARCH.DocsSearchError, "unsupported charset"):
                SEARCH.search_documents(
                    "DataCopy",
                    lang="zh",
                    doc_type="DOC",
                    page=1,
                    max_results=1,
                    version=None,
                    timeout=1,
                )

    def test_search_posts_unpadded_base64_keyword_and_rotates_csrf_token(self) -> None:
        payload = {
            "success": True,
            "data": {
                "data": [
                    {
                        "docTitle": "<em>SetAtomicType</em>",
                        "docContent": "API summary",
                        "docUrl": "/source/zh/example.html",
                        "version": "9.1.0-beta.3",
                    }
                ]
            },
        }

        requests: list[tuple[str, dict[str, object], str]] = []

        def fake_search_request(
            payload: dict[str, object], token: str, timeout: float
        ) -> tuple[bytes, str, str, str | None]:
            del timeout
            requests.append((payload["keyword"], payload, token))
            return json.dumps(payload_response).encode(), "utf-8", SEARCH.SEARCH_URL, "next-token"

        payload_response = payload

        with (
            mock.patch.object(SEARCH, "_initialize_search_session", return_value="first-token"),
            mock.patch.object(SEARCH, "_search_request", side_effect=fake_search_request),
        ):
            results = SEARCH.search_documents(
                "SetAtomicType",
                lang="zh",
                doc_type="DOC",
                page=1,
                max_results=5,
                version=None,
                timeout=1,
            )
        self.assertEqual(requests[0][0], "U2V0QXRvbWljVHlwZQ")
        self.assertEqual(requests[0][1]["pageNum"], 1)
        self.assertEqual(requests[0][2], "first-token")
        self.assertEqual(results[0]["title"], "SetAtomicType")

    def test_search_paginates_until_version_filter_is_filled(self) -> None:
        requested_pages: list[int] = []

        def fake_search_request(payload, token, timeout):
            del timeout
            page = payload["pageNum"]
            requested_pages.append(page)
            self.assertEqual(payload["pageSize"], SEARCH.SEARCH_PAGE_SIZE)
            self.assertEqual(token, f"token-{page - 1}")
            if page == 1:
                records = [
                    {
                        "docTitle": f"Preview result {index}",
                        "docContent": "Wrong release channel",
                        "docUrl": f"/source/zh/preview-{index}.html",
                        "version": "9.1.0-beta.3",
                    }
                    for index in range(SEARCH.SEARCH_PAGE_SIZE)
                ]
            else:
                records = [
                    {
                        "docTitle": f"Final result {index}",
                        "docContent": "Matching final release",
                        "docUrl": f"/source/zh/final-{index}.html",
                        "version": "9.1.0",
                    }
                    for index in range(2)
                ]
            payload = {"success": True, "data": {"data": records}}
            return json.dumps(payload).encode(), "utf-8", SEARCH.SEARCH_URL, f"token-{page}"

        with (
            mock.patch.object(SEARCH, "_initialize_search_session", return_value="token-0"),
            mock.patch.object(SEARCH, "_search_request", side_effect=fake_search_request),
        ):
            results = SEARCH.search_documents(
                "DataCopy",
                lang="zh",
                doc_type="DOC",
                page=1,
                max_results=2,
                version="9.1.0",
                timeout=1,
            )

        self.assertEqual(requested_pages, [1, 2])
        self.assertEqual([result["version"] for result in results], ["9.1.0", "9.1.0"])

    def test_search_stops_after_bounded_number_of_pages(self) -> None:
        requested_pages: list[int] = []

        def fake_search_request(payload, token, timeout):
            del token, timeout
            requested_pages.append(payload["pageNum"])
            records = [
                {
                    "docTitle": f"Preview result {index}",
                    "docContent": "Wrong release channel",
                    "docUrl": f"/source/zh/preview-{index}.html",
                    "version": "9.1.0-beta.3",
                }
                for index in range(SEARCH.SEARCH_PAGE_SIZE)
            ]
            payload = {"success": True, "data": {"data": records}}
            return json.dumps(payload).encode(), "utf-8", SEARCH.SEARCH_URL, None

        with (
            mock.patch.object(SEARCH, "_initialize_search_session", return_value="token"),
            mock.patch.object(SEARCH, "_search_request", side_effect=fake_search_request),
        ):
            results = SEARCH.search_documents(
                "DataCopy",
                lang="zh",
                doc_type="DOC",
                page=4,
                max_results=1,
                version="9.1.0",
                timeout=1,
            )

        self.assertEqual(results, [])
        self.assertEqual(
            requested_pages,
            list(range(4, 4 + SEARCH.MAX_SEARCH_PAGES)),
        )

    def test_get_rejects_responses_larger_than_the_request_class_limit(self) -> None:
        for response_kind, limit in (
            ("search", SEARCH.MAX_SEARCH_RESPONSE_BYTES),
            ("document", SEARCH.MAX_DOCUMENT_RESPONSE_BYTES),
        ):
            with self.subTest(response_kind=response_kind):
                response = mock.MagicMock()
                response.__enter__.return_value = response
                response.geturl.return_value = SEARCH.SEARCH_URL
                response.headers.get_content_charset.return_value = "utf-8"
                response.read.return_value = b"x" * (limit + 1)
                with mock.patch.object(SEARCH.OFFICIAL_OPENER, "open", return_value=response):
                    with self.assertRaisesRegex(SEARCH.DocsSearchError, "exceeds|too large"):
                        SEARCH._get(
                            SEARCH.SEARCH_URL,
                            1,
                            response_limit=limit,
                        )

    def test_parser_excludes_title_and_navigation_but_keeps_code(self) -> None:
        parser = SEARCH.DocumentParser()
        parser.feed(
            "<html><head><title>SetAtomicType docs</title></head>"
            "<body><header>SetAtomicType navigation</header><main>"
            "<h1>Function</h1><p>SetAtomicType changes the atomic data type.</p>"
            "<pre>template &lt;typename T&gt; void SetAtomicType();</pre>"
            "</main></body></html>"
        )
        parsed = parser.result()
        self.assertEqual(parsed["title"], "SetAtomicType docs")
        self.assertNotIn("navigation", parsed["content"])
        self.assertIn("SetAtomicType changes", parsed["content"])
        self.assertIn("SetAtomicType", parsed["code_blocks"][0])

    def test_self_closing_skipped_tag_does_not_hide_following_content(self) -> None:
        parser = SEARCH.DocumentParser()
        parser.feed("<main><p>before</p><svg/><p>after</p></main>")
        parser.close()
        self.assertEqual(parser.result()["content"], "before\nafter")

    def test_fetch_document_matches_natural_language_terms_and_bounds_output(self) -> None:
        long_code = "matrix API multiplication " + "x" * SEARCH.MAX_CODE_BLOCK_CHARS
        long_content = (
            "Matrix multiplication processes an API request. "
            + "content " * (SEARCH.MAX_FULL_CONTENT_CHARS // 4)
        )
        html = f"<html><main><p>{long_content}</p><pre>{long_code}</pre></main></html>"
        result = {
            "url": "https://www.hiascend.com/document/detail/zh/example.html",
            "title": "Fallback title",
        }
        with mock.patch.object(
            SEARCH,
            "_get",
            return_value=(html.encode(), "utf-8", result["url"]),
        ):
            fetched = SEARCH.fetch_document(
                result,
                "matrix API multiplication",
                timeout=1,
                full_content=True,
            )

        self.assertTrue(fetched["keyword_found"])
        self.assertEqual(fetched["matched_terms"], ["matrix", "API", "multiplication"])
        self.assertTrue(fetched["all_terms_found"])
        self.assertTrue(fetched["content_truncated"])
        self.assertLessEqual(len(fetched["content"]), SEARCH.MAX_FULL_CONTENT_CHARS)
        self.assertTrue(fetched["matching_code_blocks_truncated"])
        self.assertEqual(len(fetched["matching_code_blocks"]), 1)
        self.assertLessEqual(
            len(fetched["matching_code_blocks"][0]),
            SEARCH.MAX_CODE_BLOCK_CHARS,
        )
        self.assertIn("untrusted", fetched["content_trust"])

    def test_fetch_document_preserves_single_symbol_matching(self) -> None:
        html = "<html><main><p>Call SetAtomicType before the operation.</p></main></html>"
        result = {
            "url": "https://www.hiascend.com/document/detail/zh/example.html",
            "title": "Fallback title",
        }
        with mock.patch.object(
            SEARCH,
            "_get",
            return_value=(html.encode(), "utf-8", result["url"]),
        ):
            fetched = SEARCH.fetch_document(
                result,
                "SetAtomicType",
                timeout=1,
                full_content=False,
            )

        self.assertTrue(fetched["keyword_found"])
        self.assertEqual(fetched["matched_terms"], ["SetAtomicType"])
        self.assertTrue(fetched["all_terms_found"])
        self.assertNotIn("content", fetched)

    def test_fetch_document_falls_back_from_unknown_charset(self) -> None:
        result = {
            "url": "https://www.hiascend.com/document/detail/zh/example.html",
            "title": "Fallback title",
        }
        with mock.patch.object(
            SEARCH,
            "_get",
            return_value=(b"<main>DataCopy</main>", "not-a-codec", result["url"]),
        ):
            fetched = SEARCH.fetch_document(
                result, "DataCopy", timeout=1, full_content=False
            )

        self.assertTrue(fetched["keyword_found"])
        self.assertEqual(fetched["matched_terms"], ["DataCopy"])

    def test_main_continues_after_one_document_fetch_fails(self) -> None:
        results = [
            {
                "title": "First",
                "url": "https://www.hiascend.com/document/detail/zh/first.html",
            },
            {
                "title": "Second",
                "url": "https://www.hiascend.com/document/detail/zh/second.html",
            },
        ]
        second_document = {
            "url": results[1]["url"],
            "title": "Second",
            "content_trust": "untrusted_external_content",
        }
        stdout = io.StringIO()
        with (
            mock.patch.object(SEARCH, "search_documents", return_value=results),
            mock.patch.object(
                SEARCH,
                "fetch_document",
                side_effect=[SEARCH.DocsSearchError("page unavailable"), second_document],
            ) as fetcher,
            redirect_stdout(stdout),
        ):
            exit_code = SEARCH.main(
                ["SetAtomicType", "--fetch", "--fetch-limit", "2", "--timeout", "1"]
            )

        output = json.loads(stdout.getvalue())
        self.assertEqual(fetcher.call_count, 2)
        self.assertEqual(exit_code, 1)
        self.assertFalse(output["success"])
        self.assertEqual(output["fetch_error_count"], 1)
        self.assertEqual(output["count"], 2)
        self.assertIn("page unavailable", json.dumps(output["results"][0]))
        self.assertEqual(output["results"][1]["document"], second_document)


if __name__ == "__main__":
    unittest.main()
