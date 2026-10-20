from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from .models import User


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
