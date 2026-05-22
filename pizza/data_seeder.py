from abc import ABC, abstractmethod
import random

class BaseDataSeeder(ABC):
    
    def run(self):
        self.create_ingredients()
        self.create_pizzas()
        self.create_clients()
        self.create_couriers()
        self.create_orders()
        print("Генерация данных завершена!")
    
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
        """Генерирует 10 случайных ингредиентов"""
        from .models import Ingredient
        
        print("Генерация ингредиентов...")
        
        categories = ['sauce', 'cheese', 'topping', 'dough']
        sauces = ['Томатный', 'Сливочный', 'Барбекю', 'Песто']
        cheeses = ['Моцарелла', 'Пармезан', 'Чеддер', 'Дор блю']
        toppings = ['Пепперони', 'Ветчина', 'Грибы', 'Ананас', 'Оливки', 'Бекон', 'Курица', 'Лук']
        
        for i in range(10):
            category = random.choice(categories)
            
            if category == 'sauce':
                name = random.choice(sauces) + " соус"
                price = random.randint(40, 90)
            elif category == 'cheese':
                name = random.choice(cheeses)
                price = random.randint(70, 130)
            else:
                name = random.choice(toppings)
                price = random.randint(50, 150)
            
            Ingredient.objects.get_or_create(
                ingredient_name=name,
                defaults={
                    'price': price,
                    'category': category,
                    'is_available': True
                }
            )
            print(f"  Создан ингредиент: {name} ({price} руб.)")
    
    def create_pizzas(self):
        """Генерирует 5 случайных пицц"""
        from .models import Pizza
        
        print("Генерация пицц...")
        
        pizza_names = ['Маргарита', 'Пепперони', 'Гавайская', 'Мясная', 'Сырная', 
                       'Морская', 'Вегетарианская', 'Диабло', 'Карбонара', 'Четыре сезона']
        categories = ['Классическая', 'Мясная', 'Острая', 'Вегетарианская', 'Сырная']
        
        for i in range(5):
            name = random.choice(pizza_names) + f" #{i+1}"
            description = f"Авторская пицца с {random.choice(['сыром', 'мясом', 'овощами'])}"
            price = random.randint(400, 800)
            category = random.choice(categories)
            
            Pizza.objects.get_or_create(
                name=name,
                defaults={
                    'description': description,
                    'base_price': price,
                    'category': category,
                    'is_available': True
                }
            )
            print(f"  Создана пицца: {name} ({price} руб.)")
    
    def create_clients(self):
        """Генерирует 5 случайных клиентов"""
        from .models import Client
        
        print("Генерация клиентов...")
        
        first_names = ['Иван', 'Петр', 'Сергей', 'Алексей', 'Дмитрий', 
                       'Елена', 'Мария', 'Анна', 'Ольга', 'Татьяна']
        last_names = ['Иванов', 'Петров', 'Сидоров', 'Кузнецов', 'Смирнов']
        
        for i in range(5):
            name = f"{random.choice(first_names)} {random.choice(last_names)}"
            email = f"user{random.randint(100, 999)}@test.com"
            
            Client.objects.get_or_create(
                email=email,
                defaults={
                    'name': name,
                    'is_active': True
                }
            )
            print(f"  Создан клиент: {name} ({email})")
    
    def create_couriers(self):
        """Генерирует 3 случайных курьеров"""
        from .models import Courier
        
        print("Генерация курьеров...")
        
        first_names = ['Антон', 'Максим', 'Денис', 'Артем', 'Владимир']
        last_names = ['Соколов', 'Морозов', 'Волков', 'Зайцев', 'Соловьев']
        statuses = ['Свободен', 'В пути']
        
        for i in range(3):
            name = f"{random.choice(first_names)} {random.choice(last_names)}"
            phone = f"+7{random.randint(900, 999)}{random.randint(1000000, 9999999)}"
            status = random.choice(statuses)
            
            Courier.objects.get_or_create(
                name=name,
                defaults={
                    'phone': phone,
                    'status': status
                }
            )
            print(f"  Создан курьер: {name} ({status})")
    
    def create_orders(self):
        """Генерирует 3 случайных заказа"""
        from .models import Client, Pizza, Order
        
        print("Генерация заказов...")
        
        clients = list(Client.objects.all())
        pizzas = list(Pizza.objects.all())
        
        delivery_types = ['delivery', 'pickup']
        addresses = ['ул. Пушкина, д.10', 'пр. Ленина, д.25', 'ул. Советская, д.5']
        statuses = ['Принят', 'Готовится', 'В печи', 'Доставлен']
        
        for i in range(3):
            if not clients or not pizzas:
                print("  Нет клиентов или пицц для создания заказа")
                return
            
            client = random.choice(clients)
            pizza = random.choice(pizzas)
            delivery_type = random.choice(delivery_types)
            
            if delivery_type == 'delivery':
                address = random.choice(addresses)
            else:
                address = 'Самовывоз'
            
            amount = pizza.base_price + random.randint(0, 200)
            status = random.choice(statuses)
            
            Order.objects.create(
                client=client,
                amount=amount,
                delivery_type=delivery_type,
                address=address,
                status=status
            )
            print(f"  Создан заказ #{i+1}: {client.name} - {amount} руб. ({status})")
            
