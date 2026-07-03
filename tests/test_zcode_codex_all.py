"""Verify http_request and db_query are properly exported — now in core.client after refactor."""


def test_http_request_in_client_all():
    from core.client import __all__

    assert "http_request" in __all__, "http_request missing from client.__all__"


def test_db_query_in_client_all():
    from core.client import __all__

    assert "db_query" in __all__, "db_query missing from client.__all__"


def test_http_request_importable():
    from core.client import http_request

    assert callable(http_request)


def test_db_query_importable():
    from core.client import db_query

    assert callable(db_query)
