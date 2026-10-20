from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    ordering = ['email']
    list_display = ['email', 'full_name', 'is_staff']
    search_fields = ['email', 'full_name']
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Profil', {'fields': ('full_name',)}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {'fields': ('email', 'full_name', 'password1', 'password2')}),
    )
