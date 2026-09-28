from django.contrib import admin
from rest_framework.authtoken.models import TokenProxy

# B-03: DRF's own admin for the auth token registers a ModelAdmin whose changelist prints
# `key` in cleartext (rest_framework/authtoken/admin.py). SPEC §3.4/§3.6 promise the key is
# only ever returned once, from `POST /api/me/token`, so no admin surface may show it —
# unregister it entirely rather than replace it with a ModelAdmin that could regress and
# re-add `key` to `list_display`/`fields` later.
admin.site.unregister(TokenProxy)

# `accounts.User` is not registered in the Django admin at all, so there is no user
# changelist/change page that could expose a token either (checked for B-03).
