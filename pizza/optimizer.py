import math
import heapq

class DeliveryOptimizer:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def haversine_distance(self, lat1, lng1, lat2, lng2):
        R = 6371  
        try:
            lat1, lng1, lat2, lng2 = map(float, [lat1, lng1, lat2, lng2])
        except (ValueError, TypeError):
            return 0.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lng2 - lng1)
        a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
        c = 2 * math.asin(min(1, math.sqrt(a)))
        return R * c

    def a_star_search(self, start_idx, goal_indices, distance_matrix):

        queue = [(0, start_idx, (start_idx,))]
        
        while queue:
            f, current, path = heapq.heappop(queue)
            
            if all(g in path for g in goal_indices):
                return list(path), f
            
            for neighbor in range(len(distance_matrix)):
                if neighbor not in path:
                    g_cost = sum(distance_matrix[path[i]][path[i+1]] for i in range(len(path)-1))
                    new_g = g_cost + distance_matrix[current][neighbor]
                    remaining = [g for g in goal_indices if g not in path and g != neighbor]
                    h = min(distance_matrix[neighbor][g] for g in remaining) if remaining else 0
                    
                    heapq.heappush(queue, (new_g + h, neighbor, path + (neighbor,)))
        return None, 0

    def optimize_route(self, restaurant_coords, deliveries):

        if not deliveries:
            return [], 0
            
        points = [restaurant_coords] + [(d['lat'], d['lng']) for d in deliveries]
        n = len(points)
        
        matrix = [[self.haversine_distance(points[i][0], points[i][1], 
                                         points[j][0], points[j][1]) 
                  for j in range(n)] for i in range(n)]
        
        goal_indices = list(range(1, n))
        path_indices, total_dist = self.a_star_search(0, goal_indices, matrix)
        
        if not path_indices:
            return [], 0

        optimized_route = []
        for idx in path_indices:
            if idx == 0:
                optimized_route.append({"name": "Пиццерия", "address": "Точка сбора"})
            else:
                optimized_route.append(deliveries[idx-1])
                
        return optimized_route, total_dist


class PriceCalculator:

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def calculate_total_price(self, base_price, toppings_price, quantity, distance_km):

        subtotal = (float(base_price) + float(toppings_price)) * int(quantity)
        delivery_cost = 0
        if distance_km > 0:
            delivery_cost = 100 + (float(distance_km) * 20)
            
        if subtotal >= 500:
            delivery_cost = 0
            
        return round(subtotal + delivery_cost, 2)