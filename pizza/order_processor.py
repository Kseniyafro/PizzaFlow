# pizza/order_processor.py

from abc import ABC, abstractmethod
from .models import Order, Client, OrderStatusHistory
from .singletons import EventBus

class OrderProcessor(ABC):
    
    def process(self, request, cart_data, total_amount):
        client = self._get_client(request)
        loyalty_discount = self._calculate_loyalty_discount(client)
        delivery_fee = self.calculate_delivery_fee(total_amount)
        final_total = self._calculate_final_total(total_amount, loyalty_discount, delivery_fee)
        order = self._create_order(request, client, delivery_fee, final_total)
        self._assign_courier(order)
        self._clear_cart(request)
        self._notify(order, client)
        
        return order

    @abstractmethod
    def calculate_delivery_fee(self, total_amount):
        pass
    
    @abstractmethod
    def _assign_courier(self, order):
        pass
    
    def _get_client(self, request):
        from django.shortcuts import redirect
        if 'user_id' not in request.session:
            return None
        return Client.objects.get(client_id=request.session['user_id'])
    
    def _calculate_loyalty_discount(self, client):
        from django.utils import timezone
        if not client or not client.registration_date:
            return 0.0
        
        years = (timezone.now().date() - client.registration_date.date()).days // 365
        if years >= 2:
            return 0.05
        elif years >= 1:
            return 0.03
        return 0.0
    
    def _calculate_final_total(self, total_amount, loyalty_discount, delivery_fee):
        final_total = (total_amount * (1 - loyalty_discount)) + delivery_fee
        return round(final_total, 2)
    
    def _create_order(self, request, client, delivery_fee, final_total):
        delivery_type = request.POST.get('delivery_type')
        address = request.POST.get('address', '')
        
        if delivery_type == 'pickup':
            address = 'Самовывоз'
        
        order = Order.objects.create(
            client=client,
            delivery_type=delivery_type,
            amount=final_total,
            address=address
        )

        order._processor_type = self.__class__.__name__
        
        return order
    
    def _clear_cart(self, request):
        request.session['cart'] = {}
    
    def _notify(self, order, client):
        event_bus = EventBus()
        event_bus.publish('order_created', {
            'order_id': order.order_id, 
            'client_id': client.client_id
        })


class DeliveryOrderProcessor(OrderProcessor):
    
    def calculate_delivery_fee(self, total_amount):
        if total_amount >= 500:
            return 0
        return 200
    
    def _assign_courier(self, order):
        from .models import Courier
        
        free_courier = Courier.objects.filter(status='Свободен').first()
        if free_courier:
            order.courier = free_courier
            free_courier.status = 'В пути'
            free_courier.save()
            order.save()


class PickupOrderProcessor(OrderProcessor):
    
    def calculate_delivery_fee(self, total_amount):
        return 0  
    
    def _assign_courier(self, order):
        pass  
