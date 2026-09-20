"""T03 job rework, part 1: renames, new fields, JobOutput, and the state data migration
(pending → waiting, completed → success; steps: pending → waiting, completed → success,
skipped → cancelled). Part 2 (0004) drops the obsolete columns/models."""
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models

JOB_STATES = {'pending': 'waiting', 'completed': 'success'}
STEP_STATES = {'pending': 'waiting', 'completed': 'success', 'skipped': 'cancelled'}


def forwards(apps, schema_editor):
    Job = apps.get_model('jobs', 'Job')
    JobStep = apps.get_model('jobs', 'JobStep')
    for old, new in JOB_STATES.items():
        Job.objects.filter(status=old).update(status=new)
    for old, new in STEP_STATES.items():
        JobStep.objects.filter(status=old).update(status=new)
    for job in Job.objects.select_related('workflow').all():
        if job.workflow_id and job.workflow is not None:
            job.app_id = job.workflow.id
            job.app_name = job.workflow.name
            job.app_version = job.workflow.version or ''
            job.workflow_yaml = job.workflow.yaml_config or ''
            job.save(update_fields=['app_id', 'app_name', 'app_version', 'workflow_yaml'])


def backwards(apps, schema_editor):
    Job = apps.get_model('jobs', 'Job')
    JobStep = apps.get_model('jobs', 'JobStep')
    for old, new in JOB_STATES.items():
        Job.objects.filter(status=new).update(status=old)
    for old, new in STEP_STATES.items():
        JobStep.objects.filter(status=new).update(status=old)


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0002_initial'),
        ('workflows', '0002_workflow_env_vars_workflow_nextflow_config_and_more'),
    ]

    operations = [
        migrations.RenameField('job', 'completed_at', 'finished_at'),
        migrations.RenameField('jobstep', 'completed_at', 'finished_at'),
        migrations.RenameField('jobmessage', 'message_type', 'level'),
        migrations.RenameField('jobmessage', 'message', 'text'),
        migrations.AddField('job', 'app_id', models.CharField(blank=True, default='', max_length=255)),
        migrations.AddField('job', 'app_name', models.CharField(blank=True, default='', max_length=255)),
        migrations.AddField('job', 'app_version', models.CharField(blank=True, default='', max_length=50)),
        migrations.AddField('job', 'workflow_yaml', models.TextField(blank=True, default='')),
        migrations.AddField('job', 'app_dir', models.CharField(blank=True, default='', max_length=1024)),
        migrations.AddField('job', 'cancel_requested', models.BooleanField(default=False)),
        migrations.AddField('job', 'updated_at', models.DateTimeField(
            auto_now=True, default=django.utils.timezone.now), preserve_default=False),
        migrations.AddField('job', 'uploads', models.JSONField(blank=True, default=dict)),
        migrations.AddField('job', 'pid', models.IntegerField(blank=True, null=True)),
        migrations.AddField('job', 'pgid', models.IntegerField(blank=True, null=True)),
        migrations.AddField('job', 'current_step', models.IntegerField(default=0)),
        migrations.AddField('job', 'deleted_at', models.DateTimeField(blank=True, null=True)),
        migrations.AddField('job', 'purged_at', models.DateTimeField(
            blank=True, help_text='Workspace removed', null=True)),
        migrations.AddField('jobstep', 'processes', models.JSONField(blank=True, default=list)),
        migrations.AddField('jobmessage', 'step', models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
            related_name='messages', to='jobs.jobstep')),
        migrations.CreateModel(
            name='JobOutput',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False,
                                           verbose_name='ID')),
                ('output_id', models.CharField(max_length=255)),
                ('label', models.CharField(blank=True, default='', max_length=255)),
                ('path', models.CharField(max_length=1024)),
                ('size', models.BigIntegerField(default=0)),
                ('download_count', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('job', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                          related_name='outputs', to='jobs.job')),
            ],
            options={'db_table': 'job_outputs', 'ordering': ['output_id', 'path']},
        ),
        migrations.RunPython(forwards, backwards),
    ]
