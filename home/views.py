import smtplib

from django.conf import settings
from django.contrib import messages
from django.core.mail import EmailMessage
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import TemplateView

from .forms import LeadForm
from .models import Project, Testimonial, VideoReview, LeadAttachment


def home(request):
    MAX_TESTIMONIALS = 6

    featured = Testimonial.objects.filter(
        is_active=True,
        is_featured=True
    ).order_by("order")

    others = Testimonial.objects.filter(
        is_active=True,
        is_featured=False
    ).order_by("order")

    testimonials = list(featured) + list(others)
    testimonials = testimonials[:MAX_TESTIMONIALS]

    return render(request, "home/home.html", {
        "testimonials": testimonials
    })


def projects(request):
    projects = Project.objects.all()
    return render(request, "home/projects.html", {"projects": projects})


def project_detail(request, slug):
    project = get_object_or_404(Project, slug=slug)

    before = project.projectbeforeimage_set.all()
    construction = project.projectconstructionimage_set.all()
    after = project.projectafterimage_set.all()

    return render(request, "home/project_detail.html", {
        "project": project,
        "before": before,
        "construction": construction,
        "after": after,
    })


class Video(TemplateView):
    template_name = 'home/video.html'





class Newconstruction(TemplateView):
    template_name = 'home/newconstruction.html'


class KitchenRemodeling(TemplateView):
    template_name = 'home/kitchen_remodeling.html'


class Bathroom(TemplateView):
    template_name = 'home/bathroom.html'


class Garage(TemplateView):
    template_name = 'home/garage.html'


class Homeremodel(TemplateView):
    template_name = 'home/homeremodel.html'


class Homeadditions(TemplateView):
    template_name = 'home/homeadditions.html'


def videoreviews(request):
    featured = VideoReview.objects.filter(is_active=True, is_featured=True).order_by("order", "-created_at")

    qs = VideoReview.objects.filter(is_active=True, is_featured=False).order_by("order", "-created_at")
    paginator = Paginator(qs, 6)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    # AJAX request: return only the cards
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return render(request, "home/partials/_video_cards.html", {"page_obj": page_obj})

    return render(request, "home/videoreviews.html", {
        "featured": featured,
        "page_obj": page_obj,
    })


def create_lead(request):
    if request.method == 'POST':
        lead_form = LeadForm(request.POST, request.FILES)
        if lead_form.is_valid():
            consultation_request = lead_form.save()

            # Save uploaded attachments (optional)
            uploaded_files = lead_form.cleaned_data.get("attachments") or []
            for f in uploaded_files:
                LeadAttachment.objects.create(lead=consultation_request, file=f)

            # Prepare email content including selected consultation types
            consultation_types_display = consultation_request.get_consultation_types_display()
            # Include attachment names in the email (do NOT attach large files to email)
            attachment_names = [f.name for f in uploaded_files]
            attachments_text = (
                "\n\nAttachments:\n" + "\n".join(f"- {n}" for n in attachment_names)
            ) if attachment_names else ""

            full_message = (
                f"Name: {consultation_request.name}\n"
                f"Email: {consultation_request.email}\n"
                f"Phone: {consultation_request.phone}\n"
                f"Consultation Types: {consultation_types_display}\n\n"
                f"Message:\n{consultation_request.message}"
            ) + attachments_text

            try:
                email_message = EmailMessage(
                    subject=f'Request Consultation from {consultation_request.name}',
                    body=full_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=['info@garagelions.com'],
                )
                email_message.send(fail_silently=False)
                return redirect('create_lead_success')
            except smtplib.SMTPException:
                messages.error(request, 'There was an error sending your request. Please try again later.')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        lead_form = LeadForm()

    return render(request, 'home/create_lead.html', {'lead_form': lead_form})


def create_lead_success(request):
    return render(request, 'home/createlead_success.html')


class CopyrightPage(TemplateView):
    template_name = "home/copyright.html"



class Terms(TemplateView):
    template_name = "home/terms.html"

class Privacy(TemplateView):
    template_name = "home/privacy.html"