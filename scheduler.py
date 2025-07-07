from datetime import datetime, timedelta
import random
import pickle
import os
from config import Config

class Scheduler:
    def __init__(self):
        self.config = Config()
        self.success_hours = {}
        self.load_model()
    
    def load_model(self):
        if os.path.exists(self.config.ML_MODEL_PATH):
            with open(self.config.ML_MODEL_PATH, 'rb') as f:
                self.model = pickle.load(f)
        else:
            self.model = None
    
    def update_success_hour(self, hour):
        self.success_hours[hour] = self.success_hours.get(hour, 0) + 1
        self.train_model()
    
    def train_model(self):
        pass
    
    def get_next_run_time(self):
        best_hour = self.predict_best_hour()
        window_minutes = random.randint(-15, 15)
        next_run = datetime.now().replace(
            hour=best_hour, 
            minute=0, 
            second=0
        ) + timedelta(minutes=window_minutes)
        if next_run < datetime.now():
            next_run += timedelta(days=1)
        return next_run
    
    def predict_best_hour(self):
        if self.success_hours:
            return max(self.success_hours, key=self.success_hours.get)
        return random.randint(9, 17)