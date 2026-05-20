import json
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.db.models import Q, Count, Sum
from django.utils import timezone
from datetime import datetime, date, timedelta
from .models import *
from django.contrib.auth.hashers import make_password, check_password
from .optimizer import DeliveryOptimizer, PriceCalculator
from .strategies import (
    OrderContext, StandardPricing, LoyaltyPricing, DiscountPricing,
    StandardDelivery, ExpressDelivery, PickupStrategy
)
from .singletons import ConfigManager, EventBus, CacheManager
from .factories import ClassicPizzaFactory, MeatLoversFactory, CheeseLoversFactory, VeggieFactory
from .decorators import BasePizza, ToppingDecorator
from .observers import OrderSubject, KitchenObserver, CustomerObserver, AdminObserver
from .proxy import admin_access_required, AdminAccessProxy, CachedReportProxy
from .loyalty_adapter import LoyaltySystemAdapter
from .external_loyalty_service import LegacyLoyaltySystem

admin_proxy = AdminAccessProxy()
report_proxy = CachedReportProxy()

order_subject = OrderSubject()
order_subject.attach(KitchenObserver())
order_subject.attach(CustomerObserver())
order_subject.attach(AdminObserver())

event_bus = EventBus()

def index(request):
    ingredients = Ingredient.objects.all()
    pizzas = Pizza.objects.filter(is_available=True)
    total_clients = Client.objects.count()
    couriers_count = Courier.objects.count()
    pizzas_count = Pizza.objects.filter(is_available=True).count()
    
    context = {
        'ingredients': ingredients,
        'pizzas': pizzas,
        'total_clients': total_clients,
        'couriers_count': couriers_count,
        'pizzas_count': pizzas_count,
    }
    return render(request, 'index.html', context)

def register(request):
    if request.method == 'POST':
        name = request.POST['name']
        email = request.POST['email']
        password = make_password(request.POST['password'])
        if Client.objects.filter(email=email).exists():
            messages.error(request, 'Email уже занят')
        else:
            Client.objects.create(name=name, email=email, password=password)
            messages.success(request, 'Регистрация успешна')
            return redirect('login')
    return render(request, 'register.html')

def login_view(request):
    if request.method == 'POST':
        email = request.POST['email']
        password = request.POST['password']
        try:
            user = Client.objects.get(email=email)
            if check_password(password, user.password):
                request.session['user_id'] = user.client_id
                request.session['role'] = 'client'
                request.session['user_name'] = user.name
                request.session['loyalty_points'] = user.loyalty_points
                return redirect('index')
        except Client.DoesNotExist:
            pass
        messages.error(request, 'Неверный email или пароль')
    return render(request, 'login.html')

def admin_login(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        try:
            admin = Admin.objects.get(Q(username=username) | Q(email=username))
            if check_password(password, admin.password):
                request.session['user_id'] = admin.admin_id
                request.session['role'] = 'admin'
                request.session['user_name'] = admin.username
                admin_proxy.set_cached_orders(None)
                admin_proxy.set_cached_stats(None)
                return redirect('admin_dashboard')
        except Admin.DoesNotExist:
            pass
        messages.error(request, 'Неверные данные администратора')
    return render(request, 'admin_login.html')

def logout_view(request):
    request.session.flush()
    return redirect('index')

def constructor(request):
    ingredients = Ingredient.objects.all()
    factory_preview = None
    
    if request.method == 'POST':
        base_id = int(request.POST['base'])
        sauce_id = int(request.POST['sauce'])
        cheese_id = int(request.POST['cheese'])
        topping_ids = list(map(int, request.POST.getlist('toppings')))[:8]

        base = Ingredient.objects.get(ingredient_id=base_id)
        sauce = Ingredient.objects.get(ingredient_id=sauce_id)
        cheese = Ingredient.objects.get(ingredient_id=cheese_id)

        if "толст" in base.ingredient_name.lower():
            factory = MeatLoversFactory()
            factory_style = "Мясная (толстое тесто)"
        elif "чеддер" in cheese.ingredient_name.lower():
            factory = CheeseLoversFactory()
            factory_style = "Сырная"
        elif any(word in base.ingredient_name.lower() for word in ["гриб", "ананас"]):
            factory = VeggieFactory()
            factory_style = "Вегетарианская"
        else:
            factory = ClassicPizzaFactory()
            factory_style = "Классическая"

        pizza = BasePizza(base, sauce, cheese)
        toppings_list = []
        for tid in topping_ids:
            topping = Ingredient.objects.get(ingredient_id=tid)
            pizza = ToppingDecorator(pizza, topping)
            toppings_list.append(topping.ingredient_name)

        final_price = pizza.get_cost()
        final_description = pizza.get_description()

        custom = CustomPizza.objects.create(
            client_id=request.session.get('user_id'),
            custom_price=final_price,
            is_favorite=request.POST.get('save_favorite') == 'on',
            composition={
                'factory_style': factory_style,
                'description': final_description,
                'base': base.ingredient_name,
                'sauce': sauce.ingredient_name,
                'cheese': cheese.ingredient_name,
                'toppings': toppings_list
            }
        )
        for tid in topping_ids:
            CustomPizzaIngredient.objects.create(custom_pizza=custom, ingredient_id=tid)
        
        cart = request.session.get('cart', {})
        cart_key = f"custom_{custom.custom_pizza_id}"
        cart[cart_key] = {
            'type': 'custom',
            'id': custom.custom_pizza_id,
            'name': f'Кастомная пицца #{custom.custom_pizza_id} ({factory_style})',
            'price': final_price,
            'quantity': 1
        }
        request.session['cart'] = cart
        
        messages.success(request, f'Пицца добавлена в корзину (Фабрика: {factory_style}, Состав: {final_description})')
        return redirect('cart')
    
    if request.method == 'GET' and request.GET.get('preview_factory'):
        factory_type = request.GET.get('preview_factory')
        if factory_type == 'classic':
            factory = ClassicPizzaFactory()
            style = "Классическая"
        elif factory_type == 'meat':
            factory = MeatLoversFactory()
            style = "Мясная"
        elif factory_type == 'cheese':
            factory = CheeseLoversFactory()
            style = "Сырная"
        elif factory_type == 'veggie':
            factory = VeggieFactory()
            style = "Вегетарианская"
        else:
            factory = None
            style = None
        
        if factory:
            base = factory.create_base()
            sauce = factory.create_sauce()
            cheese = factory.create_cheese()
            
            pizza = BasePizza(base, sauce, cheese)
            
            factory_preview = {
                'style': style,
                'base': base.ingredient_name,
                'sauce': sauce.ingredient_name,
                'cheese': cheese.ingredient_name,
                'price': pizza.get_cost(),
                'description': f"{base.ingredient_name} + {sauce.ingredient_name} + {cheese.ingredient_name}"
            }

    return render(request, 'constructor.html', {
        'ingredients': ingredients,
        'factory_preview': factory_preview
    })

def favorites(request):
    if 'user_id' not in request.session:
        return redirect('login')
    favs = CustomPizza.objects.filter(client_id=request.session['user_id'], is_favorite=True)
    return render(request, 'favorites.html', {'favorites': favs})

def remove_from_favorites(request, pizza_id):
    if 'user_id' not in request.session:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)
    try:
        custom_pizza = CustomPizza.objects.get(custom_pizza_id=pizza_id, client_id=request.session['user_id'])
        custom_pizza.is_favorite = False
        custom_pizza.save()
        return JsonResponse({'success': True})
    except CustomPizza.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Pizza not found'}, status=404)

def notifications_view(request):
    if request.session.get('role') != 'admin':
        return redirect('admin_login')
    notifications = OrderNotification.objects.all().order_by('-created_at')
    return render(request, 'notifications.html', {'notifications': notifications})

def cart_view(request):
    cart = request.session.get('cart', {})
    cart_items = []
    total = 0
    for key, item in cart.items():
        item_total = item['price'] * item['quantity']
        total += item_total
        cart_items.append({
            'key': key,
            'type': item['type'],
            'name': item['name'],
            'price': item['price'],
            'quantity': item['quantity'],
            'total': item_total
        })
    delivery_fee = 200 if total < 500 else 0
    grand_total = total + delivery_fee
    context = {
        'cart_items': cart_items,
        'total': total,
        'delivery_fee': delivery_fee,
        'grand_total': grand_total,
        'free_delivery_threshold': 500,
        'cart_count': sum(item['quantity'] for item in cart.values())
    }
    return render(request, 'cart.html', context)

def add_to_cart(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        item_type = data.get('type')
        item_id = data.get('id')
        name = data.get('name')
        price = data.get('price')
        quantity = data.get('quantity', 1)
        cart = request.session.get('cart', {})
        key = f"{item_type}_{item_id}"
        if key in cart:
            cart[key]['quantity'] += quantity
        else:
            cart[key] = {
                'type': item_type,
                'id': item_id,
                'name': name,
                'price': price,
                'quantity': quantity
            }
        request.session['cart'] = cart
        cart_count = sum(item['quantity'] for item in cart.values())
        return JsonResponse({
            'success': True,
            'cart_count': cart_count,
            'message': f'{name} добавлен в корзину'
        })
    return JsonResponse({'success': False, 'error': 'Invalid request'})

def remove_from_cart(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        key = data.get('key')
        cart = request.session.get('cart', {})
        if key in cart:
            del cart[key]
            request.session['cart'] = cart
        cart_count = sum(item['quantity'] for item in cart.values())
        return JsonResponse({
            'success': True,
            'cart_count': cart_count
        })
    return JsonResponse({'success': False, 'error': 'Invalid request'})

def update_cart_quantity(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        key = data.get('key')
        quantity = data.get('quantity', 1)
        cart = request.session.get('cart', {})
        if key in cart and quantity > 0:
            cart[key]['quantity'] = quantity
            request.session['cart'] = cart
            item_total = cart[key]['price'] * quantity
            return JsonResponse({
                'success': True,
                'item_total': item_total
            })
    return JsonResponse({'success': False, 'error': 'Invalid request'})

def create_order(request):
    if 'user_id' not in request.session:
        return redirect('login')
    
    cart = request.session.get('cart', {})
    total = sum(item['price'] * item['quantity'] for item in cart.values())
    
    if total == 0:
        messages.warning(request, 'Корзина пуста')
        return redirect('constructor')
    
    if request.method == 'POST':
        delivery_type = request.POST.get('delivery_type')
        address = request.POST.get('address', '')
        comment = request.POST.get('comment', '')
        
        from .order_processor import DeliveryOrderProcessor, PickupOrderProcessor
        
        if delivery_type == 'delivery':
            processor = DeliveryOrderProcessor()
        else:
            processor = PickupOrderProcessor()
        
        order = processor.process(request, cart, total)
        
        if delivery_type == 'delivery':
            order.address = address
        order.save()
        
        total_quantity = sum(item['quantity'] for item in cart.values())
        
        if total_quantity >= 3:
            pricing_strategy = DiscountPricing(10)
            food_total_with_discount = pricing_strategy.calculate(total, 0, 1)
        else:
            food_total_with_discount = total
        
        if delivery_type == 'pickup':
            delivery_fee = 0
        else:
            if food_total_with_discount >= 500:
                delivery_fee = 0
            else:
                delivery_fee = 200
        
        final_total = food_total_with_discount + delivery_fee
        
        order.amount = final_total
        order.save()

        legacy_system = LegacyLoyaltySystem()
        loyalty_adapter = LoyaltySystemAdapter(legacy_system)
        bonus_to_give = 10
        success = loyalty_adapter.give_bonus(request.session['user_id'], bonus_to_give)
        if success:
            messages.success(request, f'Вам начислено {bonus_to_give} бонусных баллов!')
            client = Client.objects.get(client_id=request.session['user_id'])
            request.session['loyalty_points'] = client.loyalty_points
        else:
            messages.warning(request, 'Не удалось начислить бонусы.')
        
        order_subject.notify(order)
        event_bus.publish('order_status_changed', {'order_id': order.order_id, 'status': order.status})
        
        admin_proxy.set_cached_orders(None)
        admin_proxy.set_cached_stats(None)
        
        messages.success(request, f'Заказ #{order.order_id} успешно создан')
        return redirect('my_orders')
    
    total_quantity = sum(item['quantity'] for item in cart.values())
    
    discount_percent = 0
    food_total_with_discount = total
    
    if total_quantity >= 3:
        discount_percent = 10
        pricing_strategy = DiscountPricing(10)
        food_total_with_discount = pricing_strategy.calculate(total, 0, 1)
    
    delivery_type = request.GET.get('delivery_type')
    if not delivery_type:
        delivery_type = request.session.get('last_delivery_type', 'delivery')
    
    request.session['last_delivery_type'] = delivery_type
    
    if delivery_type == 'pickup':
        delivery_fee = 0
    else:
        if food_total_with_discount >= 500:
            delivery_fee = 0
        else:
            delivery_fee = 200
    
    grand_total = food_total_with_discount + delivery_fee
    
    cart_items = []
    for key, item in cart.items():
        cart_items.append({
            'key': key,
            'name': item['name'],
            'price': item['price'],
            'quantity': item['quantity'],
            'total': item['price'] * item['quantity']
        })
    
    free_delivery_need = max(0, 500 - food_total_with_discount)
    
    context = {
        'cart_items': cart_items,
        'total': total,
        'discount_percent': discount_percent,
        'discount_amount': total - food_total_with_discount,
        'food_total_with_discount': food_total_with_discount,
        'delivery_fee': delivery_fee,
        'grand_total': grand_total,
        'free_delivery_threshold': 500,
        'free_delivery_need': free_delivery_need,
        'selected_delivery_type': delivery_type,
        'address': request.GET.get('address', ''),
        'comment': request.GET.get('comment', ''),
    }
    return render(request, 'checkout.html', context)

def my_orders(request):
    if 'user_id' not in request.session:
        return redirect('login')
    orders = Order.objects.filter(client_id=request.session['user_id']).order_by('-created_at')
    return render(request, 'my_orders.html', {'orders': orders})

@admin_access_required()
def admin_dashboard(request):
    if request.session.get('role') != 'admin':
        return redirect('admin_login')
    
    force_refresh = request.GET.get('refresh') == '1'
    
    if force_refresh:
        admin_proxy.set_cached_orders(None)
        admin_proxy.set_cached_stats(None)
        messages.success(request, 'Кэш очищен! Данные загружены из базы данных.')
    
    cached_orders = admin_proxy.get_cached_orders()
    
    if cached_orders is not None and not force_refresh:
        orders = cached_orders
        from_cache = True
    else:
        orders = list(Order.objects.all().order_by('-created_at'))
        admin_proxy.set_cached_orders(orders)
        from_cache = False
    
    ingredients = Ingredient.objects.all()
    clients = Client.objects.all()
    couriers = Courier.objects.all()
    
    cached_stats = admin_proxy.get_cached_stats()
    
    if cached_stats is not None and not force_refresh:
        total_orders = cached_stats['total_orders']
        total_clients = cached_stats['total_clients']
        total_revenue = cached_stats['total_revenue']
    else:
        total_orders = len(orders)
        total_clients = clients.count()
        total_revenue = sum(o.amount for o in orders if getattr(o, 'status', '') == 'Доставлен')
        admin_proxy.set_cached_stats({
            'total_orders': total_orders,
            'total_clients': total_clients,
            'total_revenue': total_revenue
        })
    
    context = {
        'orders': orders,
        'ingredients': ingredients,
        'clients': clients,
        'couriers': couriers,
        'total_orders': total_orders,
        'total_clients': total_clients,
        'total_revenue': total_revenue,
        'from_cache': from_cache,
    }
    return render(request, 'admin_dashboard.html', context)

@admin_access_required()
def kitchen(request):
    if request.session.get('role') != 'admin':
        return redirect('admin_login')
    orders = Order.objects.all().order_by('created_at')
    return render(request, 'kitchen.html', {'orders': orders})

def update_status(request, order_id):
    order = get_object_or_404(Order, order_id=order_id)
    if order.delivery_type == 'delivery':
        statuses = ['Принят', 'Готовится', 'В печи', 'Передан курьеру', 'Доставлен']
    else:
        statuses = ['Принят', 'Готовится', 'В печи', 'Доставлен']
    try:
        idx = statuses.index(order.status)
        if idx < len(statuses) - 1:
            new_status = statuses[idx + 1]
            order.status = new_status
            order.save()
            OrderStatusHistory.objects.create(order=order, status=order.status)
            order_subject.notify(order)
            event_bus.publish('order_status_changed', {'order_id': order.order_id, 'status': order.status})
            if order.delivery_type == 'delivery':
                if order.status == 'Передан курьеру' and order.courier:
                    courier = order.courier
                    courier.status = 'В пути'
                    courier.save()
                elif order.status == 'Доставлен' and order.courier:
                    courier = order.courier
                    courier.status = 'Свободен'
                    courier.save()
            
            admin_proxy.set_cached_orders(None)
            admin_proxy.set_cached_stats(None)
            
            return JsonResponse({
                'status': order.status, 
                'order_id': order.order_id,
                'is_finished': False
            })
        else:
            return JsonResponse({
                'status': order.status, 
                'order_id': order.order_id,
                'is_finished': True
            })
    except ValueError:
        pass
    return JsonResponse({'status': order.status, 'order_id': order.order_id, 'is_finished': True})

@admin_access_required()
def courier_view(request):
    if request.session.get('role') != 'admin':
        return redirect('admin_login')
    couriers = Courier.objects.all()
    return render(request, 'courier.html', {'couriers': couriers})

def init_data(request):
    if not Ingredient.objects.exists():
        ingredients_data = [
            ("Тонкое тесто", 120, "base"),
            ("Среднее тесто", 140, "base"),
            ("Толстое тесто", 150, "base"),
            ("Кетчуп", 50, "sauce"),
            ("Сырный соус", 70, "sauce"),
            ("Соус Барбекю", 60, "sauce"),
            ("Веганский песто", 80, "sauce"),
            ("Сливочный соус", 70, "sauce"),
            ("Моцарелла", 90, "cheese"),
            ("Чеддер", 100, "cheese"),
            ("Растительный сыр", 110, "cheese"),
        ]
        for name, price, cat in ingredients_data:
            Ingredient.objects.create(ingredient_name=name, price=price, category=cat)

        Courier.objects.create(name="Иван Иванов", phone="89161234567", status="Свободен")
        Courier.objects.create(name="Петр Сидоров", phone="89167654321", status="Свободен")
        Courier.objects.create(name="Сергей Смирнов", phone="89163456789", status="Свободен")

        if not Admin.objects.exists():
            Admin.objects.create(username="admin", password=make_password("admin"), email="admin@pizzaflow.com", permissions="full")

        if not Pizza.objects.exists():
            Pizza.objects.create(name="Маргарита", description="Томатный соус, моцарелла, свежие помидоры, базилик", base_price=499, category="Классическая")
            Pizza.objects.create(name="Пепперони", description="Пикантная пепперони, томатный соус, моцарелла", base_price=599, category="Мясная")
            Pizza.objects.create(name="Четыре сыра", description="Моцарелла, пармезан, горгонзола, рикотта", base_price=649, category="Сырная")
            Pizza.objects.create(name="BBQ", description="Соус барбекю, курица, бекон, моцарелла", base_price=649, category="Мясная")

        messages.success(request, 'Начальные данные загружены')
    return redirect('index')

def pizza_menu(request):
    pizzas = Pizza.objects.filter(is_available=True)
    return render(request, 'menu.html', {'pizzas': pizzas})

def optimize_route_api(request):
    if request.method == 'GET':
        pending_orders = Order.objects.filter(
            status__in=['Принят', 'В печи', 'Передан курьеру'], 
            delivery_type='delivery'
        ).order_by('-order_id')[:10]
        
        if not pending_orders:
            return JsonResponse({'success': False, 'message': 'Нет заказов для доставки'})

        restaurant_coords = (55.751244, 37.618423)
        deliveries = []
        
        for i, order in enumerate(pending_orders):
            deliveries.append({
                'order_id': order.order_id,
                'lat': 55.751244 + (order.order_id * 0.0001), 
                'lng': 37.618423 + (order.order_id * 0.0001),
                'address': order.address or "Адрес не указан"
            })
            
        optimizer = DeliveryOptimizer()
        route, distance = optimizer.optimize_route(restaurant_coords, deliveries)
        
        response_data = {
            'success': True,
            'route': route,
            'distance_km': round(distance, 2),
            'orders_count': len(pending_orders)
        }

        return HttpResponse(
            json.dumps(response_data, ensure_ascii=False),
            content_type="application/json; charset=utf-8"
        )
    return JsonResponse({'error': 'Method not allowed'}, status=405)

def check_route_page(request):
    return render(request, 'logistics_check.html')

def get_config_api(request):
    if request.method == 'GET':
        config = ConfigManager()
        return JsonResponse(config.get_all())
    return JsonResponse({'error': 'Method not allowed'}, status=405)

def get_cart_count(request):
    cart = request.session.get('cart', {})
    count = sum(item.get('quantity', 1) for item in cart.values())
    return JsonResponse({'count': count})

def get_order_status(request, order_id):
    try:
        order = Order.objects.get(order_id=order_id)
        status_history = OrderStatusHistory.objects.filter(order=order).values('status', 'changed_at')
        return JsonResponse({
            'order_id': order.order_id,
            'status': order.status,
            'status_display': order.get_status_display(),
            'amount': order.amount,
            'delivery_type': order.delivery_type,
            'address': order.address,
            'created_at': order.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': order.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            'history': list(status_history)
        })
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Order not found'}, status=404)

def order_tracking(request, order_id):
    try:
        order = Order.objects.get(order_id=order_id)
        status_history = OrderStatusHistory.objects.filter(order=order).order_by('changed_at')
        if order.delivery_type == 'delivery':
            status_steps = [
                {'status': 'Принят', 'icon': '📋', 'description': 'Заказ принят'},
                {'status': 'Готовится', 'icon': '👨‍🍳', 'description': 'Пицца готовится'},
                {'status': 'В печи', 'icon': '🔥', 'description': 'Пицца в печи'},
                {'status': 'Передан курьеру', 'icon': '🛵', 'description': 'Курьер в пути'},
                {'status': 'Доставлен', 'icon': '✅', 'description': 'Заказ доставлен'},
            ]
        else:
            status_steps = [
                {'status': 'Принят', 'icon': '📋', 'description': 'Заказ принят'},
                {'status': 'Готовится', 'icon': '👨‍🍳', 'description': 'Пицца готовится'},
                {'status': 'В печи', 'icon': '🔥', 'description': 'Пицца в печи'},
                {'status': 'Доставлен', 'icon': '✅', 'description': 'Заказ готов к выдаче'},
            ]
        current_step = 0
        for i, step in enumerate(status_steps):
            if step['status'] == order.status:
                current_step = i
                break
        context = {
            'order': order,
            'status_history': status_history,
            'status_steps': status_steps,
            'current_step': current_step,
        }
        return render(request, 'order_tracking.html', context)
    except Order.DoesNotExist:
        messages.error(request, 'Заказ не найден')
        return redirect('index')

def cancel_order(request, order_id):
    if 'user_id' not in request.session:
        return JsonResponse({'error': 'Not authenticated'}, status=401)
    try:
        order = Order.objects.get(order_id=order_id, client_id=request.session['user_id'])
        cancel_allowed_statuses = ['Принят', 'Готовится', 'В печи']
        if order.status in cancel_allowed_statuses:
            order.status = 'Отменен'
            order.save()
            OrderStatusHistory.objects.create(order=order, status='Отменен')
            order_subject.notify(order)
            event_bus.publish('order_status_changed', {'order_id': order.order_id, 'status': order.status})
            if order.courier:
                courier = order.courier
                courier.status = 'Свободен'
                courier.save()
            
            admin_proxy.set_cached_orders(None)
            admin_proxy.set_cached_stats(None)
            
            messages.success(request, f'Заказ #{order_id} отменен')
            return JsonResponse({'success': True, 'message': 'Заказ отменен'})
        else:
            return JsonResponse({'error': 'Cannot cancel order in current status'}, status=400)
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Order not found'}, status=404)

def assign_courier_to_order(request, courier_id):
    if request.method == 'POST':
        data = json.loads(request.body)
        order_id = data.get('order_id')
        try:
            courier = Courier.objects.get(courier_id=courier_id)
            order = Order.objects.get(order_id=order_id)
            if courier.status == 'Свободен' and order.status == 'В печи' and order.delivery_type == 'delivery':
                order.courier = courier
                order.status = 'Передан курьеру'
                order.save()
                courier.status = 'В пути'
                courier.save()
                OrderStatusHistory.objects.create(order=order, status='Передан курьеру')
                order_subject.notify(order)
                event_bus.publish('order_status_changed', {'order_id': order.order_id, 'status': order.status})
                
                admin_proxy.set_cached_orders(None)
                admin_proxy.set_cached_stats(None)
                
                return JsonResponse({'success': True, 'message': f'Курьер {courier.name} назначен на заказ #{order_id}'})
            else:
                return JsonResponse({'error': 'Courier not available or order not ready'}, status=400)
        except (Courier.DoesNotExist, Order.DoesNotExist):
            return JsonResponse({'error': 'Courier or order not found'}, status=404)
    return JsonResponse({'error': 'Method not allowed'}, status=405)

@admin_access_required()
def sales_report(request):
    if request.session.get('role') != 'admin':
        return redirect('admin_login')
    
    force_refresh = request.GET.get('refresh') == '1'
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    cached_report = report_proxy.get_sales_report(days=30, force_refresh=force_refresh)
    
    if cached_report is not None and not force_refresh:
        cached_report['from_cache'] = True
        return render(request, 'reports/sales.html', cached_report)
    
    orders = Order.objects.filter(created_at__gte=start_date, status='Доставлен')
    total_revenue = sum(o.amount for o in orders)
    total_orders = orders.count()
    avg_order_value = total_revenue / total_orders if total_orders > 0 else 0
    daily_stats = []
    for i in range(30):
        day = end_date - timedelta(days=i)
        day_orders = orders.filter(created_at__date=day.date())
        daily_stats.append({
            'date': day.strftime('%Y-%m-%d'),
            'orders': day_orders.count(),
            'revenue': sum(o.amount for o in day_orders)
        })
    
    context = {
        'total_revenue': total_revenue,
        'total_orders': total_orders,
        'avg_order_value': avg_order_value,
        'daily_stats': daily_stats,
        'from_cache': False,
    }
    
    report_proxy.set_sales_report(30, context)
    
    return render(request, 'reports/sales.html', context)

@admin_access_required()
def popular_pizzas_report(request):
    if request.session.get('role') != 'admin':
        return redirect('admin_login')
    
    force_refresh = request.GET.get('refresh') == '1'
    
    cached_data = report_proxy.get_popular_pizzas_cache(limit=10, force_refresh=force_refresh)
    
    if cached_data is not None and not force_refresh:
        return render(request, 'reports/popular_pizzas.html', {'popular_pizzas': cached_data, 'from_cache': True})
    
    from django.db.models import Count
    
    popular_pizzas = CustomPizza.objects.filter(
        client__isnull=False
    ).values(
        'composition'
    ).annotate(
        order_count=Count('custom_pizza_id')
    ).order_by('-order_count')[:10]
    
    popular_list = []
    for pizza in popular_pizzas:
        composition = pizza.get('composition', {})
        popular_list.append({
            'name': f"Кастомная пицца",
            'category': composition.get('factory_style', 'Классическая'),
            'base_price': 0,
            'order_count': pizza.get('order_count', 0),
            'total_revenue': 0,
            'composition': composition
        })
    
    report_proxy.set_popular_pizzas_cache(10, popular_list)
    
    context = {
        'popular_pizzas': popular_list,
        'from_cache': False,
    }
    return render(request, 'reports/popular_pizzas.html', context)