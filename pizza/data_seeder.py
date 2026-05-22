from abc import ABC, abstractmethod

class BaseDataSeeder(ABC):
    
    def run(self):
        self.create_ingredients()
        self.create_pizzas()
        self.create_clients()
        self.create_couriers()
        self.create_orders()
        print("Генерация данных завершена!")
    
    def clear_data(self):
        from .models import Pizza, Ingredient, Client, Courier, Order
        print("Очистка старых данных...")
        Pizza.objects.all().delete()
        Ingredient.objects.all().delete()
        Client.objects.all().delete()
        Courier.objects.all().delete()
        Order.objects.all().delete()
    
    @abstractmethod
    def create_ingredients(self):
        pass
    
    @abstractmethod
    def create_pizzas(self):
        pass
    
    @abstractmethod
    def create_clients(self):
        pass
    
    @abstractmethod
    def create_couriers(self):
        pass
    
    @abstractmethod
    def create_orders(self):
        pass


class DemoDataSeeder(BaseDataSeeder):
    
    def create_ingredients(self):
        from .models import Ingredient
        print("Создание ингредиентов...")
        ingredients = [
            ("Томатный соус", 50, "sauce"),
            ("Сливочный соус", 70, "sauce"),
            ("Моцарелла", 80, "cheese"),
            ("Пармезан", 100, "cheese"),
            ("Пепперони", 120, "topping"),
            ("Ветчина", 110, "topping"),
            ("Грибы", 90, "topping"),
            ("Ананас", 80, "topping"),
        ]
        for name, price, cat in ingredients:
            Ingredient.objects.get_or_create(
                ingredient_name=name,
                defaults={'price': price, 'category': cat}
            )
    
    def create_pizzas(self):
        from .models import Pizza
        print("Создание пицц...")
        pizzas = [
            ("Маргарита", "Томатный соус, моцарелла", 499, "Классическая"),
            ("Пепперони", "Пикантная пепперони, моцарелла", 599, "Мясная"),
            ("Четыре сыра", "Смесь итальянских сыров", 649, "Сырная"),
        ]
        for name, desc, price, cat in pizzas:
            Pizza.objects.get_or_create(
                name=name,
                defaults={'description': desc, 'base_price': price, 'category': cat}
            )
    
    def create_clients(self):
        from .models import Client
        print("Создание клиентов...")
        for i in range(1, 4):
            Client.objects.get_or_create(
                email=f"client{i}@test.com",
                defaults={'name': f"Клиент {i}"}
            )
    
    def create_couriers(self):
        from .models import Courier
        print("Создание курьеров...")
        couriers = [
            ("Иван Иванов", "+79161234567", "Свободен"),
            ("Петр Петров", "+79168765432", "Свободен"),
        ]
        for name, phone, status in couriers:
            Courier.objects.get_or_create(
                name=name,
                defaults={'phone': phone, 'status': status}
            )
    
    def create_orders(self):
        from .models import Client, Pizza, Order
        print("Создание тестовых заказов...")
        client = Client.objects.first()
        if client and not Order.objects.filter(client=client).exists():
            Order.objects.create(
                client=client,
                amount=499,
                delivery_type='pickup',
                address='Самовывоз'
            )
            print("  Создан тестовый заказ")