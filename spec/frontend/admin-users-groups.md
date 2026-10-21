# Admin users and groups

## Purpose

Lets administrators find user accounts, change their group memberships, activate or deactivate
them, grant or remove admin rights, and delete them; and manage the groups that gate workflow
access (create, delete, see and remove members). The views send only the changes the admin made;
all permission and self-protection rules are enforced by the backend and mirrored in the UI only
to avoid offering actions that would fail.

## Scope

Covered:

- `frontend/src/views/admin/AdminUsersView.vue` (route `/admin/users`)
- `frontend/src/components/admin/GroupManagementModal.vue`
- `frontend/src/components/admin/GroupMembersModal.vue`
- Admin functions of `frontend/src/api/users.js`: `listUsers`, `getUser`, `updateUser`,
  `deleteUser`, `listGroups`, `createGroup`, `deleteGroup`.
- Client-side group-name check `validateGroupName` as used by the group modal (the rule itself
  is specified in [auth-views.md](auth-views.md) / [../backend/accounts.md](../backend/accounts.md)).

Out of scope:

- Profile functions of `users.js` (`getProfile`, `updateProfile`, …) — [profile.md](profile.md).
- Avatar helpers (`utils/avatar.js`) — [common-components.md](common-components.md).
- Route guards — [routing.md](routing.md). Server rules — [../backend/admin-api.md](../backend/admin-api.md).
- Group access per workflow — [admin-workflows.md](admin-workflows.md).

## Dependencies

- [../backend/admin-api.md](../backend/admin-api.md) — BE-ADM-020…027 (users), BE-ADM-030…032
  (groups).
- [../backend/accounts.md](../backend/accounts.md) — K1 uniqueness (no duplicate users), group-name rule.
- [api-client.md](api-client.md) — `apiErrorMessage`, `apiFieldErrors`.
- [state-stores.md](state-stores.md) — `auth.user.id` to detect the admin's own row.
- Contract operations: `admin_users_list`, `admin_users_retrieve`, `admin_users_partial_update`,
  `admin_users_destroy`, `admin_groups_list`, `admin_groups_create`, `admin_groups_destroy`.

## Requirements

### Access

- **FE-AUSER-001** `/admin/users` MUST be reachable only by a signed-in admin; a signed-in
  non-admin MUST land on `/` without the users table being rendered, an anonymous visitor on
  `/login?next=/admin/users`.

### User list

- **FE-AUSER-010** On mount the view MUST call `listUsers({page: 1, page_size: 20})`
  (`admin_users_list`) and `listGroups()` (`admin_groups_list`), showing a spinner until the
  user list arrives. The heading MUST show the server `count` (`admin-users-count`).
- **FE-AUSER-011** Search (`admin-users-search`, submit or Enter) MUST re-fetch page 1 with the
  trimmed `search` term; an empty term MUST be omitted. Paging MUST keep the current term.
- **FE-AUSER-012** Each fetch MUST replace the displayed rows with exactly the `results` of that
  response, keyed by `user.id`; rows MUST NOT be appended or merged across pages or searches,
  and the total MUST come from `count`, never from the number of rows held client-side. (Guards
  against re-introducing the duplicate-users symptom client-side.)
- **FE-AUSER-013** Each row (`admin-user-row`, `data-username`) MUST show the initials avatar,
  username, full name, e-mail, active/inactive badge (`admin-user-status`, `data-state`), an
  `admin` badge when `is_admin`, join date and last login ("–" when null), and the user's group
  chips excluding `admin`. An empty result MUST show "No users found." (`admin-users-empty`).
- **FE-AUSER-014** A load failure MUST show the envelope message (fallback "Could not load
  users." / "Could not load groups.") in `admin-users-error`.

### User actions

- **FE-AUSER-020** Adding a group (`admin-user-group-add`, only listing existing non-admin
  groups the user is not in) and removing a chip (`admin-user-group-remove`) MUST call
  `updateUser(id, {groups: [...]})` with the complete new list of non-admin group names. The
  `admin` group MUST NOT be sent or offered as a chip.
- **FE-AUSER-021** Activate/Deactivate (`admin-user-toggle-active`) MUST send only
  `{is_active: !current}`; Make admin/Remove admin (`admin-user-toggle-admin`) MUST send only
  `{is_admin: !current}`.
- **FE-AUSER-022** After a successful PATCH the row MUST be replaced by the returned `AdminUser`
  (same position, matched by `id`); group-changing and admin-changing actions MUST also re-fetch
  groups so member counts and choices stay current.
- **FE-AUSER-023** While a request for a row runs, that row's controls MUST be disabled. On
  failure the envelope message MUST be shown with the action-specific fallback ("Adding the
  group failed.", "Removing the group failed.", "Changing the account status failed.",
  "Changing administrator rights failed.") and the row MUST keep its previous values.
- **FE-AUSER-024** On the admin's own row the Activate/Deactivate, admin toggle and Delete
  buttons MUST be disabled; for a superuser who is admin the Remove admin button MUST be
  disabled (mirrors BE-ADM-024/026).
- **FE-AUSER-025** Delete (`admin-user-delete`) MUST open a confirmation
  (`admin-user-delete-dialog`) naming the user as text; confirming MUST call `deleteUser(id)`
  (`admin_users_destroy`) and re-fetch users and groups. If the deleted row was the only one on a
  page above 1, the previous page MUST be loaded. Cancel MUST make no request. A failure MUST
  show the envelope message (fallback "Delete failed.") and close the dialog.

### Groups modal

- **FE-AUSER-030** The Groups button (`admin-users-manage-groups`) MUST open
  `GroupManagementModal` (`group-modal`), which MUST load `listGroups()` and list each group
  (`group-row`, `data-group`) with its `member_count`, or "No groups yet." when empty.
- **FE-AUSER-031** Creating a group MUST first validate the name with `validateGroupName` and
  show the message under the input (`group-create-error`) without a request when invalid. A
  valid name MUST be sent trimmed via `createGroup({name})`. A 400 with `fields.name` (e.g.
  "already exists", any case) MUST be shown under the input; other errors in the modal alert
  (`group-error`). On success the input MUST clear, the list reload and the parent re-fetch
  users and groups.
- **FE-AUSER-032** The Delete button of the `admin` group MUST be disabled. Deleting another
  group MUST ask for confirmation (`group-delete-dialog`, naming the group and member count) and
  then call `deleteGroup(id)`; success MUST reload the list and notify the parent.
- **FE-AUSER-033** The members button (`group-members`) MUST open `GroupMembersModal`
  (`group-members-modal`), which MUST load `listUsers({group: <name>, page_size: 200})` and
  list members (`group-member`, `data-username`), or "No members. Add users to this group from
  the user list." when empty.
- **FE-AUSER-034** Removing a member (`group-member-remove`) of the `admin` group MUST send
  `{is_admin: false}`; of any other group it MUST send `{groups: <user's groups without this
  group and without admin>}`. Success MUST reload the members and notify both parents; failure
  MUST show the envelope message (fallback "Removing the member failed.").
- **FE-AUSER-035** Closing (X, Close button or backdrop click) MUST close only the topmost modal.

### Rendering safety

- **FE-AUSER-040** Usernames, full names, e-mails and group names MUST be rendered as text in
  all three components (including the delete confirmations); none of them MAY use `v-html`.

## Interfaces

| UI action | API function (`src/api/users.js`) | operationId | Body / params |
|-----------|-----------------------------------|-------------|---------------|
| List / search / page users | `listUsers(params)` | `admin_users_list` | `{search?, page, page_size}`; members modal `{group, page_size: 200}` |
| Change groups / active / admin | `updateUser(id, data)` | `admin_users_partial_update` | one of `{groups}`, `{is_active}`, `{is_admin}` |
| Delete user | `deleteUser(id)` | `admin_users_destroy` | — |
| List groups | `listGroups()` | `admin_groups_list` | — (plain array) |
| Create group | `createGroup({name})` | `admin_groups_create` | `AdminGroupRequest` |
| Delete group | `deleteGroup(id)` | `admin_groups_destroy` | — |
| (unused by views) | `getUser(id)` | `admin_users_retrieve` | — |

Events: `GroupManagementModal` emits `close`, `groups-updated`; `GroupMembersModal` emits
`close`, `members-changed`. Shapes: `AdminUser`, `PaginatedAdminUserList`, `AdminGroup` — see
[api-contract.md](api-contract.md).

## Behaviour

- Row busy state is a map `{[user.id]: true}`; a row is dimmed and its controls disabled while
  its request runs. Other rows stay usable.
- Adding a group via the select resets the select to "+ group" before the request.
- The admin group is handled only through `is_admin` everywhere, matching BE-ADM-022/023: it is
  filtered from chips and from the add-group choices, and removal from the `admin` group in the
  members modal is translated to `is_admin: false`.
- Group modal and members modal are stacked (`z-index` 1060 for members); both refresh their
  own data and bubble a change event so the user table stays consistent.

## Acceptance tests

| Requirement | Test | Layer |
|-------------|------|-------|
| FE-AUSER-001 | `e2e/tests/test_accounts.py::test_a7_non_admin_blocked_from_admin_ui_and_api` | e2e |
| FE-AUSER-010, 011, 013 | `e2e/tests/test_accounts.py::test_d3_admin_users` (search, row, groups column); `frontend/src/test/contracts/users.test.js` › admin users › listUsers → GET /admin/users/ with params (paginated) | e2e, contract |
| FE-AUSER-012 | `e2e/tests/test_accounts.py::test_d3_admin_users` (one row per search; count unchanged after group edits, K1); `frontend/src/test/views/AdminUsersView.test.js` › page change replaces rows, no duplicates (planned) | e2e, unit |
| FE-AUSER-014, 023 | `frontend/src/test/views/AdminUsersView.test.js` › shows envelope message and keeps row on PATCH failure (planned) | unit |
| FE-AUSER-020, 021, 022 | `e2e/tests/test_accounts.py::test_d3_admin_users` (add/remove group, deactivate/activate); `frontend/src/test/contracts/users.test.js` › groups are names, not objects; › updateUser / deleteUser / getUser | e2e, contract |
| FE-AUSER-024 | `frontend/src/test/views/AdminUsersView.test.js` › own row and superuser buttons disabled (planned) | unit |
| FE-AUSER-025 | `e2e/tests/test_accounts.py::test_d3_admin_users` (delete) | e2e |
| FE-AUSER-030, 031, 032 | `e2e/tests/test_accounts.py::test_d3_admin_users` (member counts, create, duplicate in other case, admin delete disabled, delete); `frontend/src/test/contracts/users.test.js` › admin groups › listGroups / createGroup / deleteGroup; `frontend/src/utils/validation.test.js` | e2e, contract, unit |
| FE-AUSER-033, 034 | `e2e/tests/test_admin_users.py::test_group_members_modal_remove_member` (planned) | e2e |
| FE-AUSER-035 | `frontend/src/test/components/GroupModals.test.js` › backdrop closes only top modal (planned) | unit |
| FE-AUSER-040 | `frontend/src/test/views/admin-no-vhtml.test.js` › user and group names render as text (planned) | unit |

## Known gaps

| Requirement | What the code does | Where | Severity |
|-------------|--------------------|-------|----------|
| FE-AUSER-033 | The members modal requests one page of at most 200 (`max_page_size`) and ignores `next`; a group with more than 200 members is silently truncated. | `frontend/src/components/admin/GroupMembersModal.vue:21` | minor |
| FE-AUSER-034 | The Remove button is disabled for every superuser in every group (`user.is_superuser`), not only in the `admin` group, so a superuser cannot be removed from e.g. `researchers` here. It is not disabled for the admin's own row in the `admin` group (server rejects with 400). | `frontend/src/components/admin/GroupMembersModal.vue:87` | minor |
| FE-AUSER-035 | Backdrop click on the members modal also lies inside the group modal; behaviour relies on `@click.self` on separate overlays and is untested. `Escape` does not close either modal. | `frontend/src/components/admin/GroupManagementModal.vue:86`, `GroupMembersModal.vue:57` | minor |
| FE-AUSER-012 | `fetchUsers` has no stale-response guard: a slow earlier request (e.g. previous page) can overwrite the rows of a later search. Rows are still replaced, not merged, so no duplicates appear. | `frontend/src/views/admin/AdminUsersView.vue:33-48` | minor |
| — | The `group` and `is_active` filters that `admin_users_list` supports are not offered in the user list UI. | `frontend/src/views/admin/AdminUsersView.vue:132-144` | minor |
| — | `GroupManagementModal` declares a `show` prop it never reads. | `frontend/src/components/admin/GroupManagementModal.vue:9-11` | minor |
| — | No component-level tests for the three components; coverage is the single e2e `test_d3_admin_users` plus API-module contract tests. | `frontend/src/test/` | minor |

## Open questions

- Should the user list expose the `group` / `is_active` filters the API already supports?
- The members modal duplicates group editing that the user table offers; keep both?
