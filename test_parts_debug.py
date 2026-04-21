import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'garagelions.settings.production')
django.setup()

from panel.views import part_list
from django.test import RequestFactory
from django.contrib.auth import get_user_model

User = get_user_model()
user = User.objects.filter(is_staff=True).first()
print(f"User: {user}")

factory = RequestFactory()
request = factory.get('/panel/parts/')
request.user = user

try:
    response = part_list(request)
    print(f"OK - Status: {response.status_code}")
except Exception as e:
    import traceback
    traceback.print_exc()
