"""Account pages: register, log in and log out."""

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView

from .forms import LoginForm, RegisterForm


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    form_class = LoginForm
    redirect_authenticated_user = True


class LogoutView(auth_views.LogoutView):
    """Logs out on POST only (a link could be triggered by another site)."""


class RegisterView(CreateView):
    """Create an account and log straight in."""

    template_name = "accounts/register.html"
    form_class = RegisterForm
    success_url = reverse_lazy("meetups:map")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        messages.success(self.request, f"Welcome, {self.object.username}! Create a group to get started.")
        return response
