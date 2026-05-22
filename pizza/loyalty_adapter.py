from abc import ABC, abstractmethod
from .models import Client 
from .external_loyalty_service import LegacyLoyaltySystem, ExternalClientData

class ILoyaltyService(ABC):
    @abstractmethod
    def give_bonus(self, client_id: int, bonus_points: int):
        pass
    
    @abstractmethod
    def spend_bonus(self, client_id: int, bonus_points: int):
        pass


class LoyaltySystemAdapter(ILoyaltyService):
    def __init__(self, legacy_system: LegacyLoyaltySystem):
        self._legacy_system = legacy_system
    
    def _ensure_client_exists(self, client: Client):
        external_id = f"ext_{client.email}"
        existing_client = self._legacy_system.get_client_by_external_id(external_id)
        
        if existing_client is None:
            new_external_client = ExternalClientData(external_id, client.name)
            self._legacy_system._clients_db[external_id] = new_external_client
            return True
        return True
    
    def give_bonus(self, client_id: int, bonus_points: int):
        try:
            our_client = Client.objects.get(client_id=client_id)
        except Client.DoesNotExist:
            return False
        
        self._ensure_client_exists(our_client)
        external_id = f"ext_{our_client.email}"
        success = self._legacy_system.add_bonus_points(external_id, bonus_points)
        
        if success:
            our_client.loyalty_points += bonus_points
            our_client.save()
        return success

    def spend_bonus(self, client_id: int, bonus_points: int):
        try:
            our_client = Client.objects.get(client_id=client_id)
        except Client.DoesNotExist:
            return False

        if our_client.loyalty_points < bonus_points:
            return False

        self._ensure_client_exists(our_client)
        external_id = f"ext_{our_client.email}"
        success = self._legacy_system.spend_bonus_points(external_id, bonus_points)
        
        if success:
            our_client.loyalty_points -= bonus_points
            our_client.save()
            return True
        return False