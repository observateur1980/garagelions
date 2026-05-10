from django.db import migrations


DEFAULT_ROLES = [
    {
        'code': 'project_manager',
        'label': 'Project Manager',
        'description': 'Works individual leads at one location.',
        'allows_multiple_locations': False,
        'sees_all_locations': False,
        'is_protected': True,
        'order': 10,
    },
    {
        'code': 'location_manager',
        'label': 'Multiple Locations Manager',
        'description': 'Oversees one or more sales points and their teams.',
        'allows_multiple_locations': True,
        'sees_all_locations': False,
        'is_protected': True,
        'order': 20,
    },
    {
        'code': 'territory_manager',
        'label': 'Territory Manager',
        'description': 'Corporate view: sees every active sales point.',
        'allows_multiple_locations': True,
        'sees_all_locations': True,
        'is_protected': True,
        'order': 30,
    },
]


def seed_roles(apps, schema_editor):
    Role = apps.get_model('account', 'Role')
    for entry in DEFAULT_ROLES:
        Role.objects.update_or_create(
            code=entry['code'],
            defaults={k: v for k, v in entry.items() if k != 'code'},
        )


def unseed_roles(apps, schema_editor):
    Role = apps.get_model('account', 'Role')
    Role.objects.filter(code__in=[r['code'] for r in DEFAULT_ROLES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0011_role_alter_projectmanager_role'),
    ]

    operations = [
        migrations.RunPython(seed_roles, unseed_roles),
    ]
