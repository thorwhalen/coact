"""Tests for the dependency-free helpers in ``coact.util``.

Name conversions, ``import_object`` (both ref forms + error cases), and
``check_requirements`` (the actionable optional-backend error).
"""

from __future__ import annotations

import pytest

from coact.util import (
    check_requirements,
    import_object,
    to_kebab_case,
    to_snake_case,
)


def test_to_kebab_case():
    assert to_kebab_case("UxAnalyst") == "ux-analyst"
    assert to_kebab_case("ux_analyst") == "ux-analyst"
    assert to_kebab_case("already-kebab") == "already-kebab"


def test_to_snake_case():
    assert to_snake_case("UxAnalyst") == "ux_analyst"
    assert to_snake_case("ux-analyst") == "ux_analyst"


def test_import_object_colon_form():
    from json import dumps

    assert import_object("json:dumps") is dumps


def test_import_object_dotted_form():
    from os.path import join

    assert import_object("os.path.join") is join


def test_import_object_nested_attr():
    # module:attr.subattr resolves through getattr chain
    obj = import_object("coact.base:ReturnContract.from_dict")
    assert callable(obj)


@pytest.mark.parametrize("ref", [":", "", "nodots", ":dumps", "json:"])
def test_import_object_invalid_ref_raises_value_error(ref):
    with pytest.raises(ValueError, match="Invalid object reference"):
        import_object(ref)


def test_import_object_missing_module_raises_import_error():
    with pytest.raises(ImportError):
        import_object("definitely_not_a_module_xyz:thing")


def test_import_object_missing_attr_raises_attribute_error():
    with pytest.raises(AttributeError):
        import_object("json:no_such_attr")


def test_check_requirements_all_present_no_raise():
    check_requirements({"json": "json"}, feature="noop")  # importable -> silent


def test_check_requirements_missing_lists_pip_target():
    with pytest.raises(ImportError) as exc:
        check_requirements({"not_real_mod_xyz": "not-real-pkg"}, feature="thing")
    msg = str(exc.value)
    assert "thing" in msg and "pip install not-real-pkg" in msg


def test_check_requirements_reports_present_vs_missing():
    with pytest.raises(ImportError) as exc:
        check_requirements(
            {"json": "json", "not_real_mod_xyz": "not-real-pkg"}, feature="mix"
        )
    msg = str(exc.value)
    assert "already present: json" in msg and "not-real-pkg" in msg
