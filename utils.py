import time
import random
import os
import re
import traceback
import glob
from datetime import datetime
from colorama import Fore, Style
from logger import setup_logger

logger = setup_logger()

SHORT_DELAY = (0.5, 5.0)
LONG_DELAY = (10.0, 60.0)

def random_delay(min_sec=None, max_sec=None, reason=None):
    min_val = min_sec or SHORT_DELAY[0]
    max_val = max_sec or SHORT_DELAY[1]
    delay = random.uniform(min_val, max_val)
    
    if reason:
        logger.info(f"Delaying {delay:.2f}s: {reason}")
    time.sleep(delay)
    if reason:
        logger.info(f"Delay completed")

def long_random_delay(min_sec=None, max_sec=None, reason=None):
    min_val = min_sec or LONG_DELAY[0]
    max_val = max_sec or LONG_DELAY[1]
    delay = random.uniform(min_val, max_val)
    
    if reason:
        logger.info(f"Long delay {delay:.2f}s: {reason}")
    time.sleep(delay)
    if reason:
        logger.info(f"Long delay completed")
    return delay

def save_order_to_txt(order, folder="orders"):
    if not os.path.exists(folder):
        os.makedirs(folder)
    
    # Status mapping with detailed descriptions
    status_map = {
        'success': 'SUCESSO',
        'not_available': 'INDISPONIVEL',
        'failed': 'FALHA',
        'not_attempted': 'NAO_TENTADO',
        'unknown': 'DESCONHECIDO'
    }
    
    status_description = {
        'success': 'Reembolso solicitado com sucesso',
        'not_available': 'Reembolso não disponível para este pedido',
        'failed': 'Falha ao solicitar reembolso',
        'not_attempted': 'Reembolso não foi tentado',
        'unknown': 'Status desconhecido'
    }
    
    # Get status info
    status = order.get('adjustment_status', 'unknown')
    status_code = status_map.get(status, 'DESCONHECIDO')
    description = status_description.get(status, 'Status desconhecido')
    
    # Get tracking number or fallback to order ID
    tracking_info = order.get('tracking_info', {})
    tracking_number = tracking_info.get('tracking_number', 'N/A')
    base_name = tracking_number if tracking_number != 'N/A' else order.get('id', 'N/A')
    
    # Sanitize base name for filename
    safe_name = re.sub(r'[\\/*?:"<>|]', '', base_name)
    
    # Create filename
    filename = f"{status_code}_{safe_name}.txt"
    filepath = os.path.join(folder, filename)
    
    # Delete previous files for this order
    pattern = os.path.join(folder, f"*_{safe_name}.txt")
    for old_file in glob.glob(pattern):
        try:
            os.remove(old_file)
            logger.info(f"Removed old order file: {os.path.basename(old_file)}")
        except Exception as e:
            logger.error(f"Error removing old order file {old_file}: {str(e)}")
    
    # Prepare content
    content = f"""Updated at: {datetime.now().strftime('%d.%m.%Y at %H:%M:%S')}

Order ID: {order.get('id', 'N/A')}
Tracking Number: {tracking_number}
Delivery: {tracking_info.get('delivery_text', 'N/A')}
Item Count: {order.get('item_count', 'N/A')}
Order Time: {order.get('date_str', 'N/A')}

===== STATUS DO REEMBOLSO =====
Status: {description}
Tentativa realizada: {'Sim' if order.get('adjustment_attempted', False) else 'Não'}
Sucesso: {'Sim' if order.get('adjustment_success', False) else 'Não'}"""

    # Add refund amount if available
    if 'refund_amount' in order:
        content += f"\nValor do reembolso: {order['refund_amount']}"
    
    # Add attempts and error info
    content += f"""
Tentativas: {order.get('attempts', 0)}/5
Último erro: {order.get('last_error', 'Nenhum')}
"""

    # Write to file
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    logger.info(f"Order details saved to: {filename}")

def validate_date(order_date):
    from datetime import timedelta
    thirty_days_ago = datetime.now() - timedelta(days=30)
    return order_date >= thirty_days_ago

def save_order_data(order):
    from config import Config
    import json
    config = Config()
    try:
        # Remove non-serializable elements
        if 'element' in order:
            del order['element']
        for key in list(order.keys()):
            if "WebElement" in str(type(order[key])):
                del order[key]
        
        # Convert datetime objects to ISO format
        if 'date_obj' in order and order['date_obj']:
            if isinstance(order['date_obj'], datetime):
                order['date_obj'] = order['date_obj'].isoformat()
        
        orders = []
        if os.path.exists(config.ORDERS_FILE):
            try:
                with open(config.ORDERS_FILE, 'r') as f:
                    orders = json.load(f)
            except json.JSONDecodeError:
                orders = []
        
        # Update existing order or add new
        existing = next((o for o in orders if o['id'] == order['id']), None)
        if existing:
            existing.update(order)
        else:
            orders.append(order)
            
        with open(config.ORDERS_FILE, 'w') as f:
            json.dump(orders, f, indent=2, default=str)
        return True
    except Exception as e:
        logger.error(f"Error saving order data: {str(e)}")
        return False

def parse_delivery_date(delivery_text):
    try:
        month_names = {
            'Jan': 'January', 'Feb': 'February', 'Mar': 'March',
            'Apr': 'April', 'May': 'May', 'Jun': 'June',
            'Jul': 'July', 'Aug': 'August', 'Sep': 'September',
            'Oct': 'October', 'Nov': 'November', 'Dec': 'December'
        }
        
        # Match different date formats
        patterns = [
            r'(\w{3} \d{1,2}-\d{1,2})',
            r'(\d{1,2}-\d{1,2} \w{3})',
            r'(\d{1,2} \w{3} - \d{1,2} \w{3})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, delivery_text)
            if match:
                date_range = match.group(1)
                if '-' in date_range:
                    parts = date_range.split(' ')
                    if len(parts) == 2:  # "MMM dd-dd"
                        month, days = parts
                        start_day, end_day = days.split('-')
                        return f"{start_day} to {end_day} {month_names.get(month, month)}"
                    else:  # "dd-dd MMM"
                        days, month = date_range.split(' ')
                        start_day, end_day = days.split('-')
                        return f"{start_day} to {end_day} {month_names.get(month, month)}"
                elif ' - ' in date_range:  # "dd MMM - dd MMM"
                    start, end = date_range.split(' - ')
                    start_parts = start.split(' ')
                    end_parts = end.split(' ')
                    return f"{start_parts[0]} to {end_parts[0]} {month_names.get(start_parts[1], start_parts[1])}"
        
        return delivery_text
    except Exception as e:
        logger.warning(f"Error parsing delivery date: {str(e)}")
        return delivery_text