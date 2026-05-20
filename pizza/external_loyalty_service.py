class ExternalClientData:
    def __init__(self, external_id: str, username: str):
        self.external_id = external_id
        self.username = username

class LegacyLoyaltySystem:
    def __init__(self):
        self._clients_db = {
            "ext_1": ExternalClientData("ext_1", "john_doe"),
            "ext_2": ExternalClientData("ext_2", "jane_smith"),
            "ext_3": ExternalClientData("ext_3", "alex_wong"),
        }

    def get_client_by_external_id(self, external_id: str):
        print(f"DEBUG: [LegacySystem] Поиск клиента по external_id '{external_id}'")
        return self._clients_db.get(external_id)

    def add_bonus_points(self, external_client_id: str, points: int):
        client = self.get_client_by_external_id(external_client_id)
        if client:
            print(f"DEBUG: [LegacySystem] Начислено {points} бонусов клиенту '{client.username}'.")
            return True
        else:
            print(f"DEBUG: [LegacySystem] Ошибка! Клиент '{external_client_id}' не найден.")
            return False