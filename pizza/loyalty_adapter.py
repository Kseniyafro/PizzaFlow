from abc import ABC, abstractmethod
from .models import Client 
from .external_loyalty_service import LegacyLoyaltySystem, ExternalClientData

class ILoyaltyService(ABC):
    @abstractmethod
    def give_bonus(self, client_id: int, bonus_points: int):
        pass

class LoyaltySystemAdapter(ILoyaltyService):
    
    def __init__(self, legacy_system: LegacyLoyaltySystem):
        self._legacy_system = legacy_system
    
    def _ensure_client_exists(self, client: Client):
        external_id = f"ext_{client.email}"
        existing_client = self._legacy_system.get_client_by_external_id(external_id)
        
        if existing_client is None:
            print(f"DEBUG: [Adapter] Клиент '{client.name}' не найден во внешней системе. Создаем...")
            new_external_client = ExternalClientData(external_id, client.name)
            self._legacy_system._clients_db[external_id] = new_external_client
            print(f"DEBUG: [Adapter] Клиент '{client.name}' успешно создан во внешней системе!")
            return True
        else:
            print(f"DEBUG: [Adapter] Клиент '{client.name}' уже существует во внешней системе")
            return True
    
    def give_bonus(self, client_id: int, bonus_points: int):
        try:
            our_client = Client.objects.get(client_id=client_id)
        except Client.DoesNotExist:
            print(f"ERROR: Адаптер не нашел клиента с id={client_id}")
            return False
        
        self._ensure_client_exists(our_client)
        
        external_id = f"ext_{our_client.email}"
        
        print(f"DEBUG: [Adapter] Вызываю старую систему для клиента '{our_client.name}'")
        success = self._legacy_system.add_bonus_points(external_id, bonus_points)
        
        if success:
            our_client.loyalty_points += bonus_points
            our_client.save()
            print(f"DEBUG: [Adapter] Теперь у {our_client.name} {our_client.loyalty_points} баллов")
            print(f"DEBUG: [Adapter] Бонусы успешно начислены!")
        
        return success