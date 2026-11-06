"""Generated clients must retain every governed Artemis HTTP operation."""
from __future__ import annotations

import warnings

from van_gateway.app import create_app


def test_artemis_aliases_have_distinct_openapi_operation_ids():
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        schema = create_app().openapi()
    operations = {
        (path, method): operation["operationId"]
        for path, methods in schema["paths"].items()
        for method, operation in methods.items()
        if method in {"get", "post", "put", "patch", "delete", "head", "options"}
    }
    assert len(set(operations.values())) == len(operations)
    for path in ("/v1/artemis/console", "/v1/artemis/console/", "/v1/artemis/console/{resource_path}", "/api/{resource_path}"):
        assert {method for candidate, method in operations if candidate == path} == {"get", "head", "options", "post"}
    for path in ("/images/{resource_path}", "/videos/{resource_path}", "/local_file/{resource_path}"):
        assert {method for candidate, method in operations if candidate == path} == {"get", "head", "options"}
    assert not [str(item.message) for item in recorded if "Duplicate Operation ID" in str(item.message)]
