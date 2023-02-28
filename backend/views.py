from requests import get
from yaml import load as load_yaml, Loader
from ujson import loads as load_json
from distutils.util import strtobool

from django.http import JsonResponse
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError
from django.db.models import Q, Sum, F

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.generics import ListAPIView
from rest_framework.authtoken.models import Token

from backend.signals import new_user_registered, new_order
from backend.models import (
    Seller,
    Product,
    ProductInfo,
    Category,
    Parameter,
    ProductParameter,
    Order,
    OrderItem,
    Contact,
    ConfirmEmailToken,
)
from backend.serializers import (
    UserSerializer,
    ProductSerializer,
    ProductInfoSerializer,
    OrderItemSerializer,
    OrderSerializer,
    SellerSerializer,
    ContactSerializer,
    CategorySerializer,
)


class CatalogView(APIView):
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {"Status": False, "Error": "Log in required"}, status=403
            )
        if request.user.type != "seller":
            return JsonResponse(
                {"Status": False, "Error": "Only for sellers"}, status=403
            )

        url = request.data.get("url")

        if url:
            validate_url = URLValidator()

            try:
                validate_url(url)
            except ValidationError as e:
                return JsonResponse({"Status": False, "Error": str(e)})

            stream = get(url).content
            data = load_yaml(stream, Loader=Loader)

            seller, _ = Seller.objects.get_or_create(
                name=data["seller"], user_id=request.user.id
            )

            for category in data["categories"]:
                category_object, _ = Category.objects.get_or_create(
                    id=category["id"], name=category["name"]
                )
                category_object.sellers.add(seller.id)
                category_object.save()

            ProductInfo.objects.filter(seller_id=seller.id).delete()

            for item in data["goods"]:
                product, _ = Product.objects.get_or_create(
                    name=item["name"], category_id=item["category"]
                )
                product_info = ProductInfo.objects.create(
                    name=item["model"],
                    product_id=product.id,
                    seller_id=seller.id,
                    quantity=item["quantity"],
                    price=item["price"],
                    price_rrc=item["price_rrc"],
                    article=item["id"],
                )

                for name, value in item["parameters"].items():
                    parameter_object, _ = Parameter.objects.get_or_create(name=name)
                    ProductParameter.objects.create(
                        product_info_id=product_info.id,
                        parameter_id=parameter_object.id,
                        value=value,
                    )

            return JsonResponse({"Status": True})

        return JsonResponse(
            {"Status": False, "Error": "All required arguments not provided"}
        )


class LogInView(APIView):
    def post(self, request, *args, **kwargs):
        if {"email", "password"}.issubset(request.data):
            user = authenticate(
                request,
                username=request.data["email"],
                password=request.data["password"],
            )

            if user is not None:
                if user.is_active:
                    token, _ = Token.objects.get_or_create(user=user)

                    return JsonResponse({"Status": True, "Token": token.key})

            return JsonResponse({"Status": False, "Errors": "Failed to authorize"})

        return JsonResponse(
            {"Status": False, "Errors": "Necessary arguments are not specified"}
        )


class SignInView(APIView):
    def post(self, request, *args, **kwargs):
        if {"email", "password", "type"}.issubset(request.data):
            try:
                validate_password(request.data["password"])
            except ValidationError:
                return JsonResponse(
                    {
                        "Status": False,
                        "Errors": "An error occurred during password validation",
                    }
                )

            request.data._mutable = True
            request.data.update({})
            user_serializer = UserSerializer(data=request.data)

            if user_serializer.is_valid():
                user = user_serializer.save()
                user.set_password(request.data["password"])
                user.save()
                new_user_registered.send(sender=self.__class__, user_id=user.id)

                return JsonResponse({"Status": True})

            else:
                return JsonResponse({"Status": False, "Errors": user_serializer.errors})

        else:
            JsonResponse(
                {"Status": False, "Errors": "Necessary arguments are not specified"}
            )


class ConfirmUserView(APIView):
    def post(self, request, *args, **kwargs):
        if {"email", "token"}.issubset(request.data):
            token = ConfirmEmailToken.objects.filter(
                user__email=request.data["email"], key=request.data["token"]
            ).first()
            if token:
                token.user.is_active = True
                token.user.save()
                token.delete()
                return JsonResponse({"Status": True})
            else:
                return JsonResponse(
                    {
                        "Status": False,
                        "Errors": "The token or email is incorrectly specified",
                    }
                )

        return JsonResponse(
            {"Status": False, "Errors": "Necessary arguments are not specified"}
        )


class UserDetailsView(APIView):
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {"Status": False, "Error": "Log in required"}, status=403
            )

        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {"Status": False, "Error": "Log in required"}, status=403
            )

        if "password" in request.data:
            try:
                validate_password(request.data["password"])
            except ValidationError:
                return JsonResponse(
                    {
                        "Status": False,
                        "Errors": "An error occurred during password validation",
                    }
                )

            request.user.set_password(request.data["password"])

        user_serializer = UserSerializer(request.user, data=request.data, partial=True)
        if user_serializer.is_valid():
            user_serializer.save()
            return JsonResponse({"Status": True})
        else:
            return JsonResponse({"Status": False, "Errors": user_serializer.errors})


class CategoryView(ListAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class ProductView(ListAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer


class SellerView(ListAPIView):
    queryset = Seller.objects.filter(state=True)
    serializer_class = SellerSerializer


class ProductInfoView(APIView):
    def get(self, request, *args, **kwargs):
        query = Q(seller__state=True)
        seller_id = request.query_params.get("seller_id")
        category_id = request.query_params.get("category_id")

        if seller_id:
            query = query & Q(seller_id=seller_id)
        if category_id:
            query = query & Q(product__category_id=category_id)

        queryset = (
            ProductInfo.objects.filter(query)
            .select_related("seller", "product__category")
            .prefetch_related("product_parameters__parameter")
            .distinct()
        )

        serializer = ProductInfoSerializer(queryset, many=True)

        return Response(serializer.data)


class BasketView(APIView):
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {"Status": False, "Error": "Log in required"}, status=403
            )

        basket = (
            Order.objects.filter(user_id=request.user.id, state="basket")
            .prefetch_related(
                "ordered_items__product_info__product__category",
                "ordered_items__product_info__product_parameters__parameter",
            )
            .annotate(
                total_sum=Sum(
                    F("ordered_items__quantity")
                    * F("ordered_items__product_info__price")
                )
            )
            .distinct()
        )

        serializer = OrderSerializer(basket, many=True)

        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {"Status": False, "Error": "Log in required"}, status=403
            )

        items_string = request.data.get("items")

        if items_string:
            try:
                items_dict = load_json(items_string)
            except ValueError:
                JsonResponse({"Status": False, "Errors": "Invalid request format"})

            basket, _ = Order.objects.get_or_create(
                user_id=request.user.id, state="basket"
            )
            objects_created = 0

            for order_item in items_dict:
                order_item.update({"order": basket.id})
                serializer = OrderItemSerializer(data=order_item)

                if serializer.is_valid():
                    try:
                        serializer.save()
                    except IntegrityError as error:
                        return JsonResponse({"Status": False, "Errors": str(error)})

                    objects_created += 1

                else:
                    JsonResponse({"Status": False, "Errors": serializer.errors})

                return JsonResponse(
                    {"Status": True, "Created objects": objects_created}
                )

        return JsonResponse(
            {"Status": False, "Errors": "Necessary arguments are not specified"}
        )

    def delete(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {"Status": False, "Error": "Log in required"}, status=403
            )

        items_string = request.data.get("items")

        if items_string:
            items_list = items_string.split(",")
            basket, _ = Order.objects.get_or_create(
                user_id=request.user.id, state="basket"
            )
            query = Q()
            objects_deleted = False

            for order_item_id in items_list:
                if order_item_id.isdigit():
                    query = query | Q(order_id=basket.id, id=order_item_id)
                    objects_deleted = True

            if objects_deleted:
                deleted_count = OrderItem.objects.filter(query).delete()[0]

                return JsonResponse({"Status": True, "Deleted objects": deleted_count})

        return JsonResponse(
            {"Status": False, "Errors": "Necessary arguments are not specified"}
        )

    def put(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {"Status": False, "Error": "Log in required"}, status=403
            )

        items_string = request.data.get("items")

        if items_string:
            try:
                items_dict = load_json(items_string)
            except ValueError:
                JsonResponse({"Status": False, "Errors": "Invalid request format"})

            basket, _ = Order.objects.get_or_create(
                user_id=request.user.id, state="basket"
            )
            objects_updated = 0

            for order_item in items_dict:
                if (
                    type(order_item["id"]) == int
                    and type(order_item["quantity"]) == int
                ):
                    objects_updated += OrderItem.objects.filter(
                        order_id=basket.id, id=order_item["id"]
                    ).update(quantity=order_item["quantity"])

            return JsonResponse({"Status": True, "Updated objects": objects_updated})

        return JsonResponse(
            {"Status": False, "Errors": "Necessary arguments are not specified"}
        )


class SellerStateView(APIView):
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {"Status": False, "Error": "Log in required"}, status=403
            )

        if request.user.type != "seller":
            return JsonResponse(
                {"Status": False, "Error": "Only for sellers"}, status=403
            )

        sellers = request.user.sellers
        serializer = SellerSerializer(sellers)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {"Status": False, "Error": "Log in required"}, status=403
            )

        if request.user.type != "seller":
            return JsonResponse(
                {"Status": False, "Error": "Only for sellers"}, status=403
            )
        state = request.data.get("state")
        if state:
            try:
                Seller.objects.filter(user_id=request.user.id).update(
                    state=strtobool(state)
                )
                return JsonResponse({"Status": True})
            except ValueError as error:
                return JsonResponse({"Status": False, "Errors": str(error)})

        return JsonResponse(
            {"Status": False, "Errors": "Necessary arguments are not specified"}
        )


class SellerOrdersView(APIView):
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {"Status": False, "Error": "Log in required"}, status=403
            )

        if request.user.type != "seller":
            return JsonResponse(
                {"Status": False, "Error": "Only for sellers"}, status=403
            )

        order = (
            Order.objects.filter(
                ordered_items__product_info__seller__user_id=request.user.id
            )
            .exclude(state="basket")
            .prefetch_related(
                "ordered_items__product_info__product__category",
                "ordered_items__product_info__product_parameters__parameter",
            )
            .select_related("contact")
            .annotate(
                total_sum=Sum(
                    F("ordered_items__quantity")
                    * F("ordered_items__product_info__price")
                )
            )
            .distinct()
        )

        serializer = OrderSerializer(order, many=True)
        return Response(serializer.data)


class ContactView(APIView):
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {"Status": False, "Error": "Log in required"}, status=403
            )
        contact = Contact.objects.filter(user_id=request.user.id)
        serializer = ContactSerializer(contact, many=True)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {"Status": False, "Error": "Log in required"}, status=403
            )

        if {"address", "phone"}.issubset(request.data):
            request.data._mutable = True
            request.data.update({"user": request.user.id})
            serializer = ContactSerializer(data=request.data)

            if serializer.is_valid():
                serializer.save()
                return JsonResponse({"Status": True})
            else:
                JsonResponse({"Status": False, "Errors": serializer.errors})

        return JsonResponse(
            {"Status": False, "Errors": "Necessary arguments are not specified"}
        )

    def delete(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {"Status": False, "Error": "Log in required"}, status=403
            )

        items_string = request.data.get("items")
        if items_string:
            items_list = items_string.split(",")
            query = Q()
            objects_deleted = False
            for contact_id in items_list:
                if contact_id.isdigit():
                    query = query | Q(user_id=request.user.id, id=contact_id)
                    objects_deleted = True

            if objects_deleted:
                deleted_count = Contact.objects.filter(query).delete()[0]
                return JsonResponse({"Status": True, "Deleted objects": deleted_count})
        return JsonResponse(
            {"Status": False, "Errors": "Necessary arguments are not specified"}
        )

    def put(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {"Status": False, "Error": "Log in required"}, status=403
            )

        if "id" in request.data:
            if request.data["id"].isdigit():
                contact = Contact.objects.filter(
                    id=request.data["id"], user_id=request.user.id
                ).first()
                if contact:
                    serializer = ContactSerializer(
                        contact, data=request.data, partial=True
                    )
                    if serializer.is_valid():
                        serializer.save()
                        return JsonResponse({"Status": True})
                    else:
                        JsonResponse({"Status": False, "Errors": serializer.errors})

        return JsonResponse(
            {"Status": False, "Errors": "Necessary arguments are not specified"}
        )


class OrderView(APIView):
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {"Status": False, "Error": "Log in required"}, status=403
            )
        order = (
            Order.objects.filter(user_id=request.user.id)
            .exclude(state="basket")
            .prefetch_related(
                "ordered_items__product_info__product__category",
                "ordered_items__product_info__product_parameters__parameter",
            )
            .select_related("contact")
            .annotate(
                total_sum=Sum(
                    F("ordered_items__quantity")
                    * F("ordered_items__product_info__price")
                )
            )
            .distinct()
        )

        serializer = OrderSerializer(order, many=True)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {"Status": False, "Error": "Log in required"}, status=403
            )

        if {"id", "contact"}.issubset(request.data):
            if request.data["id"].isdigit():
                try:
                    is_updated = Order.objects.filter(
                        user_id=request.user.id, id=request.data["id"]
                    ).update(contact_id=request.data["contact"], state="new")
                except IntegrityError:
                    return JsonResponse(
                        {
                            "Status": False,
                            "Errors": "The arguments are specified incorrectly",
                        }
                    )
                else:
                    if is_updated:
                        new_order.send(sender=self.__class__, user_id=request.user.id)
                        return JsonResponse({"Status": True})

        return JsonResponse(
            {"Status": False, "Errors": "Necessary arguments are not specified"}
        )
