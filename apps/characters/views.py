from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy
from apps.characters.models import Character

class CharacterListView(LoginRequiredMixin, ListView):
    model = Character
    template_name = 'characters/list.html'
    context_object_name = 'characters'

    def get_queryset(self):
        return Character.objects.filter(owner=self.request.user)

class CharacterCreateView(LoginRequiredMixin, CreateView):
    model = Character
    fields = ['name', 'description', 'appearance_description', 'clothing_description', 'personality', 'avatar']
    template_name = 'characters/form.html'
    success_url = reverse_lazy('characters:list')

    def form_valid(self, form):
        form.instance.owner = self.request.user
        messages.success(self.request, f"Character '{form.instance.name}' created successfully.")
        return super().form_valid(form)

class CharacterDetailView(LoginRequiredMixin, DetailView):
    model = Character
    template_name = 'characters/detail.html'
    context_object_name = 'character'

    def get_queryset(self):
        return Character.objects.filter(owner=self.request.user)

class CharacterUpdateView(LoginRequiredMixin, UpdateView):
    model = Character
    fields = ['name', 'description', 'appearance_description', 'clothing_description', 'personality', 'avatar']
    template_name = 'characters/form.html'

    def get_queryset(self):
        return Character.objects.filter(owner=self.request.user)

    def get_success_url(self):
        messages.success(self.request, f"Character '{self.object.name}' updated successfully.")
        return reverse_lazy('characters:detail', kwargs={'pk': self.object.pk})

class CharacterDeleteView(LoginRequiredMixin, DeleteView):
    model = Character
    template_name = 'characters/confirm_delete.html'
    success_url = reverse_lazy('characters:list')
    context_object_name = 'character'

    def get_queryset(self):
        return Character.objects.filter(owner=self.request.user)

    def delete(self, request, *args, **kwargs):
        char = self.get_object()
        messages.success(request, f"Character '{char.name}' deleted successfully.")
        return super().delete(request, *args, **kwargs)
