from flask import Flask, render_template, request, jsonify, redirect, url_for
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
import json
import openai
import threading
import time
import requests

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# OpenAI API key setup
openai.api_key = 'your_key_here'

# Dictionary to store element data
element_data = []
driver = None

def open_browser(url, browser):
    global driver
    if browser == 'chrome':
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()))
    elif browser == 'firefox':
        driver = webdriver.Firefox(service=FirefoxService(GeckoDriverManager().install()))
    
    driver.get(url)
    driver.maximize_window()

    def capture_click(event):
        element = driver.execute_script("return document.elementFromPoint(arguments[0], arguments[1])", event['x'], event['y'])
        element_info = {
            'tag': element.tag_name,
            'id': element.get_attribute('id'),
            'class': element.get_attribute('class'),
            'name': element.get_attribute('name'),
            'href': element.get_attribute('href')
        }
        element_data.append(element_info)
        print(f"Element clicked: {element_info}")

    driver.execute_cdp_cmd('Runtime.enable', {})
    driver.execute_cdp_cmd('Page.enable', {})
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': """
            document.addEventListener('click', (event) => {
                fetch('http://127.0.0.1:5000/capture_click', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ x: event.clientX, y: event.clientY })
                });
            });
        """
    })
    
    while True:
        time.sleep(1)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        url = request.form['url']
        browser = request.form['browser']
        thread = threading.Thread(target=open_browser, args=(url, browser))
        thread.start()
        time.sleep(5)
        return render_template('select_elements.html')
    return render_template('index.html')

@app.route('/capture_click', methods=['POST'])
def capture_click():
    try:
        global driver
        event = request.json
        element = driver.execute_script("return document.elementFromPoint(arguments[0], arguments[1])", event['x'], event['y'])
        element_info = {
            'tag': element.tag_name,
            'id': element.get_attribute('id'),
            'class': element.get_attribute('class'),
            'name': element.get_attribute('name'),
            'href': element.get_attribute('href')
        }
        element_data.append(element_info)
        print(f"Element clicked: {element_info}")
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/save_report', methods=['POST'])
def save_report():
    try:
        global element_data
        report = []
        for element in element_data:
            xpath = generate_xpath_with_openai(element)
            report.append({
                'ID': element.get('id'),
                'Name': element.get('name'),
                'Class': element.get('class'),
                'Href': element.get('href'),
                'CSS Selector': generate_css_selector(element),
                'Generated XPath': xpath
            })
        app.config['report'] = report
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/result')
def result():
    report = app.config.get('report', [])
    return render_template('result.html', report=report)

def generate_xpath_with_openai(element):
    messages = [
        {"role": "system", "content": "You are an assistant that generates XPath expressions based on descriptions."},
        {"role": "user", "content": f"Generate an XPath for the following HTML element: {json.dumps(element)}"}
    ]
    
    try:
        response = openai.ChatCompletion.create(
          model="gpt-3.5-turbo-0125",
          messages=messages
      )
        logging.info(f"OpenAI API response: {response}")
        xpath = response['choices'][0]['message']['content'].strip()
        return xpath
    except Exception as e:
        logging.error(f"Error generating XPath with OpenAI: {e}")
        raise

def generate_css_selector(element):
    css_selector = element.get('id', '')
    if css_selector:
        return f"#{css_selector}"
    css_selector = element.get('class', '').replace(' ', '.')
    if css_selector:
        return f".{css_selector}"
    return element.get('tag', '').lower()

if __name__ == '__main__':
    app.run(debug=True)
