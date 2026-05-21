"""
Паттерн «Команда» (Command) для системы PizzaFlow.

Идея: каждое значимое действие над заказом (создать, сменить статус,
отменить, назначить курьера) оборачивается в отдельный объект-команду.
Вызывающий код (views.py) не знает, как именно выполняется команда, —
он просто вызывает execute().  Это позволяет:
  • легко добавлять новые действия, не меняя views;
  • хранить историю команд и при необходимости откатывать их (undo);
  • ставить команды в очередь или логировать.

Участники паттерна:
  Command        — абстрактный интерфейс (execute / undo)
  ConcreteCommand — конкретные команды (PlaceOrder, UpdateStatus, ...)
  Receiver       — объекты модели (Order, Courier, Client), которые
                   выполняют реальную бизнес-логику
  Invoker        — OrderCommandInvoker, хранит историю и запускает команды
"""

from abc import ABC, abstractmethod
from typing import Optional

from .models import Order, OrderStatusHistory, Courier, Client, CartItem
from .observers import OrderSubject, KitchenObserver, CustomerObserver, AdminObserver
from .singletons import EventBus
from .loyalty_adapter import LoyaltySystemAdapter
from .external_loyalty_service import LegacyLoyaltySystem


# Базовый интерфейс команды

class Command(ABC):
    """Абстрактная команда: обязательно execute(), опционально undo()."""

    @abstractmethod
    def execute(self) -> dict:
        """
        Выполнить команду.
        Возвращает словарь с результатом, например {'success': True, ...}
        """

    def undo(self) -> dict:
        """Откатить команду (реализуется при необходимости)."""
        return {'success': False, 'message': 'Откат не поддерживается для этой команды'}


# Общие зависимости (Observers / EventBus)

def _make_order_subject() -> OrderSubject:
    subject = OrderSubject()
    subject.attach(KitchenObserver())
    subject.attach(CustomerObserver())
    subject.attach(AdminObserver())
    return subject


# Конкретные команды

class PlaceOrderCommand(Command):
    """
    Команда: создать новый заказ.
    Receiver — Order (модель).
    """

    DELIVERY_STATUSES = ['Принят', 'Готовится', 'В печи', 'Передан курьеру', 'Доставлен']
    PICKUP_STATUSES   = ['Принят', 'Готовится', 'В печи', 'Доставлен']

    def __init__(self, client_id: int, delivery_type: str,
                 address: str, comment: str, amount: float):
        self.client_id     = client_id
        self.delivery_type = delivery_type
        self.address       = address
        self.comment       = comment
        self.amount        = amount
        self._created_order: Optional[Order] = None

    def execute(self) -> dict:
        client = Client.objects.get(client_id=self.client_id)
        order = Order.objects.create(
            client=client,
            delivery_type=self.delivery_type,
            address=self.address,
            comment=self.comment,
            amount=self.amount,
            status='Принят',
        )
        self._created_order = order

        OrderStatusHistory.objects.create(order=order, status='Принят')

        subject = _make_order_subject()
        subject.notify(order)
        EventBus().publish('order_placed', {'order_id': order.order_id})

        # Начисляем бонусы
        loyalty_adapter = LoyaltySystemAdapter(LegacyLoyaltySystem())
        loyalty_adapter.give_bonus(self.client_id, 10)

        return {
            'success': True,
            'order_id': order.order_id,
            'message': f'Заказ #{order.order_id} успешно создан',
        }

    def undo(self) -> dict:
        """Отмена: удалить только что созданный заказ (если ещё «Принят»)."""
        if self._created_order and self._created_order.status == 'Принят':
            order_id = self._created_order.order_id
            self._created_order.delete()
            return {'success': True, 'message': f'Заказ #{order_id} удалён (откат)'}
        return {'success': False, 'message': 'Нельзя откатить: заказ уже в обработке'}


class UpdateOrderStatusCommand(Command):
    """
    Команда: перевести заказ на следующий статус по цепочке.
    Receiver — Order.
    """

    DELIVERY_STATUSES = ['Принят', 'Готовится', 'В печи', 'Передан курьеру', 'Доставлен']
    PICKUP_STATUSES   = ['Принят', 'Готовится', 'В печи', 'Доставлен']

    def __init__(self, order_id: int):
        self.order_id        = order_id
        self._previous_status: Optional[str] = None

    def execute(self) -> dict:
        order = Order.objects.get(order_id=self.order_id)
        statuses = (self.DELIVERY_STATUSES
                    if order.delivery_type == 'delivery'
                    else self.PICKUP_STATUSES)

        try:
            idx = statuses.index(order.status)
        except ValueError:
            return {'success': False, 'is_finished': True, 'status': order.status}

        if idx >= len(statuses) - 1:
            return {'success': False, 'is_finished': True, 'status': order.status,
                    'message': 'Заказ уже в финальном статусе'}

        self._previous_status = order.status
        new_status = statuses[idx + 1]
        order.status = new_status
        order.save()

        OrderStatusHistory.objects.create(order=order, status=new_status)

        # Синхронизация курьера
        if order.delivery_type == 'delivery' and order.courier:
            courier = order.courier
            if new_status == 'Передан курьеру':
                courier.status = 'В пути'
                courier.save()
            elif new_status == 'Доставлен':
                courier.status = 'Свободен'
                courier.save()

        subject = _make_order_subject()
        subject.notify(order)
        EventBus().publish('order_status_changed',
                           {'order_id': order.order_id, 'status': new_status})

        return {
            'success': True,
            'is_finished': False,
            'status': new_status,
            'order_id': order.order_id,
        }

    def undo(self) -> dict:
        """Откатить статус на предыдущий."""
        if self._previous_status is None:
            return {'success': False, 'message': 'Нечего откатывать'}
        order = Order.objects.get(order_id=self.order_id)
        order.status = self._previous_status
        order.save()
        OrderStatusHistory.objects.create(order=order, status=self._previous_status)
        return {
            'success': True,
            'status': self._previous_status,
            'message': f'Статус заказа #{self.order_id} откатан до «{self._previous_status}»',
        }


class CancelOrderCommand(Command):
    """
    Команда: отменить заказ клиентом.
    Receiver — Order, Courier.
    """

    ALLOWED_STATUSES = ['Принят', 'Готовится', 'В печи']

    def __init__(self, order_id: int, client_id: int):
        self.order_id        = order_id
        self.client_id       = client_id
        self._previous_status: Optional[str] = None
        self._courier_id: Optional[int] = None

    def execute(self) -> dict:
        try:
            order = Order.objects.get(order_id=self.order_id, client_id=self.client_id)
        except Order.DoesNotExist:
            return {'success': False, 'message': 'Заказ не найден'}

        if order.status not in self.ALLOWED_STATUSES:
            return {'success': False, 'message': 'Заказ нельзя отменить в текущем статусе'}

        self._previous_status = order.status

        if order.courier:
            self._courier_id = order.courier.courier_id
            order.courier.status = 'Свободен'
            order.courier.save()

        order.status = 'Отменен'
        order.save()

        OrderStatusHistory.objects.create(order=order, status='Отменен')

        subject = _make_order_subject()
        subject.notify(order)
        EventBus().publish('order_cancelled', {'order_id': order.order_id})

        return {
            'success': True,
            'message': f'Заказ #{self.order_id} отменён',
        }

    def undo(self) -> dict:
        """Восстановить отменённый заказ."""
        if self._previous_status is None:
            return {'success': False, 'message': 'Нечего откатывать'}
        try:
            order = Order.objects.get(order_id=self.order_id)
        except Order.DoesNotExist:
            return {'success': False, 'message': 'Заказ не найден'}

        order.status = self._previous_status
        order.save()
        OrderStatusHistory.objects.create(order=order, status=self._previous_status)

        if self._courier_id:
            try:
                courier = Courier.objects.get(courier_id=self._courier_id)
                courier.status = 'В пути'
                courier.save()
                order.courier = courier
                order.save()
            except Courier.DoesNotExist:
                pass

        return {
            'success': True,
            'status': self._previous_status,
            'message': f'Отмена заказа #{self.order_id} откатана',
        }


class AssignCourierCommand(Command):
    """
    Команда: назначить курьера на заказ.
    Receiver — Order, Courier.
    """

    def __init__(self, order_id: int, courier_id: int):
        self.order_id   = order_id
        self.courier_id = courier_id
        self._previous_courier_id: Optional[int] = None

    def execute(self) -> dict:
        try:
            order   = Order.objects.get(order_id=self.order_id)
            courier = Courier.objects.get(courier_id=self.courier_id)
        except (Order.DoesNotExist, Courier.DoesNotExist):
            return {'success': False, 'message': 'Заказ или курьер не найден'}

        if courier.status != 'Свободен':
            return {'success': False, 'message': 'Курьер недоступен'}
        if order.status != 'В печи' or order.delivery_type != 'delivery':
            return {'success': False, 'message': 'Заказ не готов к назначению курьера'}

        if order.courier:
            self._previous_courier_id = order.courier.courier_id

        order.courier = courier
        order.status  = 'Передан курьеру'
        order.save()

        courier.status = 'В пути'
        courier.save()

        OrderStatusHistory.objects.create(order=order, status='Передан курьеру')

        subject = _make_order_subject()
        subject.notify(order)
        EventBus().publish('courier_assigned',
                           {'order_id': order.order_id, 'courier_id': courier.courier_id})

        return {
            'success': True,
            'message': f'Курьер {courier.name} назначен на заказ #{self.order_id}',
        }

    def undo(self) -> dict:
        try:
            order   = Order.objects.get(order_id=self.order_id)
            courier = Courier.objects.get(courier_id=self.courier_id)
        except (Order.DoesNotExist, Courier.DoesNotExist):
            return {'success': False, 'message': 'Не найдено'}

        order.status  = 'В печи'
        order.courier = None
        if self._previous_courier_id:
            try:
                order.courier = Courier.objects.get(courier_id=self._previous_courier_id)
            except Courier.DoesNotExist:
                pass
        order.save()

        courier.status = 'Свободен'
        courier.save()

        OrderStatusHistory.objects.create(order=order, status='В печи')

        return {
            'success': True,
            'message': f'Назначение курьера на заказ #{self.order_id} откатано',
        }


# Invoker — менеджер команд

class OrderCommandInvoker:
    """
    Вызывающий (Invoker).
    Хранит историю выполненных команд и предоставляет
    метод undo_last() для отката последней операции.

    Используется как синглтон уровня запроса — создаётся один раз
    и передаётся во view-функции.
    """

    def __init__(self):
        self._history: list[Command] = []

    def run(self, command: Command) -> dict:
        """Выполнить команду и сохранить её в историю."""
        result = command.execute()
        if result.get('success'):
            self._history.append(command)
        return result

    def undo_last(self) -> dict:
        """Откатить последнюю успешную команду."""
        if not self._history:
            return {'success': False, 'message': 'История команд пуста'}
        command = self._history.pop()
        return command.undo()

    @property
    def history_size(self) -> int:
        return len(self._history)