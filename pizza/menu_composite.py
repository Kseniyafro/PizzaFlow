from abc import ABC, abstractmethod
from typing import List, Iterator
from .models import Pizza

class MenuComponent(ABC):
    @abstractmethod
    def get_name(self) -> str:
        pass
    
    @abstractmethod
    def get_price(self) -> float:
        pass
    
    @abstractmethod
    def get_description(self) -> str:
        pass
    
    @abstractmethod
    def display(self, indent: int = 0):
        pass
    
    @abstractmethod
    def create_iterator(self) -> Iterator:
        pass

    @abstractmethod
    def get_count(self) -> int:
        pass

class PizzaLeaf(MenuComponent):
    def __init__(self, pizza: Pizza):
        self._pizza = pizza
    
    def get_name(self) -> str:
        return self._pizza.name
    
    def get_price(self) -> float:
        return self._pizza.base_price
    
    def get_description(self) -> str:
        return self._pizza.description or "Вкусная пицца"
    
    def display(self, indent: int = 0):
        print("  " * indent + f"{self.get_name()} - {self.get_price()} ₽")
    
    def create_iterator(self) -> Iterator:
        return PizzaIterator([self])
    
    def get_count(self) -> int:
        return 1

class PizzaCategory(MenuComponent):
    def __init__(self, name: str, description: str = ""):
        self._name = name
        self._description = description
        self._children: List[MenuComponent] = []  
    
    def add(self, component: MenuComponent):
        self._children.append(component)
    
    def remove(self, component: MenuComponent):
        self._children.remove(component)
    
    def get_child(self, index: int) -> MenuComponent:
        return self._children[index]
    
    def get_name(self) -> str:
        return self._name
    
    def get_price(self) -> float:
        total = 0
        for child in self._children:
            total += child.get_price()
        return total
    
    def get_description(self) -> str:
        return self._description
    
    def display(self, indent: int = 0):
        print("  " * indent + f"{self.get_name()} (всего: {self.get_price()} ₽)")
        for child in self._children:
            child.display(indent + 1)
    
    def create_iterator(self) -> Iterator:
        all_pizzas = self._collect_all_pizzas()
        return PizzaIterator(all_pizzas)
    
    def _collect_all_pizzas(self) -> List[PizzaLeaf]:
        result = []
        for child in self._children:
            if isinstance(child, PizzaLeaf):
                result.append(child)
            elif isinstance(child, PizzaCategory):
                result.extend(child._collect_all_pizzas())
        return result
    
    def get_count(self) -> int:
        total = 0
        for child in self._children:
            total += child.get_count()
        return total

class PizzaIterator(Iterator):
    def __init__(self, pizzas: List[PizzaLeaf]):
        self._pizzas = pizzas
        self._index = 0
    
    def __iter__(self):
        return self
    
    def __next__(self) -> PizzaLeaf:
        if self._index < len(self._pizzas):
            result = self._pizzas[self._index]
            self._index += 1
            return result
        raise StopIteration
    
    def has_next(self) -> bool:
        return self._index < len(self._pizzas)
    
    def reset(self):
        self._index = 0

class MenuBuilder:
    @staticmethod
    def build_from_database():
        root_menu = PizzaCategory("Все пиццы", "Полный ассортимент пиццерии")
        from .models import Pizza
        categories = Pizza.objects.values_list('category', flat=True).distinct()
        category_map = {}
        
        for category_name in categories:
            if category_name:
                category_node = PizzaCategory(category_name, f"Все пиццы категории {category_name}")
                category_map[category_name] = category_node
                root_menu.add(category_node)

        all_pizzas = Pizza.objects.filter(is_available=True)
        
        for pizza in all_pizzas:
            pizza_leaf = PizzaLeaf(pizza)
            if pizza.category and pizza.category in category_map:
                category_map[pizza.category].add(pizza_leaf)
            else:
                root_menu.add(pizza_leaf)

        return root_menu