from main import get_role_permissions


def test_admin_permissions_include_admin_actions():
    permissions = get_role_permissions("admin")
    assert "documents:upload" in permissions
    assert "settings:edit" in permissions
    assert "dashboard:read" in permissions


def test_legacy_roles_are_treated_as_admin_access():
    permissions = get_role_permissions("agent")
    assert "documents:upload" in permissions
    assert "settings:edit" in permissions


def test_default_permissions_cover_base_access():
    permissions = get_role_permissions("unknown")
    assert "documents:upload" in permissions
    assert "documents:read" in permissions
    assert "chat:ask" in permissions
