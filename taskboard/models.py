from django.db import models
from django.conf import settings


class TaskCategory(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "name"]
        verbose_name_plural = "Task Categories"

    def __str__(self):
        return self.name


class TaskItem(models.Model):
    PRIORITY_CHOICES = [
        ("New", "New"),
        ("Low", "Low"),
        ("Medium", "Medium"),
        ("High", "High"),
        ("Urgent", "Urgent"),
    ]

    title = models.CharField(max_length=255)
    category = models.ForeignKey(
        TaskCategory, on_delete=models.CASCADE, related_name="tasks"
    )
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="New")
    done = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="taskboard_tasks",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
