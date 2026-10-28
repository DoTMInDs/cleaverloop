from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils.translation import gettext_lazy as _

class UserManager(BaseUserManager):
    """Custom user manager where email is the unique identifier for auth."""
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_('The Email must be set'))
        email = self.normalize_email(email).lower()
        username = extra_fields.pop('username', None) or email.split('@')[0]
        user = self.model(email=email, username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))

        return self.create_user(email, password, **extra_fields)

class User(AbstractUser):
    """Custom User model with email as primary login identity."""
    email = models.EmailField(_('email address'), unique=True, db_index=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    starter_credits_granted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    objects = UserManager()

    class Meta:
        ordering = ['-date_joined']
        verbose_name = _('User')
        verbose_name_plural = _('Users')

    def __str__(self):
        return self.email


class ReferralRedemption(models.Model):
    """Tracks referral code redemptions and bonus credit awards between creators."""
    referrer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='referrals_made',
        help_text='The user whose referral code was redeemed.'
    )
    referee = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='referral_redeemed',
        help_text='The user who redeemed the referral code (one per account).'
    )
    code_used = models.CharField(max_length=16, db_index=True)
    credits_awarded = models.PositiveIntegerField(default=1000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Referral Redemption')
        verbose_name_plural = _('Referral Redemptions')

    def __str__(self):
        return f"{self.referee.email} redeemed {self.code_used} from {self.referrer.email}"
