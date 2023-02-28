from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _

from django_rest_passwordreset.tokens import get_token_generator


STATE_CHOICES = (
    ("basket", "В корзине"),
    ("new", "Новый"),
    ("confirmed", "Подтвержден"),
    ("assembled", "Собран"),
    ("sent", "Отправлен"),
    ("delivered", "Доставлен"),
    ("canceled", "Отменен"),
)

USER_TYPE_CHOICES = (
    ("seller", "Продавец"),
    ("buyer", "Покупатель"),
)


class User(AbstractUser):
    EMAIL_FIELD = "email"

    email = models.EmailField(verbose_name="Почта", unique=True)
    type = models.CharField(
        max_length=16, verbose_name="Тип", choices=USER_TYPE_CHOICES, default="client"
    )

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    def __str__(self):
        return self.email


class Contact(models.Model):
    user = models.ForeignKey(
        User,
        verbose_name="Пользователь",
        related_name="contacts",
        blank=True,
        on_delete=models.CASCADE,
    )
    address = models.CharField(max_length=128, verbose_name="Адрес")
    phone = models.CharField(max_length=16, verbose_name="Телефон")

    class Meta:
        verbose_name = "Контакт"
        verbose_name_plural = "Контакты"

    def __str__(self):
        return self.phone


class Seller(models.Model):
    user = models.OneToOneField(
        User,
        verbose_name="Пользователь",
        blank=True,
        null=True,
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=64, verbose_name="Название")
    state = models.BooleanField(verbose_name="Статус получения заказов", default=True)
    url = models.URLField(verbose_name="Ссылка на каталог", null=True, blank=True)

    class Meta:
        verbose_name = "Продавец"
        verbose_name_plural = "Продавцы"

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=64, verbose_name="Название")
    shops = models.ManyToManyField(
        Seller, verbose_name="Продавцы", related_name="categories", blank=True
    )

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=64, verbose_name="Название")
    category = models.ForeignKey(
        Category,
        verbose_name="Категория",
        related_name="products",
        blank=True,
        on_delete=models.CASCADE,
    )

    class Meta:
        verbose_name = "Продукт"
        verbose_name_plural = "Продукты"

    def __str__(self):
        return self.name


class ProductInfo(models.Model):
    name = models.CharField(max_length=64, verbose_name="Название")
    product = models.ForeignKey(
        Product,
        verbose_name="Продукт",
        related_name="product_infos",
        blank=True,
        on_delete=models.CASCADE,
    )
    seller = models.ForeignKey(
        Seller,
        verbose_name="Продавец",
        related_name="product_infos",
        blank=True,
        on_delete=models.CASCADE,
    )
    quantity = models.PositiveIntegerField(verbose_name="Кол-во")
    price = models.PositiveIntegerField(verbose_name="Цена")
    price_rrc = models.PositiveIntegerField(verbose_name="РРЦ")
    article = models.PositiveIntegerField(verbose_name="Артикул")

    class Meta:
        verbose_name = "Информация"
        verbose_name_plural = "Информация"


class Parameter(models.Model):
    name = models.CharField(max_length=64, verbose_name="Название")

    class Meta:
        verbose_name = "Параметр"
        verbose_name_plural = "Параметры"

    def __str__(self):
        return self.name


class ProductParameter(models.Model):
    product_info = models.ForeignKey(
        ProductInfo,
        verbose_name="Информация",
        related_name="product_parameters",
        blank=True,
        on_delete=models.CASCADE,
    )
    parameter = models.ForeignKey(
        Parameter,
        verbose_name="Параметр",
        related_name="product_parameters",
        blank=True,
        on_delete=models.CASCADE,
    )
    value = models.CharField(max_length=64, verbose_name="Значение")

    class Meta:
        verbose_name = "Параметр"
        verbose_name_plural = "Параметры"


class Order(models.Model):
    user = models.ForeignKey(
        Contact,
        verbose_name="Покупатель",
        related_name="orders",
        blank=True,
        on_delete=models.CASCADE,
    )
    dt = models.DateTimeField(auto_now_add=True)
    state = models.CharField(
        verbose_name="Статус", choices=STATE_CHOICES, max_length=16
    )

    class Meta:
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"

    def __str__(self):
        return str(self.dt)


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        verbose_name="Заказ",
        related_name="ordered_items",
        blank=True,
        on_delete=models.CASCADE,
    )
    product = models.ForeignKey(
        ProductInfo,
        verbose_name="Информация",
        related_name="ordered_items",
        blank=True,
        on_delete=models.CASCADE,
    )
    shop = models.ForeignKey(
        Seller,
        verbose_name="Заказ",
        related_name="ordered_items",
        blank=True,
        on_delete=models.CASCADE,
    )
    quantity = models.PositiveIntegerField(verbose_name="Кол-во")

    class Meta:
        verbose_name = "Заказанная позиция"
        verbose_name_plural = "Заказанные позиции"


class ConfirmEmailToken(models.Model):
    class Meta:
        verbose_name = "Токен"
        verbose_name_plural = "Токены"

    @staticmethod
    def generate_key():
        return get_token_generator().generate_token()

    user = models.ForeignKey(
        User,
        related_name="confirm_email_tokens",
        on_delete=models.CASCADE,
        verbose_name=_("Associated user"),
    )

    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name=_("Generation time")
    )

    key = models.CharField(_("Key"), max_length=64, db_index=True, unique=True)

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self.generate_key()
        return super(ConfirmEmailToken, self).save(*args, **kwargs)

    def __str__(self):
        return "Password reset token for user {user}".format(user=self.user)
