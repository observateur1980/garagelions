import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'garagelions.settings.production')
django.setup()

from panel.models import PartCategory, Unit, Part

# Global categories
for name in ['Garage Flooring', 'Garage Cabinets', 'Slatwall', 'Storage Racks', 'Garage Door', 'Lighting', 'Electrical']:
    PartCategory.objects.get_or_create(name=name, sales_point=None, defaults={'is_active': True})
print(f"Categories: {PartCategory.objects.filter(sales_point__isnull=True).count()}")

# Global units
for name, abbr in [('Each', 'ea'), ('Hour', 'hr'), ('Square Foot', 'sq ft'), ('Linear Foot', 'lin ft'), ('Square Yard', 'sq yd'), ('Piece', 'pc'), ('Set', 'set'), ('Box', 'box'), ('Bag', 'bag'), ('Gallon', 'gal')]:
    Unit.objects.get_or_create(name=name, sales_point=None, defaults={'abbreviation': abbr, 'is_active': True})
print(f"Units: {Unit.objects.filter(sales_point__isnull=True).count()}")

# Global parts
cats = {c.name: c for c in PartCategory.objects.filter(sales_point__isnull=True)}
ea = Unit.objects.filter(name='Each', sales_point__isnull=True).first()
sqft = Unit.objects.filter(name='Square Foot', sales_point__isnull=True).first()
lft = Unit.objects.filter(name='Linear Foot', sales_point__isnull=True).first()
hr = Unit.objects.filter(name='Hour', sales_point__isnull=True).first()
st = Unit.objects.filter(name='Set', sales_point__isnull=True).first()

parts = [
    ('Polyaspartic Floor Coating', '', cats.get('Garage Flooring'), sqft),
    ('Epoxy Floor Coating', '', cats.get('Garage Flooring'), sqft),
    ('Floor Prep & Grinding', '', cats.get('Garage Flooring'), sqft),
    ('Decorative Flake Broadcast', '', cats.get('Garage Flooring'), sqft),
    ('Premium Garage Cabinet Set 6pc', 'CAB-6PC', cats.get('Garage Cabinets'), st),
    ('Wall Cabinet 24x30', 'CAB-2430', cats.get('Garage Cabinets'), ea),
    ('Base Cabinet 24x34', 'CAB-2434', cats.get('Garage Cabinets'), ea),
    ('Workbench Cabinet 72in', 'CAB-WB72', cats.get('Garage Cabinets'), ea),
    ('Slatwall Panel 4x8', 'SW-48', cats.get('Slatwall'), ea),
    ('Slatwall Hook Pack 10pc', 'SW-HP10', cats.get('Slatwall'), st),
    ('Slatwall Basket Large', 'SW-BL', cats.get('Slatwall'), ea),
    ('Overhead Storage Rack 4x8', 'SR-48', cats.get('Storage Racks'), ea),
    ('Overhead Storage Rack 4x6', 'SR-46', cats.get('Storage Racks'), ea),
    ('Garage Door Insulation Kit', 'GD-INS', cats.get('Garage Door'), ea),
    ('LED Shop Light 4ft', 'LT-4FT', cats.get('Lighting'), ea),
    ('LED Recessed Light 6in', 'LT-R6', cats.get('Lighting'), ea),
    ('Electrical Outlet Install', 'EL-OUT', cats.get('Electrical'), ea),
    ('220V Outlet Install', 'EL-220', cats.get('Electrical'), ea),
    ('Labor - Installation', '', None, hr),
    ('Labor - Removal & Disposal', '', None, hr),
]

created = 0
for name, sku, cat, unit in parts:
    _, c = Part.objects.get_or_create(name=name, sales_point=None, defaults={'sku': sku, 'category': cat, 'unit': unit, 'unit_price': 0})
    if c:
        created += 1
print(f"Parts: created {created}, total {Part.objects.filter(sales_point__isnull=True).count()}")
print("Done!")
