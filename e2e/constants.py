"""Seed data shared by `seed.py` (runs inside Django) and the pytest side (no Django import)."""

USERS = {
    'admin': {'password': 'Admin1234', 'email': 'admin@e2e.test', 'full_name': 'E2E Admin',
              'groups': ['admin'], 'is_admin': True},
    'alice': {'password': 'Alice1234', 'email': 'alice@e2e.test', 'full_name': 'Alice Researcher',
              'groups': ['researchers'], 'is_admin': False},
    'bob': {'password': 'Bob12345', 'email': 'bob@e2e.test', 'full_name': 'Bob Nogroup',
            'groups': [], 'is_admin': False},
}

# Installed fixture apps and their access rules (written to settings.yaml `apps:`).
APPS = {
    'hello': {'public': True, 'groups': []},
    'all-inputs': {'public': False, 'groups': ['researchers']},
    'fail': {'public': False, 'groups': ['admin']},
    'slow': {'public': False, 'groups': ['admin']},
    'multi-process': {'public': False, 'groups': ['admin']},
}

# Queue limits written to settings.yaml (Q1 relies on max_running_jobs == 2).
MAX_RUNNING_JOBS = 2
MAX_QUEUE_SIZE = 5

# Navbar written to settings.yaml, in this order. Admin-only items must be hidden for non-admins.
NAVBAR = [
    {'title': 'Home', 'url': '/'},
    {'title': 'Run Hello', 'url': '/run/hello'},
    {'title': 'About E2E', 'url': '/pages/about'},
    {'title': 'Admin Area', 'url': '/admin', 'admin_only': True},
]

# Unique markers placed in the page templates so tests can prove the files were rendered.
PAGE_MARKERS = {
    'home': 'E2E-HOME-MARKER welcome to the test server',
    'footer': 'E2E-FOOTER-MARKER',
    'about': 'E2E-ABOUT-MARKER about this server',
}

SERVER_NAME = 'Cloudgene E2E'
