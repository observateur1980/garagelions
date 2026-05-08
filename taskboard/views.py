import csv
import io
import json
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.db import models, transaction
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404
from django.utils.text import slugify
from django.views.decorators.http import require_POST, require_http_methods

from .models import TaskCategory, TaskItem


VALID_PRIORITIES = {p[0] for p in TaskItem.PRIORITY_CHOICES}


def admin_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser):
            return HttpResponseForbidden("Access denied.")
        return view_func(request, *args, **kwargs)
    return wrapper


@admin_required
def board(request):
    return render(request, "taskboard/board.html")


@admin_required
def api_tasks(request):
    if request.method == "GET":
        category_filter = request.GET.get("category")
        qs = TaskItem.objects.select_related("category", "created_by")
        if category_filter:
            qs = qs.filter(category__slug=category_filter)
        tasks = [
            {
                "id": t.id,
                "title": t.title,
                "category": t.category.slug,
                "categoryName": t.category.name,
                "priority": t.priority,
                "done": t.done,
                "createdAt": t.created_at.isoformat(),
                "updatedAt": t.updated_at.isoformat(),
            }
            for t in qs
        ]
        return JsonResponse({"tasks": tasks})

    if request.method == "POST":
        data = json.loads(request.body)
        title = data.get("title", "").strip()
        category_slug = data.get("category", "")
        priority = data.get("priority", "New")

        if not title:
            return JsonResponse({"error": "Title is required."}, status=400)

        category = get_object_or_404(TaskCategory, slug=category_slug)
        task = TaskItem.objects.create(
            title=title,
            category=category,
            priority=priority,
            created_by=request.user,
        )
        return JsonResponse({
            "id": task.id,
            "title": task.title,
            "category": task.category.slug,
            "categoryName": task.category.name,
            "priority": task.priority,
            "done": task.done,
            "createdAt": task.created_at.isoformat(),
            "updatedAt": task.updated_at.isoformat(),
        }, status=201)

    return JsonResponse({"error": "Method not allowed."}, status=405)


@admin_required
@require_http_methods(["DELETE", "PATCH"])
def api_task_detail(request, pk):
    task = get_object_or_404(TaskItem, pk=pk)

    if request.method == "DELETE":
        task.delete()
        return JsonResponse({"ok": True})

    data = json.loads(request.body or "{}")
    update_fields = []

    if "title" in data:
        title = (data.get("title") or "").strip()
        if not title:
            return JsonResponse({"error": "Title cannot be empty."}, status=400)
        task.title = title
        update_fields.append("title")

    if "category" in data:
        category = get_object_or_404(TaskCategory, slug=data["category"])
        task.category = category
        update_fields.append("category")

    if "priority" in data:
        priority = data["priority"]
        if priority not in VALID_PRIORITIES:
            return JsonResponse({"error": "Invalid priority."}, status=400)
        task.priority = priority
        update_fields.append("priority")

    if update_fields:
        update_fields.append("updated_at")
        task.save(update_fields=update_fields)

    return JsonResponse({
        "id": task.id,
        "title": task.title,
        "category": task.category.slug,
        "categoryName": task.category.name,
        "priority": task.priority,
        "done": task.done,
        "createdAt": task.created_at.isoformat(),
        "updatedAt": task.updated_at.isoformat(),
    })


@admin_required
@require_POST
def api_task_toggle(request, pk):
    task = get_object_or_404(TaskItem, pk=pk)
    task.done = not task.done
    task.save(update_fields=["done", "updated_at"])
    return JsonResponse({"id": task.id, "done": task.done})


@admin_required
@require_POST
def api_clear_completed(request):
    deleted, _ = TaskItem.objects.filter(done=True).delete()
    return JsonResponse({"deleted": deleted})


@admin_required
def api_categories(request):
    if request.method == "GET":
        cats = TaskCategory.objects.all()
        data = [
            {"id": c.id, "slug": c.slug, "name": c.name, "order": c.order}
            for c in cats
        ]
        return JsonResponse({"categories": data})

    if request.method == "POST":
        data = json.loads(request.body)
        name = data.get("name", "").strip()
        if not name:
            return JsonResponse({"error": "Name is required."}, status=400)

        base_slug = slugify(name) or "category"
        slug = base_slug
        counter = 2
        while TaskCategory.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1

        max_order = TaskCategory.objects.aggregate(m=models.Max("order"))["m"] or 0
        cat = TaskCategory.objects.create(name=name, slug=slug, order=max_order + 1)
        return JsonResponse(
            {"id": cat.id, "slug": cat.slug, "name": cat.name, "order": cat.order},
            status=201,
        )

    return JsonResponse({"error": "Method not allowed."}, status=405)


@admin_required
@require_http_methods(["DELETE"])
def api_category_detail(request, pk):
    cat = get_object_or_404(TaskCategory, pk=pk)
    cat.delete()
    return JsonResponse({"ok": True})


@admin_required
@require_POST
def api_import_csv(request):
    upload = request.FILES.get("file")
    if not upload:
        return JsonResponse({"error": "No file uploaded."}, status=400)

    try:
        raw = upload.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return JsonResponse({"error": "File must be UTF-8 encoded."}, status=400)

    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames:
        return JsonResponse({"error": "CSV is empty."}, status=400)

    normalized = {(name or "").strip().lower(): name for name in reader.fieldnames}
    if "category" not in normalized or "title" not in normalized:
        return JsonResponse(
            {"error": "CSV must have 'category' and 'title' columns (priority optional)."},
            status=400,
        )

    cat_col = normalized["category"]
    title_col = normalized["title"]
    prio_col = normalized.get("priority")

    created_categories = 0
    created_tasks = 0
    skipped = 0
    errors = []

    category_cache = {c.name.strip().lower(): c for c in TaskCategory.objects.all()}
    max_order = TaskCategory.objects.aggregate(m=models.Max("order"))["m"] or 0

    with transaction.atomic():
        for idx, row in enumerate(reader, start=2):
            cat_name = (row.get(cat_col) or "").strip()
            title = (row.get(title_col) or "").strip()
            priority = (row.get(prio_col) or "New").strip() if prio_col else "New"

            if not cat_name or not title:
                skipped += 1
                continue

            if priority not in VALID_PRIORITIES:
                priority = "New"

            key = cat_name.lower()
            category = category_cache.get(key)
            if category is None:
                base_slug = slugify(cat_name) or "category"
                slug = base_slug
                counter = 2
                while TaskCategory.objects.filter(slug=slug).exists():
                    slug = f"{base_slug}-{counter}"
                    counter += 1
                max_order += 1
                category = TaskCategory.objects.create(
                    name=cat_name, slug=slug, order=max_order
                )
                category_cache[key] = category
                created_categories += 1

            TaskItem.objects.create(
                title=title,
                category=category,
                priority=priority,
                created_by=request.user,
            )
            created_tasks += 1

    return JsonResponse({
        "createdTasks": created_tasks,
        "createdCategories": created_categories,
        "skipped": skipped,
        "errors": errors,
    })
