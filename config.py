import os
from dotenv import load_dotenv

class Config:
    def __init__(self):
        load_dotenv()
        self.EMAIL = os.getenv("TEMU_EMAIL")
        self.PASSWORD = os.getenv("TEMU_PASSWORD")
        self.SESSION_FILE = "session.json"
        self.ORDERS_FILE = "orders.json"
        self.LOG_FILE = "temu_bot.log"
        self.ML_MODEL_PATH = "success_model.pkl"
        self.CAPTCHA_API_KEY = os.getenv("CAPTCHA_API_KEY")
        self.ORDERS_FOLDER = "orders"