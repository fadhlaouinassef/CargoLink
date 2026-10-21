import re
from datetime import timedelta

from django.core import mail
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import PasswordResetCode, User


class SignupTests(TestCase):
    def setUp(self):
        self.url = reverse('authentification:register')
        self.data = {
            'full_name': 'Amine Test',
            'email': 'Amine@example.com',
            'password1': 'Cargo-Strong-872!',
            'password2': 'Cargo-Strong-872!',
        }

    def test_get_displays_form(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="password1"')

    def test_signup_creates_user_with_hashed_password(self):
        response = self.client.post(self.url, self.data)
        self.assertRedirects(response, reverse('authentification:login'))
        user = User.objects.get()
        self.assertEqual(user.full_name, self.data['full_name'])
        self.assertEqual(user.email, 'amine@example.com')
        self.assertNotEqual(user.password, self.data['password1'])
        self.assertTrue(user.check_password(self.data['password1']))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_invalid_submissions_do_not_create_users(self):
        for changes in [
            {'full_name': ''},
            {'email': 'invalid'},
            {'password2': 'Different-password-872!'},
            {'password1': '123', 'password2': '123'},
        ]:
            with self.subTest(changes=changes):
                response = self.client.post(self.url, {**self.data, **changes})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'].errors)
                self.assertFalse(User.objects.exists())

    def test_duplicate_email_is_rejected_regardless_of_case(self):
        User.objects.create_user('AMINE@example.com', 'Existing-password-872!')
        response = self.client.post(self.url, self.data)
        self.assertIn('email', response.context['form'].errors)
        self.assertEqual(User.objects.count(), 1)

    def test_database_rejects_duplicate_email_regardless_of_case(self):
        User.objects.create_user('amine@example.com', 'Existing-password-872!')
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create(email='AMINE@example.com', full_name='Duplicate')

    def test_signup_requires_csrf_token(self):
        response = Client(enforce_csrf_checks=True).post(self.url, self.data)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.exists())


class AdminUserManagementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            'admin@example.com',
            'Admin-Strong-872!',
            full_name='Admin CargoLink',
            role=User.Role.ADMIN,
        )
        self.user = User.objects.create_user(
            'user@example.com',
            'User-Strong-872!',
            full_name='Utilisateur Test',
            role=User.Role.PME,
        )
        self.client.force_login(self.admin)

    def test_management_requires_admin_role(self):
        self.client.logout()
        non_admin = self.client.post(reverse('authentification:admin_user_create'))
        self.assertEqual(non_admin.status_code, 302)
        self.assertIn(reverse('authentification:login'), non_admin['Location'])

        self.client.force_login(self.user)
        response = self.client.get(reverse('authentification:admin_dashboard'))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_create_and_validate_user(self):
        response = self.client.post(reverse('authentification:admin_user_create'), {
            'full_name': 'Nouveau Transporteur',
            'email': 'new@example.com',
            'role': User.Role.TRANSPORTEUR,
            'is_active': 'on',
            'password1': 'New-Strong-872!',
            'password2': 'New-Strong-872!',
        })
        self.assertRedirects(response, reverse('authentification:admin_dashboard'))
        created = User.objects.get(email='new@example.com')
        self.assertEqual(created.role, User.Role.TRANSPORTEUR)
        self.assertTrue(created.check_password('New-Strong-872!'))

        invalid = self.client.post(reverse('authentification:admin_user_create'), {
            'full_name': '',
            'email': 'not-an-email',
            'role': User.Role.PME,
            'password1': 'short',
            'password2': 'different',
        })
        self.assertEqual(invalid.status_code, 200)
        self.assertTrue(invalid.context['form'].errors)

    def test_admin_can_filter_and_manage_account(self):
        response = self.client.get(reverse('authentification:admin_dashboard'), {
            'q': 'Utilisateur',
            'role': User.Role.PME,
            'status': 'active',
        })
        self.assertContains(response, 'user@example.com')
        self.assertNotContains(response, 'admin@example.com')

        toggle_url = reverse('authentification:admin_user_toggle_active', args=[self.user.pk])
        self.assertRedirects(self.client.post(toggle_url), reverse(
            'authentification:admin_user_detail', args=[self.user.pk],
        ))
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

        delete_url = reverse('authentification:admin_user_delete', args=[self.user.pk])
        self.assertRedirects(self.client.post(delete_url), reverse('authentification:admin_dashboard'))
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

    def test_admin_cannot_disable_or_delete_self(self):
        toggle_url = reverse('authentification:admin_user_toggle_active', args=[self.admin.pk])
        self.client.post(toggle_url)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

        delete_url = reverse('authentification:admin_user_delete', args=[self.admin.pk])
        self.client.post(delete_url)
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())


class LoginTests(TestCase):
    def setUp(self):
        self.url = reverse('authentification:login')
        self.password = 'Cargo-Strong-872!'
        User.objects.create_user(
            email='amine@example.com',
            password=self.password,
            full_name='Amine Test',
        )

    def test_get_displays_login_form(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="username"')
        self.assertContains(response, 'name="password"')

    def test_pme_credentials_redirect_to_pme_dashboard(self):
        response = self.client.post(self.url, {
            'username': 'AMINE@EXAMPLE.COM',
            'password': self.password,
        })
        self.assertRedirects(response, reverse('pme:dashboard'))
        self.assertEqual(str(self.client.session['_auth_user_id']), str(User.objects.get(email='amine@example.com').pk))

    def test_destinataire_credentials_redirect_to_destinataire_dashboard(self):
        User.objects.create_user(
            email='dest@example.com',
            password=self.password,
            full_name='Destinataire Test',
            role=User.Role.DESTINATAIRE,
        )
        response = self.client.post(self.url, {
            'username': 'dest@example.com',
            'password': self.password,
        })
        self.assertRedirects(response, reverse('destinataire:dashboard'))

    def test_admin_credentials_redirect_to_dashboard(self):
        User.objects.create_user(
            email='admin@example.com',
            password=self.password,
            full_name='Admin Test',
            role=User.Role.ADMIN,
        )
        response = self.client.post(self.url, {
            'username': 'admin@example.com',
            'password': self.password,
        })
        self.assertRedirects(response, reverse('authentification:admin_dashboard'))

    def test_admin_redirect_ignores_external_dashboard_destination(self):
        User.objects.create_user(
            email='admin@example.com',
            password=self.password,
            full_name='Admin Test',
            role=User.Role.ADMIN,
        )
        response = self.client.post(f'{self.url}?next=/somewhere/', {
            'username': 'admin@example.com',
            'password': self.password,
        })
        self.assertRedirects(response, reverse('authentification:admin_dashboard'))

    def test_invalid_credentials_do_not_log_user_in(self):
        response = self.client.post(self.url, {
            'username': 'amine@example.com',
            'password': 'incorrect-password',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        self.assertNotIn('_auth_user_id', self.client.session)


class ForgotPasswordTests(TestCase):
    def setUp(self):
        self.email = 'amine@example.com'
        self.user = User.objects.create_user(self.email, 'Old-Password-872!', full_name='Amine Test')
        self.forget_url = reverse('authentification:forget_password')
        self.verify_url = reverse('authentification:verify_code')
        self.reset_url = reverse('authentification:reset_password')

    def request_code(self, email=None):
        response = self.client.post(self.forget_url, {'email': email or self.email})
        self.assertRedirects(response, self.verify_url)

    def sent_code(self):
        return re.search(r'\b(\d{6})\b', mail.outbox[-1].body).group(1)

    def test_pages_display(self):
        self.assertContains(self.client.get(self.forget_url), 'name="email"')
        self.request_code()
        self.assertContains(self.client.get(self.verify_url), 'name="code"')

    def test_email_is_validated(self):
        for value in ['', 'invalid']:
            with self.subTest(value=value):
                response = self.client.post(self.forget_url, {'email': value})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'].errors)
        self.assertEqual(len(mail.outbox), 0)

    def test_code_is_emailed_and_stored_hashed(self):
        self.request_code('AMINE@example.com')
        code = self.sent_code()
        self.assertEqual(mail.outbox[0].to, [self.email])
        stored = PasswordResetCode.objects.get(user=self.user)
        self.assertNotEqual(stored.code, code)
        self.assertTrue(stored.matches(code))

    def test_unknown_email_gets_same_response_without_email(self):
        self.request_code('nobody@example.com')
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(PasswordResetCode.objects.exists())

    def test_resend_is_rate_limited(self):
        self.request_code()
        response = self.client.post(self.forget_url, {'email': self.email})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

    def test_verify_requires_requested_code(self):
        self.assertRedirects(self.client.get(self.verify_url), self.forget_url)
        self.assertRedirects(self.client.get(self.reset_url), self.forget_url)

    def test_code_format_is_validated(self):
        self.request_code()
        for value in ['', '123', 'abcdef', '1234567']:
            with self.subTest(value=value):
                response = self.client.post(self.verify_url, {'code': value})
                self.assertEqual(response.status_code, 200)
                self.assertIn('code', response.context['form'].errors)

    def test_wrong_code_then_lockout(self):
        self.request_code()
        good = self.sent_code()
        wrong = '000000' if good != '000000' else '111111'
        for _ in range(PasswordResetCode.MAX_ATTEMPTS):
            response = self.client.post(self.verify_url, {'code': wrong})
            self.assertEqual(response.status_code, 200)
        response = self.client.post(self.verify_url, {'code': good})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('reset_user_id', self.client.session)

    def test_expired_code_is_rejected(self):
        self.request_code()
        PasswordResetCode.objects.update(created_at=timezone.now() - timedelta(minutes=11))
        response = self.client.post(self.verify_url, {'code': self.sent_code()})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('reset_user_id', self.client.session)

    def test_full_flow_changes_password(self):
        self.request_code()
        response = self.client.post(self.verify_url, {'code': self.sent_code()})
        self.assertRedirects(response, self.reset_url)
        response = self.client.post(self.reset_url, {
            'new_password1': 'Brand-New-Pass-4411!',
            'new_password2': 'Brand-New-Pass-4411!',
        })
        self.assertRedirects(response, reverse('authentification:login'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Brand-New-Pass-4411!'))
        self.assertFalse(PasswordResetCode.objects.exists())
        self.assertNotIn('reset_user_id', self.client.session)
        self.assertRedirects(self.client.get(self.reset_url), self.forget_url)

    def test_admin_full_flow_logs_in_and_redirects_to_dashboard(self):
        self.user.role = User.Role.ADMIN
        self.user.save(update_fields=['role'])
        self.request_code()
        self.client.post(self.verify_url, {'code': self.sent_code()})
        response = self.client.post(self.reset_url, {
            'new_password1': 'Brand-New-Admin-Pass-4411!',
            'new_password2': 'Brand-New-Admin-Pass-4411!',
        })
        self.assertRedirects(response, reverse('authentification:admin_dashboard'))
        self.assertEqual(str(self.client.session['_auth_user_id']), str(self.user.pk))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Brand-New-Admin-Pass-4411!'))

    def test_new_password_is_validated(self):
        self.request_code()
        self.client.post(self.verify_url, {'code': self.sent_code()})
        for data in [
            {'new_password1': 'Brand-New-Pass-4411!', 'new_password2': 'Different-4411!'},
            {'new_password1': '123', 'new_password2': '123'},
        ]:
            with self.subTest(data=data):
                response = self.client.post(self.reset_url, data)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'].errors)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Old-Password-872!'))
