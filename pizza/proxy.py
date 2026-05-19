from functools import wraps
from django.core.cache import cache
from django.shortcuts import redirect
from django.http import JsonResponse
from .models import Admin
from .singletons import CacheManager


class AdminAccessProxy:
    _instance = None
    _cache_manager = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cache_manager = CacheManager()
        return cls._instance
    
    def check_access(self, request, required_permission='full'):
        if request.session.get('role') != 'admin':
            return False
        
        admin_id = request.session.get('user_id')
        if not admin_id:
            return False
        
        cache_key = f'admin_permissions_{admin_id}'
        permissions = self._cache_manager.get(cache_key)
        
        if permissions is None:
            try:
                admin = Admin.objects.get(admin_id=admin_id)
                permissions = admin.permissions
                self._cache_manager.set(cache_key, permissions, timeout=300)
            except Admin.DoesNotExist:
                return False
        
        if required_permission == 'full' and permissions != 'full':
            return False
        
        return True
    
    def get_cached_orders(self, force_refresh=False):
        cache_key = 'admin_orders_list'
        
        if force_refresh:
            cache.delete(cache_key)
            return None
        
        return self._cache_manager.get(cache_key)
    
    def set_cached_orders(self, orders_data):
        cache_key = 'admin_orders_list'
        self._cache_manager.set(cache_key, orders_data, timeout=60)
    
    def get_cached_stats(self, force_refresh=False):
        cache_key = 'admin_stats'
        
        if force_refresh:
            cache.delete(cache_key)
            return None
        
        return self._cache_manager.get(cache_key)
    
    def set_cached_stats(self, stats_data):
        cache_key = 'admin_stats'
        self._cache_manager.set(cache_key, stats_data, timeout=120)


def admin_access_required(permission='full'):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            proxy = AdminAccessProxy()
            
            if not proxy.check_access(request, permission):
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'error': 'Доступ запрещен'}, status=403)
                return redirect('admin_login')
            
            return view_func(request, *args, **kwargs)
        return wrapped_view
    return decorator


class CachedReportProxy:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_sales_report(self, days=30, force_refresh=False):
        cache_key = f'sales_report_{days}'
        
        if not force_refresh:
            cached_data = cache.get(cache_key)
            if cached_data is not None:
                return cached_data
        
        return None
    
    def set_sales_report(self, days, report_data):
        cache_key = f'sales_report_{days}'
        cache.set(cache_key, report_data, timeout=300)
    
    def get_popular_pizzas_cache(self, limit=10, force_refresh=False):
        cache_key = f'popular_pizzas_{limit}'
        
        if not force_refresh:
            cached_data = cache.get(cache_key)
            if cached_data is not None:
                return cached_data
        
        return None
    
    def set_popular_pizzas_cache(self, limit, data):
        cache_key = f'popular_pizzas_{limit}'
        cache.set(cache_key, data, timeout=600)