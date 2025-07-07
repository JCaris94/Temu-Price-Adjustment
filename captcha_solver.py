import time
import random
import traceback
from datetime import datetime
from colorama import Fore, Style
from temu_captcha_solver.launcher import make_undetected_chromedriver_solver
from temu_captcha_solver import CaptchaSolvingException
from logger import setup_logger

logger = setup_logger()

class CaptchaSolver:
    def __init__(self, verbose=False):
        from config import Config
        config = Config()
        self.api_key = config.CAPTCHA_API_KEY
        self.verbose = verbose
        
    def solve(self, driver):
        try:
            wait_time = random.uniform(2, 5)
            logger.info(f"Waiting {wait_time:.2f} seconds before CAPTCHA solving")
            time.sleep(wait_time)
            
            logger.info("Attempting to solve CAPTCHA")
            solver = make_undetected_chromedriver_solver(api_key=self.api_key)
            solver(driver)
            
            logger.success("CAPTCHA solved successfully")
            return True
            
        except CaptchaSolvingException as e:
            logger.error(f"CAPTCHA solving failed: {str(e)}")
            if self.verbose:
                logger.verbose(f"Stacktrace:\n{traceback.format_exc()}")
            
            wait_time = random.uniform(30, 60)
            logger.warning("Manual CAPTCHA solving required")
            logger.info(f"Bot will pause for {wait_time:.2f} seconds")
            
            for i in range(int(wait_time)):
                if i % 10 == 0:
                    remaining = wait_time - i
                    logger.info(f"Manual CAPTCHA solving time remaining: {remaining:.0f} seconds")
                time.sleep(1)
            
            print(f"\n{Fore.YELLOW}{'=' * 80}")
            print(f"{Fore.RED}ACTION REQUIRED:{Style.RESET_ALL} Please solve the CAPTCHA manually!")
            print("After solving, the bot will continue automatically")
            print(f"{'=' * 80}{Style.RESET_ALL}\n")
            
            try:
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support import expected_conditions as EC
                from selenium.common.exceptions import TimeoutException
                
                WebDriverWait(driver, 120).until(
                    EC.presence_of_element_located((By.XPATH, "//input[@aria-label='Password']"))
                )
                return True
            except TimeoutException:
                logger.error("Manual CAPTCHA solving timeout")
                return False
        except Exception as e:
            logger.error(f"Unexpected error during CAPTCHA solving: {str(e)}")
            if self.verbose:
                logger.verbose(f"Stacktrace:\n{traceback.format_exc()}")
            return False