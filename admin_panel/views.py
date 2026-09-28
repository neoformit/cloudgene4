"""
Admin panel API (SPEC §3.6). Settings live in ``settings.yaml`` / files under
``$CLOUDGENE_HOME`` and are read and written through ``core.config``.
"""
import logging
from datetime import datetime, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core import config
from core.exceptions import error_response
from core.models import WorkerHeartbeat
from core.permissions import ADMIN_GROUP, IsAdmin
from workflows.template_utils import VARIABLES

from . import serializers as s
from .models import SystemLog

User = get_user_model()
logger = logging.getLogger('cloudgene.admin')

PROTECTED_PAGES = ('home', 'footer')

# Job states (SPEC §3.3) and the legacy names T03's migration maps from.
JOB_STATES = ('waiting', 'running', 'success', 'failed', 'cancelled')
LEGACY_STATES = {'pending': 'waiting', 'completed': 'success'}


def _config_error(exc: config.ConfigError, prefix: str):
    """ConfigError(errors={'server.name': [...]}) → envelope with un-prefixed field names."""
    fields = {}
    for key, msgs in exc.errors.items():
        name = key[len(prefix):] if prefix and key.startswith(prefix) else key
        fields[name] = msgs
    first = next(iter(fields))
    return error_response(f'{first}: {fields[first][0]}', 'invalid', 400, fields=fields)


def _actor(request):
    return {'user': request.user}


# --------------------------------------------------------------------------------------
# Settings: general / mail / nextflow / navbar
# --------------------------------------------------------------------------------------

GENERAL_KEYS = ('name', 'url', 'max_running_jobs', 'max_queue_size', 'job_retention_days',
                'max_upload_mb', 'maintenance', 'maintenance_message')


class GeneralSettingsView(APIView):
    permission_classes = [IsAdmin]

    def _payload(self):
        server = config.load_settings()['server']
        return {k: server[k] for k in GENERAL_KEYS}

    @extend_schema(operation_id='admin_settings_general_retrieve',
                   responses=s.GeneralSettingsSerializer)
    def get(self, request):
        return Response(self._payload())

    @extend_schema(operation_id='admin_settings_general_update',
                   request=s.GeneralSettingsSerializer, responses=s.GeneralSettingsSerializer)
    def put(self, request):
        ser = s.GeneralSettingsSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            config.update_settings({'server': dict(ser.validated_data)})
        except config.ConfigError as exc:
            return _config_error(exc, 'server.')
        logger.info('General settings changed: %s', ', '.join(sorted(ser.validated_data)),
                    extra=_actor(request))
        return Response(self._payload())


MAIL_KEYS = ('backend', 'file_path', 'host', 'port', 'user', 'use_tls', 'use_ssl',
             'from_email')


class MailSettingsView(APIView):
    permission_classes = [IsAdmin]

    def _payload(self):
        mail = config.load_settings()['mail']
        data = {k: mail[k] for k in MAIL_KEYS}
        data['password_set'] = bool(mail['password'])
        return data

    @extend_schema(operation_id='admin_settings_mail_retrieve',
                   responses=s.MailSettingsSerializer)
    def get(self, request):
        return Response(self._payload())

    @extend_schema(operation_id='admin_settings_mail_update', request=s.MailSettingsSerializer,
                   responses=s.MailSettingsSerializer)
    def put(self, request):
        ser = s.MailSettingsSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = dict(ser.validated_data)
        clear = data.pop('clear_password', False)
        password = data.pop('password', '')
        if clear:
            data['password'] = ''
        elif password:
            data['password'] = password
        try:
            config.update_settings({'mail': data})
        except config.ConfigError as exc:
            return _config_error(exc, 'mail.')
        logger.info('Mail settings changed: %s', ', '.join(sorted(data)), extra=_actor(request))
        return Response(self._payload())


class MailTestView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(operation_id='admin_settings_mail_test', request=s.MailTestSerializer,
                   responses=s.MailTestResultSerializer)
    def post(self, request):
        ser = s.MailTestSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        to = ser.validated_data.get('to') or request.user.email
        if not to:
            return error_response('Your account has no e-mail address; enter a recipient.',
                                  'invalid', 400, fields={'to': ['This field is required.']})
        from core.mail import send_mail
        name = config.get('server.name')
        try:
            send_mail(f'[{name}] Test e-mail',
                      f'This is a test e-mail sent from the {name} admin panel by '
                      f'{request.user.username}.\n\nYour mail settings work.', [to])
        except Exception as exc:  # SMTP errors, bad host, …
            logger.warning('Test e-mail to %s failed: %s', to, exc, extra=_actor(request))
            return error_response(f'Sending failed: {exc}', 'mail_failed', 502)
        logger.info('Test e-mail sent to %s', to, extra=_actor(request))
        return Response({'message': f'Test e-mail sent to {to}.', 'to': to})


def _variables():
    return [{'name': n, 'scope': sc, 'description': d} for n, sc, d in VARIABLES
            if sc == 'global']


class NextflowSettingsView(APIView):
    permission_classes = [IsAdmin]

    def _payload(self):
        nf = config.load_settings()['nextflow']
        return {
            'binary': nf['binary'], 'profile': nf['profile'], 'work_dir': nf['work_dir'],
            'config': config.read_text(config.nextflow_config_path()),
            'env': config.read_text(config.nextflow_env_path()),
            'variables': _variables(),
        }

    @extend_schema(operation_id='admin_settings_nextflow_retrieve',
                   responses=s.NextflowSettingsSerializer)
    def get(self, request):
        return Response(self._payload())

    @extend_schema(operation_id='admin_settings_nextflow_update',
                   request=s.NextflowSettingsSerializer, responses=s.NextflowSettingsSerializer)
    def put(self, request):
        ser = s.NextflowSettingsSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = dict(ser.validated_data)
        config_text = data.pop('config', None)
        env_text = data.pop('env', None)
        if data:
            try:
                config.update_settings({'nextflow': data})
            except config.ConfigError as exc:
                return _config_error(exc, 'nextflow.')
        if config_text is not None:
            config.write_text_atomic(config.nextflow_config_path(), config_text)
        if env_text is not None:
            config.write_text_atomic(config.nextflow_env_path(), env_text)
        logger.info('Nextflow settings changed', extra=_actor(request))
        return Response(self._payload())


class NavbarSettingsView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(operation_id='admin_settings_navbar_retrieve', responses=s.NavbarSerializer)
    def get(self, request):
        return Response({'navbar': config.load_settings()['navbar']})

    @extend_schema(operation_id='admin_settings_navbar_update', request=s.NavbarSerializer,
                   responses=s.NavbarSerializer)
    def put(self, request):
        ser = s.NavbarSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        items = [dict(item) for item in ser.validated_data['navbar']]
        try:
            new = config.update_settings(lambda doc: {**doc, 'navbar': items})
        except config.ConfigError as exc:
            return _config_error(exc, '')
        logger.info('Navbar changed (%d items)', len(items), extra=_actor(request))
        return Response({'navbar': new['navbar']})


# --------------------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------------------


def _page_summary(slug):
    path = config.page_path(slug)
    st = path.stat()
    return {'slug': slug, 'size': st.st_size,
            'updated_at': datetime.fromtimestamp(st.st_mtime, tz=dt_timezone.utc),
            'deletable': slug not in PROTECTED_PAGES}


def _check_slug(slug):
    try:
        config.page_path(slug)
    except ValueError:
        return error_response('Invalid page name: use a-z, 0-9, "-" and "_" (max 64).',
                              'invalid', 400,
                              fields={'slug': ['Use a-z, 0-9, "-" and "_" (max 64).']})
    return None


class PageListView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(operation_id='admin_pages_list', responses=s.PageSummarySerializer(many=True))
    def get(self, request):
        return Response([_page_summary(slug) for slug in config.list_pages()])


class PageDetailView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(operation_id='admin_pages_retrieve', responses=s.PageSerializer)
    def get(self, request, slug):
        bad = _check_slug(slug)
        if bad:
            return bad
        html = config.read_page(slug)
        if html is None:
            return error_response('Page not found.', 'not_found', 404)
        return Response({'slug': slug, 'html': html, 'deletable': slug not in PROTECTED_PAGES})

    @extend_schema(operation_id='admin_pages_update', request=s.PageSerializer,
                   responses={200: s.PageSerializer, 201: s.PageSerializer})
    def put(self, request, slug):
        bad = _check_slug(slug)
        if bad:
            return bad
        ser = s.PageSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        created = config.read_page(slug) is None
        config.write_page(slug, ser.validated_data['html'])
        logger.info('Page %s %s', slug, 'created' if created else 'updated', extra=_actor(request))
        return Response({'slug': slug, 'html': ser.validated_data['html'],
                         'deletable': slug not in PROTECTED_PAGES},
                        status=201 if created else 200)

    @extend_schema(operation_id='admin_pages_destroy', responses={204: None})
    def delete(self, request, slug):
        bad = _check_slug(slug)
        if bad:
            return bad
        if slug in PROTECTED_PAGES:
            return error_response(f'The "{slug}" page cannot be deleted (edit it instead).',
                                  'protected', 400)
        if not config.delete_page(slug):
            return error_response('Page not found.', 'not_found', 404)
        logger.info('Page %s deleted', slug, extra=_actor(request))
        return Response(status=204)


# --------------------------------------------------------------------------------------
# Dashboard & queue
# --------------------------------------------------------------------------------------


def _job_model():
    from jobs.models import Job
    return Job


def _state_field(Job):
    names = {f.name for f in Job._meta.get_fields()}
    return 'state' if 'state' in names else 'status'


def _finished_field(Job):
    names = {f.name for f in Job._meta.get_fields()}
    return 'finished_at' if 'finished_at' in names else 'completed_at'


def job_counts():
    Job = _job_model()
    field = _state_field(Job)
    counts = {state: 0 for state in JOB_STATES}
    total = 0
    for value, n in Job.objects.values_list(field).annotate(n=Count('pk')).order_by():
        state = LEGACY_STATES.get(value, value)
        if state in counts:
            counts[state] += n
        total += n
    counts['total'] = total
    return counts


def queue_status(counts=None):
    settings = config.load_settings()
    counts = counts or job_counts()
    worker = WorkerHeartbeat.status()
    return {
        'paused': settings['queue']['paused'],
        'maintenance': settings['server']['maintenance'],
        'maintenance_message': settings['server']['maintenance_message'],
        'running': counts['running'],
        'waiting': counts['waiting'],
        'max_running': settings['server']['max_running_jobs'],
        'max_queue': settings['server']['max_queue_size'],
        'worker': worker,
    }


def recent_jobs(limit=10):
    Job = _job_model()
    field = _state_field(Job)
    finished = _finished_field(Job)
    out = []
    for job in Job.objects.select_related('workflow', 'user').order_by('-submitted_at')[:limit]:
        value = getattr(job, field)
        out.append({
            'id': str(job.pk),
            'name': job.name or '',
            'state': LEGACY_STATES.get(value, value),
            'workflow': {'id': job.workflow_id or getattr(job, 'app_id', ''),
                         'name': job.workflow.name if job.workflow_id else getattr(job, 'app_name', '')},
            'user': {'id': job.user_id, 'username': job.user.username},
            'submitted_at': job.submitted_at,
            'started_at': job.started_at,
            'finished_at': getattr(job, finished, None),
        })
    return out


class DashboardView(APIView):
    permission_classes = [IsAdmin]

    @extend_schema(operation_id='admin_dashboard', responses=s.DashboardSerializer)
    def get(self, request):
        from workflows import registry
        from workflows.models import Workflow

        counts = job_counts()
        statuses = registry.list_apps()
        users = User.objects.aggregate(
            total=Count('pk'),
            active=Count('pk', filter=Q(is_active=True)),
            admins=Count('pk', distinct=True, filter=Q(is_superuser=True) | Q(is_staff=True)
                         | Q(groups__name=ADMIN_GROUP)),
        )
        unmanaged = Workflow.objects.filter(app_path='')  # rows not from settings.yaml
        wf = {
            'total': len(statuses) + unmanaged.count(),
            'enabled': sum(1 for x in statuses if x.valid and x.enabled)
            + unmanaged.filter(status='enabled').count(),
            'invalid': sum(1 for x in statuses if not x.valid),
        }
        wf['disabled'] = wf['total'] - wf['enabled'] - wf['invalid']
        cfg = config.config_status()
        data = {
            'queue': queue_status(counts),
            'jobs': counts,
            'users': users,
            'workflows': wf,
            'recent_jobs': recent_jobs(),
            'config': {'ok': cfg['ok'],
                      'errors': [f'{k}: {m}' for k, msgs in cfg['errors'].items() for m in msgs]},
        }
        return Response(s.DashboardSerializer(data).data)


class _QueueAction(APIView):
    permission_classes = [IsAdmin]
    key = None
    value = None
    message = ''

    def post(self, request):
        patch = {}
        section, name = self.key.split('.')
        patch[section] = {name: self.value}
        if self.key == 'server.maintenance' and self.value:
            ser = s.MaintenanceRequestSerializer(data=request.data or {})
            ser.is_valid(raise_exception=True)
            if ser.validated_data.get('message'):
                patch['server']['maintenance_message'] = ser.validated_data['message']
        config.update_settings(patch)
        logger.info(self.message, extra=_actor(request))
        return Response(s.QueueStatusSerializer(queue_status()).data)


class QueuePauseView(_QueueAction):
    key, value, message = 'queue.paused', True, 'Queue paused'

    @extend_schema(operation_id='admin_queue_pause', request=None,
                   responses=s.QueueStatusSerializer)
    def post(self, request):
        return super().post(request)


class QueueResumeView(_QueueAction):
    key, value, message = 'queue.paused', False, 'Queue resumed'

    @extend_schema(operation_id='admin_queue_resume', request=None,
                   responses=s.QueueStatusSerializer)
    def post(self, request):
        return super().post(request)


class MaintenanceEnterView(_QueueAction):
    key, value, message = 'server.maintenance', True, 'Maintenance mode entered'

    @extend_schema(operation_id='admin_maintenance_enter', request=s.MaintenanceRequestSerializer,
                   responses=s.QueueStatusSerializer)
    def post(self, request):
        return super().post(request)


class MaintenanceExitView(_QueueAction):
    key, value, message = 'server.maintenance', False, 'Maintenance mode left'

    @extend_schema(operation_id='admin_maintenance_exit', request=None,
                   responses=s.QueueStatusSerializer)
    def post(self, request):
        return super().post(request)


# --------------------------------------------------------------------------------------
# Logs
# --------------------------------------------------------------------------------------


@extend_schema(parameters=[
    OpenApiParameter('level', OpenApiTypes.STR, description='Exact level (debug…critical)'),
    OpenApiParameter('min_level', OpenApiTypes.STR, description='This level and above'),
    OpenApiParameter('component', OpenApiTypes.STR, description='e.g. jobs, auth, admin'),
    OpenApiParameter('search', OpenApiTypes.STR, description='Substring of the message'),
])
class LogListView(generics.ListAPIView):
    permission_classes = [IsAdmin]
    serializer_class = s.SystemLogSerializer
    ORDER = ['debug', 'info', 'warning', 'error', 'critical']

    def get_queryset(self):
        qs = SystemLog.objects.select_related('user').order_by('-timestamp', '-id')
        params = self.request.query_params
        level = (params.get('level') or '').lower()
        if level:
            qs = qs.filter(level=level)
        min_level = (params.get('min_level') or '').lower()
        if min_level in self.ORDER:
            qs = qs.filter(level__in=self.ORDER[self.ORDER.index(min_level):])
        component = params.get('component')
        if component:
            qs = qs.filter(component=component)
        search = params.get('search')
        if search:
            qs = qs.filter(message__icontains=search)
        return qs
