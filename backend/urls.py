from django.urls import path

from django_rest_passwordreset.views import (
    reset_password_request_token,
    reset_password_confirm,
)

from backend.views import (
    CatalogView,
    SignInView,
    LogInView,
    CategoryView,
    SellerView,
    ProductInfoView,
    BasketView,
    UserDetailsView,
    ContactView,
    OrderView,
    SellerStateView,
    SellerOrdersView,
    ConfirmUserView,
)


app_name = "backend"

urlpatterns = [
    path("seller/update", CatalogView.as_view(), name="seller-update"),
    path("seller/state", SellerStateView.as_view(), name="seller-state"),
    path("seller/orders", SellerOrdersView.as_view(), name="seller-orders"),
    path("user/register", SignInView.as_view(), name="user-register"),
    path(
        "user/register/confirm", ConfirmUserView.as_view(), name="user-register-confirm"
    ),
    path("user/details", UserDetailsView.as_view(), name="user-details"),
    path("user/contact", ContactView.as_view(), name="user-contact"),
    path("user/login", LogInView.as_view(), name="user-login"),
    path("user/password_reset", reset_password_request_token, name="password-reset"),
    path(
        "user/password_reset/confirm",
        reset_password_confirm,
        name="password-reset-confirm",
    ),
    path("categories", CategoryView.as_view(), name="categories"),
    path("sellers", SellerView.as_view(), name="sellers"),
    path("products", ProductInfoView.as_view(), name="sellers"),
    path("basket", BasketView.as_view(), name="basket"),
    path("order", OrderView.as_view(), name="order"),
]
