# Temu Price Adjustment Bot 🤖

> Automated solution for requesting price adjustments on Temu orders

## Overview 💡
This Python bot automates the process of requesting price adjustments for orders on Temu. It navigates through your order history, identifies eligible purchases, and systematically requests refunds when prices drop within Temu's 30-day adjustment policy.

## Key Features ✨

- **Automated Login**: Handles session management with cookie persistence
- **CAPTCHA Solving**: Integrates with external services or manual intervention
- **Smart Scheduling**: Uses ML to determine optimal run times
- **Order Processing**: 
  - Identifies eligible orders (within 30 days)
  - Extracts order details and tracking information
  - Automates refund requests
- **Comprehensive Logging**: Color-coded console output and file logging
- **Error Handling**: Automatic retries and page source saving for debugging

## Project Structure 🗂️

```bash
temu-price-bot/
├── captcha_solver.py    # CAPTCHA solving functionality
├── config.py            # Environment configuration loader
├── logger.py            # Custom logging setup with colors
├── main.py              # Main bot execution logic
├── scheduler.py         # Run scheduling with ML optimization
└── utils.py             # Helper functions and utilities
```

## Installation ⚙️

1. **Clone repository**:
```bash
git clone https://github.com/yourusername/temu-price-bot.git
cd temu-price-bot
```

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

3. **Set up environment variables**:
Create `.env` file with:
```env
TEMU_EMAIL=your@email.com
TEMU_PASSWORD=yourpassword
CAPTCHA_API_KEY=your_captcha_service_key
```

## Configuration ⚙️

Customize these options in `config.py`:
```python
class Config:
    SESSION_FILE = "session.json"       # Browser session storage
    ORDERS_FILE = "orders.json"         # Order data storage
    LOG_FILE = "temu_bot.log"           # Log file path
    ML_MODEL_PATH = "success_model.pkl" # ML model path
    ORDERS_FOLDER = "orders"            # Output folder for order reports
```

## Usage 🚀

Run with options:
```bash
python main.py [options]
```

### Command Options:
| Option        | Description                          |
|---------------|--------------------------------------|
| `--now`       | Run immediately                      |
| `--schedule`  | Enable scheduled runs                |
| `--verbose`   | Enable detailed logging              |
| `--headless`  | Run browser in headless mode         |

### Sample Output:
```
15.07.2025 - 14:22:15 - INFO - Found 12 orders in total
15.07.2025 - 14:22:18 - SUCCESS - Price adjustment SUCCESS for order PO-123456
15.07.2025 - 14:25:31 - INFO - Next scheduled run at: 16/07/2025 - 09:15:22
```

## Customization 🛠️

1. **Adjustment Logic**: Modify `attempt_price_adjustment()` in `main.py` for different e-commerce platforms
2. **Delay Times**: Tune in `utils.py`:
   ```python
   SHORT_DELAY = (0.5, 5.0)   # Min/max seconds for short delays
   LONG_DELAY = (10.0, 60.0)  # Min/max seconds for long delays
   ```
3. **Logging**: Customize log levels and colors in `logger.py`

## License 📄
This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

```
MIT License

Copyright (c) 2025 Your Name

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Contribution 🤝
Contributions are welcome! Please follow these steps:
1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a pull request

## Disclaimer ⚠️
This bot is for educational purposes only. Use responsibly and comply with Temu's Terms of Service. The developers are not responsible for any account restrictions resulting from bot usage.
