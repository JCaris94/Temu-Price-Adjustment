import argparse
import json
import os
import random
import re
import time
import traceback
from datetime import datetime, timedelta

import numpy as np
from colorama import Fore, Style
from dotenv import load_dotenv
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains
from sklearn.linear_model import LinearRegression

from logger import setup_logger
from utils import long_random_delay, random_delay, save_order_to_txt

# Load environment variables
load_dotenv()

# Global logger instance
logger = setup_logger()

# Time delay configurations
SHORT_DELAY = (0.5, 5.0)
LONG_DELAY = (10.0, 30.0)


class CaptchaSolver:
    """Handles CAPTCHA solving operations."""
    
    def __init__(self, verbose=False):
        self.api_key = os.getenv("CAPTCHA_API_KEY")
        self.verbose = verbose

    def solve(self, driver):
        """Attempt to solve CAPTCHA automatically or prompt for manual intervention."""
        try:
            wait_time = random.uniform(3, 6)
            logger.info(f"Waiting {wait_time:.2f}s before CAPTCHA solving")
            time.sleep(wait_time)
            logger.info("Attempting to solve CAPTCHA")
            
            from temu_captcha_solver.launcher import make_undetected_chromedriver_solver
            solver = make_undetected_chromedriver_solver(api_key=self.api_key)
            solver(driver)
            
            logger.info("CAPTCHA solved successfully")
            return True
            
        except Exception as e:
            logger.error(f"CAPTCHA solving failed: {str(e)}")
            if self.verbose:
                logger.verbose(f"Stacktrace:\n{traceback.format_exc()}")
            
            logger.warning("Waiting 60s for manual intervention...")
            print(f"\n{'=' * 80}")
            print("CAPTCHA SOLVING FAILED - MANUAL INTERVENTION REQUIRED")
            print("Please solve the CAPTCHA manually in the browser window")
            print("After solving, the bot will continue automatically")
            print("You have 60 seconds to complete this action")
            print(f"{'=' * 80}\n")
            
            try:
                WebDriverWait(driver, 60).until(
                    EC.visibility_of_element_located(
                        (By.XPATH, "//input[@aria-label='Password']")
                    )
                )
                logger.info("Manual CAPTCHA solved, continuing...")
                return True
            except TimeoutException:
                logger.error("Manual CAPTCHA solving timeout after 60 seconds")
                return False


class Scheduler:
    """Manages bot execution scheduling based on historical success data."""
    
    def __init__(self, state_file="scheduler_state.json"):
        self.state_file = state_file
        self.success_data = self.load_state()
        self.model = LinearRegression()

    def load_state(self):
        """Load scheduler state from JSON file."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except Exception:
                return {"hours": {}, "timestamps": []}
        return {"hours": {}, "timestamps": []}

    def save_state(self):
        """Save current scheduler state to file."""
        with open(self.state_file, 'w') as f:
            json.dump(self.success_data, f, indent=2)

    def update_success(self, timestamp):
        """Update success metrics with new timestamp."""
        hour = timestamp.hour
        hour_key = str(hour)
        self.success_data['hours'][hour_key] = self.success_data['hours'].get(hour_key, 0) + 1
        self.success_data['timestamps'].append(timestamp.isoformat())
        self.save_state()

    def get_next_run_time(self):
        """Calculate optimal next run time based on historical data."""
        if not self.success_data['timestamps']:
            default_hour = random.randint(9, 17)
            return datetime.now().replace(
                hour=default_hour, minute=0, second=0
            ) + timedelta(days=1)

        try:
            timestamps = [datetime.fromisoformat(ts) for ts in self.success_data['timestamps']]
            X = np.array([ts.timestamp() for ts in timestamps]).reshape(-1, 1)
            y = np.array([ts.hour for ts in timestamps])
            
            self.model.fit(X, y)
            next_time = datetime.now() + timedelta(days=1)
            predicted_hour = round(self.model.predict([[next_time.timestamp()]])[0] % 24)
            predicted_hour = max(9, min(21, int(predicted_hour)))
            
        except Exception as e:
            logger.error(f"Error in prediction model: {str(e)}")
            best_hour = max(self.success_data['hours'].items(), key=lambda x: x[1])[0]
            predicted_hour = int(best_hour)

        window_minutes = random.randint(-30, 30)
        next_run = datetime.now().replace(
            hour=predicted_hour,
            minute=0,
            second=0
        ) + timedelta(minutes=window_minutes)

        if next_run < datetime.now():
            next_run += timedelta(days=1)
            
        return next_run


class TemuBot:
    """Main bot class for Temu price adjustment operations."""
    
    def __init__(self):
        self.logger = logger
        self.scheduler = Scheduler()
        self.captcha_solver = None
        self.driver = None
        self.stats = {
            'total_orders': 0,
            'valid_orders': 0,
            'processed': 0,
            'success': 0,
            'failures': 0,
            'adjustment_available': 0,
            'adjustment_not_available': 0,
            'start_time': datetime.now(),
            'end_time': None,
            'duration': 0
        }
        self.session_file = "session.json"
        self.verbose = False

    def init_driver(self, headless=False):
        """Initialize Chrome WebDriver with configurable options."""
        options = webdriver.ChromeOptions()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")
        options.add_argument('--disable-logging')
        options.add_argument('--log-level=0')
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        
        if headless:
            options.add_argument("--headless=new")
            
        self.driver = webdriver.Chrome(options=options)
        
        if not headless:
            self.driver.maximize_window()

    def save_session(self):
        """Save current browser session cookies to file."""
        try:
            cookies = self.driver.get_cookies()
            with open(self.session_file, 'w') as f:
                json.dump(cookies, f)
            logger.info("Session saved successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to save session: {str(e)}")
            return False

    def load_cached_session(self):
        """Load and validate cached session from file."""
        try:
            if not os.path.exists(self.session_file):
                logger.info("No session file found")
                return False
                
            with open(self.session_file, 'r') as f:
                cookies = json.load(f)
                
            self.driver.get("https://www.temu.com")
            for cookie in cookies:
                if 'sameSite' in cookie and not isinstance(cookie['sameSite'], str):
                    del cookie['sameSite']
                self.driver.add_cookie(cookie)
                
            self.driver.get("https://www.temu.com")
            random_delay(3, 5, "After loading cached session")
            
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located(
                        (By.XPATH, "//div[text()='Orders & Account']")
                    )
                )
                logger.info("Cached session is valid")
                return True
            except TimeoutException:
                logger.warning("Cached session is invalid")
                return False
                
        except Exception as e:
            logger.error(f"Failed to load cached session: {str(e)}")
            return False

    def handle_privacy_banner(self):
        """Close privacy banner if present."""
        try:
            random_delay(1, 3, "Before checking privacy banner")
            
            # Banner detection strategies
            banner_strategies = [
                (By.XPATH, "//div[contains(@class, '_1ay60Jd-')]"),
                (By.XPATH, "//div[contains(@class, 'privacy-banner')]"),
                (By.XPATH, "//div[contains(@class, 'cookie-banner')]"),
                (By.XPATH, "//div[contains(text(), 'We use cookies')]"),
                (By.XPATH, "//div[contains(text(), 'Your privacy')]"),
                (By.XPATH, "//div[@id='privacy-banner']"),
                (By.CSS_SELECTOR, "div[class*='privacy']"),
                (By.CSS_SELECTOR, "div[class*='cookie']"),
                (By.XPATH, "//div[@role='dialog' and contains(@aria-label, 'privacy')]")
            ]
            
            banner = None
            for strategy in banner_strategies:
                try:
                    banner = WebDriverWait(self.driver, 5).until(
                        EC.visibility_of_element_located(strategy)
                    )
                    logger.info("Privacy banner found")
                    break
                except TimeoutException:
                    continue
                    
            if not banner:
                logger.info("No privacy banner found")
                return False
                
            logger.info("Attempting to close privacy banner")
            
            # Accept button strategies
            accept_btn_strategies = [
                (By.XPATH, "//div[@role='button']//span[contains(., 'Accept all')]"),
                (By.XPATH, "//button[contains(., 'Accept all')]"),
                (By.XPATH, "//div[contains(., 'Accept all')]"),
                (By.XPATH, "//span[contains(., 'Accept all')]/ancestor::button"),
                (By.XPATH, "//div[@data-uniqid and contains(., 'Accept all')]"),
                (By.CSS_SELECTOR, "button[id*='accept']"),
                (By.CSS_SELECTOR, "div[class*='accept']"),
                (By.XPATH, "//div[contains(@class, 'KmT5vb1F')]/div[contains(., 'Accept all')]"),
                (By.XPATH, "//div[contains(@class, 'privacy-button-accept')]")
            ]
            
            accept_btn = None
            for strategy in accept_btn_strategies:
                try:
                    accept_btn = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable(strategy)
                    )
                    logger.info("Found Accept All button")
                    break
                except TimeoutException:
                    continue
                    
            if accept_btn:
                random_delay(0.5, 1.5, "Before clicking Accept All")
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", 
                    accept_btn
                )
                random_delay(0.5, 1.5, "Scrolling to Accept All button")
                
                try:
                    accept_btn.click()
                except Exception:
                    self.driver.execute_script("arguments[0].click();", accept_btn)
                    
                logger.info("Clicked 'Accept All' on privacy banner")
                random_delay(1, 3, "After closing privacy banner")
                return True
                
            # Fallback to ESC key
            try:
                actions = ActionChains(self.driver)
                actions.send_keys(Keys.ESCAPE).perform()
                logger.info("Pressed ESC to close privacy banner")
                return True
            except Exception:
                logger.warning("Could not close privacy banner")
                return False
                
        except Exception as e:
            logger.warning(f"Failed to handle privacy banner: {str(e)}")
            if self.verbose:
                logger.verbose(f"Stacktrace:\n{traceback.format_exc()}")
            return False

    def login(self):
        """Perform login sequence with fallback strategies."""
        try:
            logger.info("Navigating to login page")
            self.driver.get("https://www.temu.com/login.html")
            random_delay(2, 4, "Page load")
            self.handle_privacy_banner()
            
            if self.load_cached_session():
                logger.info("Logged in using cached session")
                return True
                
            try:
                email_field = WebDriverWait(self.driver, 30).until(
                    EC.visibility_of_element_located(
                        (By.XPATH, "//input[@aria-label='Email or phone number']")
                    )
                )
                random_delay(0.5, 1.5, "Before typing email")
                email_field.send_keys(os.getenv("TEMU_EMAIL"))
                random_delay(1, 2, "Typing email")
                
                continue_btn = WebDriverWait(self.driver, 30).until(
                    EC.element_to_be_clickable(
                        (By.XPATH, "//button[@id='submit-button']")
                    )
                )
                random_delay(0.5, 1.5, "Before clicking Continue")
                continue_btn.click()
                random_delay(3, 5, "After clicking Continue")
                
            except TimeoutException:
                logger.warning("Email field not found, proceeding directly to password/captcha")
                
            if not self.captcha_solver.solve(self.driver):
                logger.error("CAPTCHA solving failed after manual attempt")
                return False
                
            password_field = WebDriverWait(self.driver, 60).until(
                EC.visibility_of_element_located(
                    (By.XPATH, "//input[@aria-label='Password']")
                )
            )
            random_delay(0.5, 1.5, "Before typing password")
            password_field.send_keys(os.getenv("TEMU_PASSWORD"))
            random_delay(1, 2, "Typing password")
            
            submit_btn = WebDriverWait(self.driver, 30).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[@id='submit-button']")
                )
            )
            random_delay(0.5, 1.5, "Before clicking Sign In")
            submit_btn.click()
            random_delay(3, 5, "After clicking Sign In")
            
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//div[text()='Orders & Account']")
                )
            )
            self.save_session()
            return True
            
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            if self.verbose:
                logger.verbose(f"Stacktrace:\n{traceback.format_exc()}")
            return False

    def navigate_to_orders(self):
        """Navigate to orders management page."""
        try:
            logger.info("Navigating to orders page")
            orders_btn = WebDriverWait(self.driver, 30).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//div[text()='Orders & Account']")
                )
            )
            random_delay(0.5, 1.5, "Before clicking Orders & Account")
            orders_btn.click()
            
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//div[contains(@class, '_2DCuXnC8')]")
                )
            )
            random_delay(2, 4, "Orders page load")
            return True
            
        except Exception as e:
            logger.error(f"Navigation to orders failed: {str(e)}")
            return False

    def is_view_more_present(self):
        """Check if 'View more' button is present."""
        try:
            return WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//span[contains(text(),'View more')]/parent::div[@role='button']")
                )
            ) is not None
        except TimeoutException:
            return False

    def click_view_more(self):
        """Click the 'View more' button to load additional orders."""
        try:
            view_more_btn = WebDriverWait(self.driver, 20).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//span[contains(text(),'View more')]/parent::div[@role='button']")
                )
            )
            random_delay(0.5, 1.5, "Before clicking View More")
            view_more_btn.click()
            
            WebDriverWait(self.driver, 30).until(
                EC.invisibility_of_element_located(
                    (By.XPATH, "//span[contains(text(),'Loading')]")
                )
            )
            random_delay(3, 5, "After clicking View More")
            return True
            
        except Exception as e:
            logger.error(f"Failed to click 'View more': {str(e)}")
            return False

    def get_order_elements(self):
        """Locate order elements using multiple strategies."""
        strategies = [
            (By.XPATH, "//div[contains(@class, '_2DCuXnC8') and @data-uniqid]"),
            (By.XPATH, "//span[contains(text(),'PO-')]/ancestor::div[contains(@class, '_2DCuXnC8')]"),
            (By.XPATH, "//span[normalize-space()='View order details']/ancestor::div[contains(@class, '_2DCuXnC8')]")
        ]
        
        for i, strategy in enumerate(strategies, 1):
            try:
                elements = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_all_elements_located(strategy)
                )
                if elements:
                    logger.info(f"Found {len(elements)} orders using strategy {i}")
                    return elements
            except TimeoutException:
                logger.info(f"Strategy {i} failed, trying next")
                continue
                
        logger.warning("No orders found using any strategy")
        return []

    def get_orders(self):
        """Extract and parse order information from page elements."""
        try:
            orders = []
            order_elements = self.get_order_elements()
            
            for element in order_elements:
                try:
                    # Extract order ID
                    order_id_element = self.safe_find_element(
                        element,
                        (By.XPATH, ".//span[contains(@class, 'VlINftPl') and contains(., 'PO-')]"),
                        (By.XPATH, ".//span[contains(text(),'PO-')]"),
                        (By.CLASS_NAME, "_2tnFgQdq")
                    )
                    order_id_text = order_id_element.text.strip()
                    order_id_match = re.search(r'PO-[\w-]+', order_id_text)
                    order_id = order_id_match.group(0) if order_id_match else "N/A"
                    
                    # Extract order date
                    date_element = self.safe_find_element(
                        element,
                        (By.XPATH, ".//span[contains(@class, 'VlINftPl')]/span"),
                        (By.XPATH, ".//span[contains(@class, '_2tnFgQdq')][2]"),
                        (By.XPATH, ".//span[contains(text(),'Order Time:')]/following-sibling::span")
                    )
                    date_str = date_element.text.strip() if date_element else "N/A"
                    order_date = parse_order_date(date_str)
                    
                    # Extract item count
                    items_element = self.safe_find_element(
                        element,
                        (By.XPATH, ".//span[contains(text(),'items:')]"),
                        (By.XPATH, ".//span[contains(@class, '_2tnFgQdq')][1]")
                    )
                    items_text = items_element.text.strip() if items_element else "N/A"
                    items_match = re.search(r'(\d+)\s+items?', items_text)
                    item_count = items_match.group(1) if items_match else "N/A"
                    
                    orders.append({
                        'id': order_id,
                        'date_str': date_str,
                        'date_obj': order_date,
                        'item_count': item_count,
                        'valid': validate_order_date(order_date) if order_date else False,
                        'element': element
                    })
                    
                except Exception as e:
                    logger.warning(f"Error processing order element: {str(e)}")
                    
            return orders
            
        except Exception as e:
            logger.error(f"Failed to get orders: {str(e)}")
            return []

    def safe_find_element(self, parent, *strategies):
        """Find element using multiple strategies with fallback."""
        for strategy in strategies:
            try:
                return parent.find_element(*strategy)
            except Exception:
                continue
        raise NoSuchElementException(f"Element not found using strategies: {strategies}")

    def get_order_details_page(self, order_id):
        """Navigate to specific order details page."""
        try:
            logger.info(f"Navigating to order details: {order_id}")
            order_url = f"https://www.temu.com/bgt_order_detail.html?parent_order_sn={order_id}"
            self.driver.get(order_url)
            
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//div[@class='_3ofg55P_']")
                )
            )
            long_random_delay(3, 15, "Order details page load")
            return True
            
        except Exception as e:
            logger.error(f"Failed to navigate to order details: {str(e)}")
            return False

    def get_element_text_or_default(self, locator, by=By.XPATH, default="N/A"):
        """Get element text with safe fallback."""
        try:
            element = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((by, locator))
            )
            return element.text.strip()
        except Exception:
            return default

    def get_tracking_info(self):
        """Extract tracking information from order page."""
        logger.info("Clicking Track button")
        
        # Track button location strategies
        track_btn_strategies = [
            (By.CSS_SELECTOR, "div[class='_2ugbvrpI _3E4sGl93 _28_m8Owy _3RLRwCY0 _1Qlry8Qy'] span[class='_3cgghkPI']"),
            (By.XPATH, "//div[@class='_2ugbvrpI _3E4sGl93 _28_m8Owy _3RLRwCY0 _1Qlry8Qy']//span[@class='_3cgghkPI']"),
            (By.XPATH, "(//span[@class='_3cgghkPI'])[3]"),
            (By.XPATH, "//span[contains(text(),'Track')]"),
            (By.CSS_SELECTOR, "span._3cgghkPI"),
            (By.XPATH, "//div[contains(@class, 'tracking-btn')]"),
            (By.CLASS_NAME, "track-button")
        ]
        
        track_btn = None
        for strategy in track_btn_strategies:
            try:
                track_btn = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable(strategy))
                break
            except Exception:
                continue
                
        if not track_btn:
            raise NoSuchElementException("Track button not found")
            
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", 
            track_btn
        )
        random_delay(0.5, 1.5, "Scrolling to Track button")
        self.driver.execute_script("arguments[0].click();", track_btn)
        long_random_delay(3, 15, "After clicking Track")
        
        WebDriverWait(self.driver, 30).until(
            EC.presence_of_element_located(
                (By.CLASS_NAME, "trackingInfoWrap-1NRtF"))
            )
        long_random_delay(3, 15, "Tracking page load")
        
        # Extract tracking number
        tracking_number = "N/A"
        tracking_strategies = [
            (By.XPATH, "//div[contains(@class, 'serviceProviderNumber-VPeGz')]"),
            (By.CLASS_NAME, "serviceProviderNumber-VPeGz"),
            (By.XPATH, "//div[contains(text(), 'Tracking Number:')]/following-sibling::div"),
            (By.XPATH, "//div[contains(text(), 'Tracking Number:')]"),
            (By.CSS_SELECTOR, ".trackingInfo-zPYF_"),
            (By.XPATH, "//div[@class='trackingInfo-zPYF_']"),
            (By.XPATH, "//div[contains(@class, 'tracking-number')]")
        ]
        
        for strategy in tracking_strategies:
            try:
                element = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located(strategy))
                text = element.text
                
                if 'Tracking Number:' in text:
                    tracking_number = text.split('Tracking Number:')[-1].strip()
                    if 'copy' in tracking_number:
                        tracking_number = tracking_number.split('copy')[0].strip()
                else:
                    tracking_number = text
                    
                tracking_number = re.sub(r'\s+', '', tracking_number)
                break
            except Exception:
                continue
                
        # Extract delivery information
        delivery_text = self.get_element_text_or_default(
            "//div[@class='deliveryInfoWrap-12bOU']",
            By.XPATH,
            default="N/A"
        )
        from utils import parse_delivery_date
        formatted_delivery = parse_delivery_date(delivery_text)
        
        self.driver.back()
        long_random_delay(3, 15, "After going back from tracking")
        
        return {
            'tracking_number': tracking_number,
            'delivery_text': delivery_text,
            'formatted_delivery': formatted_delivery
        }

    def save_page_source(self, prefix="error"):
        """Save current page source for debugging."""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"page_source_{prefix}_{timestamp}.html"
            
            with open(filename, "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
                
            logger.error(f"Saved page source to {filename}")
        except Exception as e:
            logger.error(f"Failed to save page source: {str(e)}")

    def process_orders(self):
        """Main order processing workflow."""
        try:
            # Load all available orders
            while self.is_view_more_present():
                self.click_view_more()
                long_random_delay(10, 20, "Loading more orders")
                
            orders = self.get_orders()
            if not orders:
                logger.info("No orders found")
                return True
                
            # Update statistics
            self.stats['total_orders'] = len(orders)
            valid_orders = [order for order in orders if order['valid']]
            self.stats['valid_orders'] = len(valid_orders)
            
            logger.info(f"Found {self.stats['total_orders']} orders in total")
            logger.info(f"Found {self.stats['valid_orders']} valid orders within 30 days")
            
            # Process top orders
            max_orders = min(10, self.stats['valid_orders'])
            orders_to_process = valid_orders[:max_orders]
            logger.info(f"Processing {len(orders_to_process)} orders in this run")
            
            for i, order in enumerate(orders_to_process, 1):
                self.stats['processed'] += 1
                logger.info(f"\n{'='*50}")
                logger.info(f"Processing order {i}/{len(orders_to_process)}")
                logger.info(f"Order ID: {order['id']}")
                logger.info(f"Order date: {order['date_obj'].strftime('%d/%m/%Y') if order['date_obj'] else 'N/A'}")
                logger.info(f"Item count: {order['item_count']}")
                
                if not self.process_order(order):
                    logger.warning(f"Skipping order {order['id']}")
                    
                long_random_delay(15, 45, "Between order processing")
                
            return True
            
        except Exception as e:
            logger.error(f"Order processing failed: {str(e)}")
            if self.verbose:
                logger.verbose(f"Stacktrace:\n{traceback.format_exc()}")
            return False

    def process_order(self, order):
        """Process individual order for price adjustment with enhanced verification"""
        order['attempts'] = 0
        max_attempts = 5
        result = None
        
        while order['attempts'] < max_attempts and result is None:
            try:
                order['attempts'] += 1
                logger.info(f"Attempt {order['attempts']}/{max_attempts} for order {order['id']}")
                
                if not self.get_order_details_page(order['id']):
                    continue
                    
                # Extract tracking info
                tracking_info = self.get_tracking_info()
                order['tracking_info'] = tracking_info
                order['adjustment_attempted'] = False
                order['adjustment_success'] = False
                order['adjustment_status'] = 'not_attempted'
                order['last_error'] = ''
                
                logger.info(f"Tracking Code: {tracking_info.get('tracking_number', 'N/A')}")
                logger.info(f"Delivery estimate: {tracking_info.get('formatted_delivery', 'N/A')}")
                
                # Extract order details
                order_details = {
                    'item_name': self.get_element_text_or_default(
                        "//img[@aria-label='goods banner']/../following-sibling::div/span[@role='button']//span"),
                    'order_date': self.get_element_text_or_default(
                        "//div[contains(text(), 'Order time:')]"),
                    'order_id': order['id']
                }
                order['details'] = order_details
                
                # Attempt price adjustment with enhanced verification
                adjustment_result = self.attempt_price_adjustment(order)
                
                if adjustment_result is True:
                    self.stats['success'] += 1
                    self.scheduler.update_success(datetime.now())
                    order['adjustment_status'] = 'success'
                    order['adjustment_success'] = True
                    result = True
                elif adjustment_result is False:
                    self.stats['adjustment_not_available'] += 1
                    order['adjustment_status'] = 'not_available'
                    result = False
                else:
                    self.stats['failures'] += 1
                    order['adjustment_status'] = 'failed'
                    order['last_error'] = 'Price adjustment failed'
                    
                order['adjustment_attempted'] = True
                save_order_data(order)
                save_order_to_txt(order)
                
                self.navigate_to_orders_page()
                
            except Exception as e:
                logger.error(f"Error processing order: {str(e)}")
                if self.verbose:
                    logger.verbose(f"Stacktrace:\n{traceback.format_exc()}")
                    
                self.stats['failures'] += 1
                self.save_page_source(f"order_{order['id']}")
                order['last_error'] = str(e)
                order['adjustment_status'] = 'failed'
                
                try:
                    self.navigate_to_orders_page()
                except Exception:
                    pass
                    
                # Random delay before next attempt
                delay = long_random_delay(15, 45, "Before next attempt")
                logger.info(f"Waiting {delay:.2f}s before next attempt")
        
        return result is True

    def navigate_to_orders_page(self):
        """Return to main orders page."""
        try:
            self.driver.get("https://www.temu.com/bgt_order.html")
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//div[contains(@class, '_2DCuXnC8')]")
                )
            )
            long_random_delay(3, 15, "Navigating back to orders page")
            return True
        except Exception as e:
            logger.error(f"Failed to navigate to orders page: {str(e)}")
            return False

    def check_dialog_type(self):
        """Check the type of the dialog that appears after clicking price adjustment.
        Returns:
            'success' if the dialog is the price adjustment form
            'failure' if the dialog indicates adjustment is not available
            'unknown' otherwise
        """
        try:
            # Get the dialog element
            dialog = WebDriverWait(self.driver, 5).until(
                EC.visibility_of_element_located((By.XPATH, "//div[@role='dialog']"))
            )
            dialog_text = dialog.text.lower()
            logger.info(f"Dialog text: {dialog_text[:200]}...")

            # Adicionar pausa de 5-10 segundos antes de verificar o tipo
            long_random_delay(5, 10, "After dialog appears")

            # Failure indicators (multiple languages)
            failure_indicators = [
                r"sorry,? you cannot request",
                r"not eligible for price adjustment",
                r"exact same specifications",
                r"same seller",
                r"desculpe,? você não pode solicitar",
                r"não é elegível para ajuste",
                r"mesmas especificações",
                r"mesmo vendedor",
                r"items that are sold out",
                r"discontinued",
                r"out of stock",
                r"no longer available",
                r"refunded",
                r"refund\/return"
            ]

            for indicator in failure_indicators:
                if re.search(indicator, dialog_text, re.IGNORECASE):
                    logger.info("Failure dialog detected")
                    return 'failure'

            # Success indicators (multiple languages)
            success_indicators = [
                r"request a price adjustment",
                r"select refund method",
                r"price adjustment",
                r"refund amount",
                r"reembolso",
                r"ajuste de preço",
                r"solicitar ajuste",
                r"selecionar método"
            ]

            for indicator in success_indicators:
                if re.search(indicator, dialog_text, re.IGNORECASE):
                    logger.info("Success dialog detected")
                    return 'success'

            # Class-based indicators as fallback
            class_indicators = [
                "_39vL3TE4",  # Error title class
                "_10EiyDKr",  # Content container
                "_2OaJDN8Y"   # Dialog container
            ]
            found_classes = sum(
                1 for cls in class_indicators 
                if self.driver.find_elements(By.CLASS_NAME, cls)
            )

            if found_classes >= 2:
                logger.info("Failure dialog detected by class indicators")
                return 'failure'

            logger.warning("Unknown dialog type")
            return 'unknown'
        except Exception as e:
            logger.error(f"Error checking dialog type: {str(e)}")
            return 'unknown'

    def attempt_price_adjustment(self, order):
        """Attempt to initiate price adjustment with enhanced button detection"""
        try:
            logger.info("Attempting price adjustment")
            
            # Button location strategies - enhanced detection
            strategies = [
                # Exact text match
                (By.XPATH, "//div[contains(@class, '_1TeP2qll') and contains(., 'Price adjustment')]"),
                (By.XPATH, "//div[contains(@class, '_2bQDCYwF') and contains(., 'Price adjustment')]"),
                (By.XPATH, "//div[@role='button' and .//span[contains(text(), 'Price adjustment')]]"),
                
                # Portuguese version
                (By.XPATH, "//div[contains(@class, '_1TeP2qll') and contains(., 'Ajuste de preço')]"),
                (By.XPATH, "//div[contains(@class, '_2bQDCYwF') and contains(., 'Ajuste de preço')]"),
                (By.XPATH, "//div[@role='button' and .//span[contains(text(), 'Ajuste de preço')]]"),
                
                # Fallback strategies
                (By.XPATH, "//div[contains(@class, 'adjustment') and contains(., 'Price')]"),
                (By.XPATH, "//div[contains(@data-uniqid, 'price-adjustment')]"),
                (By.CSS_SELECTOR, "div[class*='adjustment']"),
                (By.XPATH, "//div[contains(@data-testid, 'price-adjustment')]"),
                (By.XPATH, "//div[contains(@data-role, 'price-adjustment')]"),
                (By.XPATH, "//div[contains(@id, 'priceAdjustmentBtn')]")
            ]
            
            max_attempts = 7
            for attempt in range(1, max_attempts + 1):
                logger.info(f"Price adjustment attempt {attempt}/{max_attempts}")
                price_adj_btn = None
                
                for strategy in strategies:
                    try:
                        elements = self.driver.find_elements(strategy[0], strategy[1])
                        for element in elements:
                            if element.is_displayed() and ("Price adjustment" in element.text or "Ajuste de preço" in element.text):
                                price_adj_btn = element
                                logger.info(f"Found valid button using strategy: {strategy}")
                                break
                        if price_adj_btn:
                            break
                    except Exception:
                        continue
                        
                if not price_adj_btn:
                    logger.error(f"Price adjustment button not found on attempt {attempt}")
                    if attempt == max_attempts:
                        return None
                        
                    # Try scrolling to trigger lazy loading
                    self.driver.execute_script("window.scrollBy(0, 500);")
                    long_random_delay(3, 5, "Scrolling to find button")
                    self.driver.refresh()
                    long_random_delay(5, 10, "Page refresh")
                    continue
                    
                # Double verification
                if "Price adjustment" not in price_adj_btn.text and "Ajuste de preço" not in price_adj_btn.text:
                    logger.warning("Button text verification failed, trying next strategy")
                    continue
                    
                # Scroll to button with smooth behavior
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", 
                    price_adj_btn
                )
                long_random_delay(1, 3, "After scrolling to button")
                
                # Highlight button for visual confirmation
                self.driver.execute_script(
                    "arguments[0].style.border = '3px solid red';", 
                    price_adj_btn
                )
                long_random_delay(0.5, 1, "Highlighting button")
                
                # Click using JavaScript to avoid interception
                self.driver.execute_script("arguments[0].click();", price_adj_btn)
                logger.info("Clicked price adjustment button")
                
                # Wait for the dialog to appear and check its type
                try:
                    # Wait for any dialog to appear with increased timeout
                    WebDriverWait(self.driver, 15).until(
                        EC.visibility_of_element_located((By.XPATH, "//div[@role='dialog']"))
                    )
                    
                    # Check dialog content
                    dialog_type = self.check_dialog_type()
                    
                    if dialog_type == 'success':
                        logger.info("Price adjustment form detected")
                        return self.handle_price_adjustment_flow(order)
                    elif dialog_type == 'failure':
                        logger.info("Price adjustment not available")
                        return False
                    else:
                        logger.warning("Unknown dialog type after click")
                        # Try to close the dialog and retry
                        try:
                            close_btn = self.driver.find_element(
                                By.XPATH, "//div[@role='button' and .//*[local-name()='svg']]"
                            )
                            self.driver.execute_script("arguments[0].click();", close_btn)
                            logger.info("Closed unknown dialog")
                        except Exception:
                            pass
                        continue
                except TimeoutException:
                    logger.warning("Dialog did not appear after click")
                    if attempt < max_attempts:
                        continue
                    else:
                        return None
                    
            logger.error("All price adjustment attempts failed")
            return None
            
        except Exception as e:
            logger.error(f"Price adjustment failed: {str(e)}")
            if self.verbose:
                logger.verbose(f"Stacktrace:\n{traceback.format_exc()}")
            return None

    def handle_price_adjustment_flow(self, order):
        """Complete the price adjustment workflow with enhanced verification"""
        try:
            logger.info("Starting price adjustment flow")
            
            # Wait for main elements to appear with timeout
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located(
                        (By.XPATH, "//div[contains(text(), 'Request a price adjustment') or contains(text(), 'Solicitar ajuste de preço')]")
                    )
                )
            except TimeoutException:
                logger.error("Price adjustment window not detected")
                return False
                
            logger.info("Price adjustment window appeared")
            
            # Request button strategies with enhanced verification
            request_btn = None
            request_texts = [
                "Request a price adjustment",
                "Solicitar ajuste de preço",
                "Request adjustment",
                "Solicitar reembolso"
            ]
            
            for text in request_texts:
                try:
                    elements = self.driver.find_elements(By.XPATH, f"//div[@role='button' and contains(., '{text}')]")
                    for element in elements:
                        if text in element.text and element.is_displayed():
                            request_btn = element
                            logger.info(f"Found request button with text: {text}")
                            break
                    if request_btn:
                        break
                except Exception:
                    continue
            
            if not request_btn:
                logger.error("Valid request button not found in adjustment window")
                return False
                
            # Double verification
            if not any(text in request_btn.text for text in request_texts):
                logger.error("Request button text verification failed")
                return False
                
            # Scroll and click request button
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", 
                request_btn
            )
            long_random_delay(1, 2, "After scrolling to request button")
            
            self.driver.execute_script("arguments[0].click();", request_btn)
            long_random_delay(3, 5, "After clicking request button")
            
            # Wait for refund method selection with timeout
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located(
                        (By.XPATH, "//div[contains(text(), 'Select refund method') or contains(text(), 'Selecionar método de reembolso')]")
                    )
                )
            except TimeoutException:
                logger.error("Refund method selection not detected")
                return False
                
            logger.info("Refund method selection appeared")
            
            # Select "Receive in seconds" option with enhanced verification
            refund_method = None
            refund_texts = [
                "Receive in seconds",
                "Receber em segundos",
                "Instant refund",
                "Reembolso instantâneo"
            ]
            
            for text in refund_texts:
                try:
                    elements = self.driver.find_elements(By.XPATH, f"//div[contains(., '{text}')]")
                    for element in elements:
                        if text in element.text and element.is_displayed():
                            refund_method = element
                            logger.info(f"Found refund method: {text}")
                            break
                    if refund_method:
                        break
                except Exception:
                    continue
                    
            if not refund_method:
                logger.error("Valid refund method option not found")
                return False
                
            # Double verification
            if not any(text in refund_method.text for text in refund_texts):
                logger.error("Refund method text verification failed")
                return False
                
            # Select refund method
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", 
                refund_method
            )
            long_random_delay(0.5, 1, "After scrolling to refund method")
            
            self.driver.execute_script("arguments[0].click();", refund_method)
            long_random_delay(2, 4, "After selecting refund method")
            
            # Verify selection visually
            try:
                self.driver.execute_script(
                    "arguments[0].style.border = '2px solid green';", 
                    refund_method
                )
                long_random_delay(0.5, 1, "Highlighting selected method")
            except Exception:
                pass
                
            # Submit button with enhanced verification
            submit_btn = None
            submit_texts = [
                "Submit",
                "Enviar",
                "Confirm",
                "Confirmar",
                "Request",
                "Solicitar"
            ]
            
            for text in submit_texts:
                try:
                    elements = self.driver.find_elements(By.XPATH, f"//div[@role='button' and contains(., '{text}')]")
                    for element in elements:
                        if text in element.text and element.is_displayed():
                            submit_btn = element
                            logger.info(f"Found submit button: {text}")
                            break
                    if submit_btn:
                        break
                except Exception:
                    continue
                    
            if not submit_btn:
                logger.error("Valid submit button not found")
                return False
                
            # Double verification
            if not any(text in submit_btn.text for text in submit_texts):
                logger.error("Submit button text verification failed")
                return False
                
            # Submit request
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", 
                submit_btn
            )
            long_random_delay(1, 2, "After scrolling to submit button")
            
            self.driver.execute_script("arguments[0].click();", submit_btn)
            long_random_delay(5, 15, "After submitting request")
            
            # Verify confirmation with multiple strategies
            confirmation = False
            refund_amount = "N/A"
            confirmation_indicators = [
                "Your refund is being processed",
                "Reembolso está sendo processado",
                "request has been submitted",
                "solicitação foi enviada",
                "successfully requested",
                "solicitado com sucesso"
            ]
            
            for text in confirmation_indicators:
                try:
                    element = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located(
                            (By.XPATH, f"//*[contains(text(), '{text}')]")
                        )
                    )
                    logger.info(f"Confirmation found: {text}")
                    confirmation = True
                    
                    # Try to extract refund amount
                    try:
                        amount_elements = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'refund-amount')]")
                        for elem in amount_elements:
                            if "$" in elem.text or "R$" in elem.text:
                                refund_amount = elem.text.strip()
                                break
                        order['refund_amount'] = refund_amount
                        logger.info(f"Refund amount detected: {refund_amount}")
                    except Exception:
                        logger.warning("Could not extract refund amount")
                    
                    break
                except TimeoutException:
                    continue
                    
            if not confirmation:
                logger.error("Confirmation message not found")
                self.save_page_source(f"adjustment_failure_{order['id']}")
                return False
                
            logger.success(f"Price adjustment SUCCESS for order {order['id']}")
            return True
            
        except Exception as e:
            logger.error(f"Price adjustment flow failed: {str(e)}")
            self.save_page_source(f"adjustment_error_{order['id']}")
            if self.verbose:
                logger.verbose(f"Stacktrace:\n{traceback.format_exc()}")
            return False
        
    def print_summary(self):
        """Print execution statistics summary."""
        self.stats['end_time'] = datetime.now()
        self.stats['duration'] = (
            self.stats['end_time'] - self.stats['start_time']
        ).total_seconds() / 60
        
        summary = f"""
========================= EXECUTION SUMMARY =========================
Total orders: {self.stats['total_orders']}
Valid orders: {self.stats['valid_orders']}
Processed orders: {self.stats['processed']}
Successful adjustments: {self.stats['success']}
Adjustment not available: {self.stats['adjustment_not_available']}
Failures: {self.stats['failures']}
Execution time: {self.stats['duration']:.2f} minutes
=====================================================================
"""
        logger.info(summary)
        self.print_summary_box(self.stats)

    def print_summary_box(self, stats):
        """Print formatted summary box with color coding."""
        title = "EXECUTION SUMMARY"
        content = f"""
Total orders: {stats['total_orders']}
Valid orders: {stats['valid_orders']}
Processed orders: {stats['processed']}
Successful adjustments: {stats['success']}
Adjustment not available: {stats['adjustment_not_available']}
Failures: {stats['failures']}
Execution time: {stats['duration']:.2f} minutes
"""
        # Color selection based on success
        if stats['success'] > 0:
            color = Fore.GREEN
        elif stats['failures'] > 0:
            color = Fore.RED
        else:
            color = Fore.YELLOW
            
        reset = Style.RESET_ALL
        border = color + "═" * (len(title) + 4) + reset
        
        print(f"{color}╔{border}╗{reset}")
        print(f"{color}║  {title}  ║{reset}")
        print(f"{color}╠{border}╣{reset}")
        
        for line in content.strip().split('\n'):
            print(f"{color}║{line}║{reset}")
            
        print(f"{color}╚{border}╝{reset}")

    def run(self, immediate=False, verbose=False, headless=False):
        """Main bot execution flow."""
        self.verbose = verbose
        self.captcha_solver = CaptchaSolver(verbose=verbose)
        global logger
        logger = setup_logger(verbose=verbose)
        self.logger = logger
        
        self.stats['start_time'] = datetime.now()
        logger.info("Starting TemuBot execution")
        
        self.init_driver(headless)
        
        try:
            if self.login() and self.navigate_to_orders():
                self.process_orders()
                
            self.print_summary()
            
            if immediate:
                next_run = self.scheduler.get_next_run_time()
                logger.info(f"Next scheduled run at: {next_run.strftime('%d/%m/%Y - %H:%M:%S')}")
                
        except Exception as e:
            logger.error(f"Critical error during execution: {str(e)}")
            if verbose:
                logger.verbose(f"Stacktrace:\n{traceback.format_exc()}")
            self.print_summary()
        finally:
            self.driver.quit()


def parse_order_date(date_str):
    """Parse order date from various string formats."""
    try:
        patterns = [
            r'([A-Z][a-z]{2} \d{1,2},? \d{4})',
            r'(\d{1,2} [A-Z][a-z]{2} \d{4})',
            r'([A-Z][a-z]{2} \d{1,2})',
            r'(\d{1,2}/\d{1,2}/\d{4})',
            r'(\d{1,2}-\d{1,2}-\d{4})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, date_str)
            if match:
                date_part = match.group(1).replace(',', '')
                try:
                    return datetime.strptime(date_part, "%b %d %Y")
                except Exception:
                    try:
                        return datetime.strptime(date_part, "%d %b %Y")
                    except Exception:
                        try:
                            return datetime.strptime(date_part, "%d/%m/%Y")
                        except Exception:
                            try:
                                return datetime.strptime(date_part, "%m/%d/%Y")
                            except Exception:
                                continue
                                
        if "Order time:" in date_str:
            parts = date_str.split("Order time:")
            if len(parts) > 1:
                return parse_order_date(parts[1])
                
        return None
        
    except Exception as e:
        logger.error(f"Error parsing date: {date_str} - {str(e)}")
        return None


def validate_order_date(order_date):
    """Validate if order is within 30-day adjustment window."""
    if order_date is None:
        return False
        
    thirty_days_ago = datetime.now() - timedelta(days=30)
    return order_date >= thirty_days_ago


def save_order_data(order):
    """Save order data to JSON file."""
    try:
        # Clean up un-serializable elements
        if 'element' in order:
            del order['element']
            
        for key in list(order.keys()):
            if isinstance(order[key], webdriver.remote.webelement.WebElement):
                del order[key]
                
        # Convert datetime objects
        if 'date_obj' in order and order['date_obj']:
            order['date_obj'] = order['date_obj'].isoformat()
            
        # Load existing data
        orders = []
        file_path = "orders.json"
        
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r') as f:
                    orders = json.load(f)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"Corrupted orders file, resetting: {str(e)}")
                orders = []
                
        # Update or add new order
        existing = next((o for o in orders if o['id'] == order['id']), None)
        if existing:
            existing.update(order)
        else:
            orders.append(order)
            
        # Save to file
        with open(file_path, 'w') as f:
            json.dump(orders, f, indent=2, default=str)
            
        logger.info("Order data saved successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error saving order data: {str(e)}")
        return False


def main():
    """Main entry point with command-line arguments."""
    parser = argparse.ArgumentParser(description='Temu Price Adjustment Bot')
    parser.add_argument('--now', action='store_true', help='Run the bot immediately')
    parser.add_argument('--schedule', action='store_true', help='Run the bot on scheduled intervals')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging with stack traces')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode')
    args = parser.parse_args()
    
    bot = TemuBot()
    
    if args.now:
        bot.run(immediate=True, verbose=args.verbose, headless=args.headless)
    elif args.schedule:
        next_run = bot.scheduler.get_next_run_time()
        logger.info(f"Next run scheduled at: {next_run.strftime('%d/%m/%Y - %H:%M:%S')}")
        
        while True:
            current_time = datetime.now()
            if current_time >= next_run:
                bot.run(verbose=args.verbose, headless=args.headless)
                next_run = bot.scheduler.get_next_run_time()
                logger.info(f"Next run scheduled at: {next_run.strftime('%d/%m/%Y - %H:%M:%S')}")
                
            sleep_time = random.randint(300, 1800)
            logger.info(f"Sleeping for {sleep_time} seconds")
            time.sleep(sleep_time)
    else:
        print("Please specify a run mode: --now or --schedule")


if __name__ == "__main__":
    logger = setup_logger()
    main()