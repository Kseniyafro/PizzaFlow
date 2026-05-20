from django.core.management.base import BaseCommand
from pizza.data_seeder import DemoDataSeeder

class Command(BaseCommand):
    help = 'Генерирует тестовые данные для пиццерии'
    
    def handle(self, *args, **options):
        self.stdout.write("Запуск генерации данных...")
        seeder = DemoDataSeeder()
        seeder.run()
        self.stdout.write(self.style.SUCCESS("Данные успешно сгенерированы!"))