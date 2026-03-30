import smtplib

from django.conf import settings
from django.contrib import messages
from django.core.mail import EmailMessage
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import TemplateView

from .forms import LeadForm
from .models import Gallery, LeadAttachment, Testimonial, VideoReview


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




def galleries(request):
    gallery_list = Gallery.objects.filter(is_active=True).prefetch_related("items")
    return render(request, "home/gallery.html", {"galleries": gallery_list})


def gallery_detail(request, slug):
    gallery = get_object_or_404(
        Gallery.objects.filter(is_active=True).prefetch_related("items"),
        slug=slug,
    )
    items = list(gallery.items.all())
    return render(request, "home/gallery_detail.html", {"gallery": gallery, "items": items})


class Service(TemplateView):
    template_name = 'home/service.html'

    def get_context_data(self, **kwargs):
        context = super(Service, self).get_context_data(**kwargs)
        return context


class Product(TemplateView):
    template_name = 'home/product.html'

    def get_context_data(self, **kwargs):
        context = super(Product, self).get_context_data(**kwargs)
        return context


class About(TemplateView):
    template_name = 'home/about.html'

    def get_context_data(self, **kwargs):
        context = super(About, self).get_context_data(**kwargs)
        return context




class Video(TemplateView):
    template_name = 'home/video.html'



def videoreviews(request):
    featured = VideoReview.objects.filter(is_active=True, is_featured=True).order_by("order", "-created_at")

    qs = VideoReview.objects.filter(is_active=True, is_featured=False).order_by("order", "-created_at")
    paginator = Paginator(qs, 6)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

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

            uploaded_files = lead_form.cleaned_data.get("attachments") or []
            for f in uploaded_files:
                LeadAttachment.objects.create(lead=consultation_request, file=f)

            consultation_types_display = consultation_request.get_consultation_types_display()
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


class GarageCabinet(TemplateView):
    template_name = 'home/garage_cabinet.html'

    def get_context_data(self, **kwargs):
        context = super(GarageCabinet, self).get_context_data(**kwargs)
        return context


class GarageFlooring(TemplateView):
    template_name = 'home/garage_flooring.html'

    def get_context_data(self, **kwargs):
        context = super(GarageFlooring, self).get_context_data(**kwargs)
        return context


class GarageSlatwall(TemplateView):
    template_name = 'home/garage_slatwall.html'

    def get_context_data(self, **kwargs):
        context = super(GarageSlatwall, self).get_context_data(**kwargs)
        return context


class StorageRack(TemplateView):
    template_name = 'home/storage_rack.html'

    def get_context_data(self, **kwargs):
        context = super(StorageRack, self).get_context_data(**kwargs)
        return context


class GarageMakeover(TemplateView):
    template_name = 'home/garage_makeover.html'

    def get_context_data(self, **kwargs):
        context = super(GarageMakeover, self).get_context_data(**kwargs)
        return context


class GarageDoor(TemplateView):
    template_name = 'home/garage_door.html'

    def get_context_data(self, **kwargs):
        context = super(GarageDoor, self).get_context_data(**kwargs)
        return context


class GarageConversion(TemplateView):
    template_name = 'home/garage_conversion.html'

    def get_context_data(self, **kwargs):
        context = super(GarageConversion, self).get_context_data(**kwargs)
        return context


class CarLift(TemplateView):
    template_name = 'home/car_lift.html'

    def get_context_data(self, **kwargs):
        context = super(CarLift, self).get_context_data(**kwargs)
        return context
