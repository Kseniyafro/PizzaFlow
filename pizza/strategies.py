from abc import ABC, abstractmethod

class PricingStrategy(ABC):
    @abstractmethod
    def calculate(self, base_price, toppings_price, quantity):
        pass


class StandardPricing(PricingStrategy):
    def calculate(self, base_price, toppings_price, quantity):
        return (base_price + toppings_price) * quantity


class DiscountPricing(PricingStrategy):
    def __init__(self, discount_percent=10):
        self.discount_percent = discount_percent
    
    def calculate(self, base_price, toppings_price, quantity):
        total = (base_price + toppings_price) * quantity
        return total * (1 - self.discount_percent / 100)


class BulkPricing(PricingStrategy):
    def calculate(self, base_price, toppings_price, quantity):
        total = (base_price + toppings_price) * quantity
        if quantity >= 5:
            return total * 0.75
        elif quantity >= 3:
            return total * 0.85
        return total


class LoyaltyPricing(PricingStrategy):
    def __init__(self, loyalty_points):
        self.loyalty_points = loyalty_points
    
    def calculate(self, base_price, toppings_price, quantity):
        total = (base_price + toppings_price) * quantity
        max_discount = min(self.loyalty_points, total * 0.2)
        return total - max_discount


class DeliveryStrategy(ABC):
    @abstractmethod
    def calculate_cost(self, distance_km, total_amount):
        pass


class StandardDelivery(DeliveryStrategy):
    def calculate_cost(self, distance_km, total_amount):
        if total_amount >= 500:
            return 0
        return 100 + int(distance_km * 20)


class ExpressDelivery(DeliveryStrategy):
    def calculate_cost(self, distance_km, total_amount):
        if total_amount >= 800:
            return 0
        return 200 + int(distance_km * 30)


class PickupStrategy(DeliveryStrategy):
    def calculate_cost(self, distance_km, total_amount):
        return 0


# ============ Контекст для заказа ============

class OrderContext:
    def __init__(self, pricing_strategy=None, delivery_strategy=None):
        self._pricing_strategy = pricing_strategy or StandardPricing()
        self._delivery_strategy = delivery_strategy or StandardDelivery()
    
    def set_pricing_strategy(self, strategy):
        self._pricing_strategy = strategy
    
    def set_delivery_strategy(self, strategy):
        self._delivery_strategy = strategy
    
    def calculate_total(self, base_price, toppings_price, quantity, distance_km, total_amount):
        food_total = self._pricing_strategy.calculate(base_price, toppings_price, quantity)
        delivery_cost = self._delivery_strategy.calculate_cost(distance_km, total_amount)
        return food_total + delivery_cost
