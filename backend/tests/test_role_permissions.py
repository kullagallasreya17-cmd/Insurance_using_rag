from main import get_role_permissions


def test_admin_permissions_include_admin_actions():
    permissions = get_role_permissions("admin")
    assert "documents:upload" in permissions
    assert "settings:edit" in permissions


def test_analyst_permissions_are_role_specific():
    permissions = get_role_permissions("analyst")
    assert "claims:analyze" in permissions
    assert "documents:upload" not in permissions


def test_default_permissions_cover_base_access():
    permissions = get_role_permissions("unknown")
    assert "documents:read" in permissions
    assert "chat:ask" in permissions
