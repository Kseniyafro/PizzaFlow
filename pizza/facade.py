# facade.py
from django.shortcuts import redirect
from django.contrib import messages
from .models import Order, Client
from .strategies import OrderContext, StandardPricing, DiscountPricing, StandardDelivery, ExpressDelivery, PickupStrategy
from .loyalty_adapter import LoyaltySystemAdapter
from .external_loyalty_service import LegacyLoyaltySystem
from .observers import order_subject
from .singletons import EventBus, ConfigManager
from .proxy import AdminAccessProxy
from .commands import OrderCommandInvoker

class OrderFacade:
    """
    Фасад для создания заказа — скрывает всю сложность:
    - Выбор стратегии ценообразования
    - Расчет скидок и доставки
    - Начисление бонусов через адаптер
    - Уведомление наблюдателей
    - Публикация событий
    - Очистка кэша админ-прокси
    """
    
    def __init__(self):
        self._legacy_system = LegacyLoyaltySystem()
        self._loyalty_adapter = LoyaltySystemAdapter(self._legacy_system)
        self._event_bus = EventBus()
        self._config = ConfigManager()
        self._admin_proxy = AdminAccessProxy()
        self._order_invoker = OrderCommandInvoker()
    
    def create_order(self, request, cart, total, delivery_type, address="", comment=""):

        if 'user_id' not in request.session:
            return False, None, "Необходимо авторизоваться"
        
        if not cart or total == 0:
            return False, None, "Корзина пуста"
        
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
            food_total = pricing_strategy.calculate(total, 0, 1)
            discount_applied = 10
        else:
            pricing_strategy = StandardPricing()
            food_total = pricing_strategy.calculate(total, 0, 1)
            discount_applied = 0
        
        if delivery_type == 'pickup':
            delivery_fee = 0
        else:
            if food_total >= self._config.get('free_delivery_threshold', 500):
                delivery_fee = 0
            else:
                delivery_fee = self._config.get('delivery_base_fee', 200)
        
        final_total = food_total + delivery_fee
        order.amount = final_total
        order.comment = comment
        order.save()
        
        bonus_to_give = self._config.get('bonus_points_per_order', 10)
        success = self._loyalty_adapter.give_bonus(request.session['user_id'], bonus_to_give)
        
        if success:
            client = Client.objects.get(client_id=request.session['user_id'])
            request.session['loyalty_points'] = client.loyalty_points
        
        order_subject.notify(order)
        
        self._event_bus.publish('order_status_changed', {
            'order_id': order.order_id, 
            'status': order.status
        })
        
        self._admin_proxy.set_cached_orders(None)
        self._admin_proxy.set_cached_stats(None)
        
        from .commands import CreateOrderCommand
        create_command = CreateOrderCommand(order.order_id)
        self._order_invoker.add_command(create_command)
        
        return True, order, f"Заказ #{order.order_id} успешно создан"
    
    def calculate_order_preview(self, cart, total, delivery_type):

        total_quantity = sum(item['quantity'] for item in cart.values())
        
        if total_quantity >= 3:
            discount_percent = self._config.get('bulk_discount_percent', 10)
            pricing_strategy = DiscountPricing(discount_percent)
            food_total_with_discount = pricing_strategy.calculate(total, 0, 1)
        else:
            discount_percent = 0
            food_total_with_discount = total
        
        discount_amount = total - food_total_with_discount
        
        if delivery_type == 'pickup':
            delivery_fee = 0
        else:
            threshold = self._config.get('free_delivery_threshold', 500)
            base_fee = self._config.get('delivery_base_fee', 200)
            
            if food_total_with_discount >= threshold:
                delivery_fee = 0
                free_delivery_need = 0
            else:
                delivery_fee = base_fee
                free_delivery_need = threshold - food_total_with_discount
        
        grand_total = food_total_with_discount + delivery_fee
        
        return {
            'total': total,
            'discount_percent': discount_percent,
            'discount_amount': discount_amount,
            'food_total_with_discount': food_total_with_discount,
            'delivery_fee': delivery_fee,
            'grand_total': grand_total,
            'free_delivery_threshold': self._config.get('free_delivery_threshold', 500),
            'free_delivery_need': free_delivery_need if delivery_type != 'pickup' else 0,
        }


class OrderFacadeSingleton:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = OrderFacade()
        return cls._instance


order_facade = OrderFacadeSingleton()