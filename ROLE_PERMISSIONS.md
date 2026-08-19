# Insurance AI Role Permissions

This document reflects the permission behavior currently implemented in `backend/main.py`.

## Role Mapping

The application supports three selectable roles:

| User role | Effective permission profile |
|---|---|
| Customer | Customer |
| Admin | Admin |
| Auditor | Auditor |

## Permission Matrix

| Permission | Customer | Admin | Auditor |
|---|:---:|:---:|:---:|
| `documents:upload` | Yes | Yes | No |
| `documents:read` | Yes | Yes | Yes |
| `documents:delete` | No | Yes | No |
| `documents:reindex` | No | Yes | No |
| `chat:ask` | Yes | Yes | No |
| `claims:analyze` | Yes | Yes | No |
| `claims:read` | Yes | Yes | Yes |
| `dashboard:read` | Yes | Yes | Yes |
| `analytics:read` | No | Yes | Yes |
| `admin:read` | No | Yes | No |
| `audit:read` | No | Yes | Yes |
| `monitoring:read` | No | Yes | Yes |
| `users:manage` | No | Yes | No |
| `settings:edit` | No | Yes | No |

## Role Summaries

### Customer

Customers can:

- Upload and view documents.
- Ask the AI chatbot questions.
- Analyze claims.
- View their claim records.
- View the dashboard.

Customers cannot delete or reindex documents, manage users, access audit/monitoring data, or edit system settings.

### Admin

Admins have full application access:

- Upload, view, delete, and reindex documents.
- Ask policy and claim questions through the chatbot.
- Analyze and view claims.
- View dashboard, analytics, audit, and monitoring data.
- Manage users.
- Edit settings.

### Auditor

Auditors can:

- View documents.
- View claims and claim details.
- View the dashboard.
- View analytics.
- View audit logs.
- View monitoring information.

Auditors cannot upload, delete, or reindex documents; ask chatbot questions; analyze claims; manage users; or edit settings.

Removed roles are no longer offered in login or registration and no longer receive Admin access through backend aliases.