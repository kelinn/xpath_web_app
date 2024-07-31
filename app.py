import pandas as pd
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
import json
import openai
import threading
import time
from flask_cors import CORS
import logging
import os

app = Flask(__name__)
CORS(app)
app.secret_key = 'your_secret_key'

# OpenAI API key setup
openai.api_key = 'you_api_key'

# Dictionary to store element data
element_data = []
driver = None

# Configure logging
logging.basicConfig(level=logging.DEBUG)

def open_browser(url, browser):
    global driver
    if browser == 'chrome':
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()))
    elif browser == 'firefox':
        driver = webdriver.Firefox(service=FirefoxService(GeckoDriverManager().install()))
    
    driver.get(url)
    driver.maximize_window()
    
    # Inject JavaScript to capture click events and monitor URL changes
    script = """
    (function() {
        var currentURL = location.href;
        
        function injectClickListener() {
            document.addEventListener('click', function(event) {
                event.preventDefault();
                setTimeout(function() {
                    var element = event.target;
                    var description = prompt('Enter a description for the element:', element.innerText);
                    if (description !== null) {
                        var elementData = {
                            description: description,
                            tag: element.tagName,
                            id: element.id,
                            class: element.className,
                            name: element.name,
                            href: element.href
                        };

                        fetch('http://127.0.0.1:5000/capture_click', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify(elementData)
                        })
                        .then(response => {
                            if (!response.ok) {
                                throw new Error('Network response was not ok');
                            }
                            return response.json();
                        })
                        .then(data => {
                            if (data.status === 'success') {
                                console.log('Element data captured successfully');
                            } else {
                                console.error('Error capturing element data:', data.message);
                            }
                        })
                        .catch(error => console.error('Error:', error));
                    }
                }, 100); // Adding a delay to ensure prompt window is displayed
            });
        }

        function monitorURLChanges() {
            setInterval(function() {
                if (currentURL !== location.href) {
                    currentURL = location.href;
                    injectClickListener();
                }
            }, 1000); // Check for URL changes every second
        }

        injectClickListener();
        monitorURLChanges();
    })();
    """
    driver.execute_script(script)

    # Keep the browser open
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
        global element_data
        data = request.json
        logging.debug(f"Captured data: {data}")
        element_data.append(data)
        return jsonify({'status': 'success'})
    except Exception as e:
        logging.error(f"Error capturing click: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/save_report', methods=['POST'])
def save_report():
    try:
        global element_data
        report = []
        for element in element_data:
            logging.debug(f"Processing element: {element}")
            xpath = generate_xpath_with_openai(element)
            if not xpath:
                logging.error(f"Failed to generate XPath for element: {element}")
                continue
            report.append({
                'Description': element.get('description', ''),
                'ID': element.get('id'),
                'Name': element.get('name'),
                'Class': element.get('class'),
                'Href': element.get('href'),
                'CSS Selector': generate_css_selector(element),
                'Generated XPath': xpath
            })
        app.config['report'] = report
        logging.debug(f"Generated report: {report}")
        return jsonify({'status': 'success'})
    except Exception as e:
        logging.error(f"Error saving report: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/result')
def result():
    report = app.config.get('report', [])
    return render_template('result.html', report=report, enumerate=enumerate)

@app.route('/clear_data')
def clear_data():
    global element_data
    element_data = []
    app.config['report'] = []
    return redirect(url_for('index'))

@app.route('/download_csv')
def download_csv():
    report = app.config.get('report', [])
    if not report:
        return redirect(url_for('result'))

    df = pd.DataFrame(report)
    csv_file_path = 'static/xpath_report.csv'
    df.to_csv(csv_file_path, index=False)

    return send_file(csv_file_path, as_attachment=True, download_name='xpath_report.csv')

@app.route('/remove_row/<int:index>', methods=['DELETE'])
def remove_row(index):
    try:
        report = app.config.get('report', [])
        if 0 <= index < len(report):
            del report[index]
            app.config['report'] = report
            return jsonify({'status': 'success'})
        else:
            return jsonify({'status': 'error', 'message': 'Index out of range'}), 400
    except Exception as e:
        logging.error(f"Error removing row: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/update_field/<int:index>/<field>', methods=['PUT'])
def update_field(index, field):
    try:
        report = app.config.get('report', [])
        if 0 <= index < len(report) and field in report[index]:
            value = request.json.get('value')
            report[index][field] = value
            app.config['report'] = report
            return jsonify({'status': 'success'})
        else:
            return jsonify({'status': 'error', 'message': 'Index or field not found'}), 400
    except Exception as e:
        logging.error(f"Error updating field: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

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
        
        xpath = response['choices'][0]['message']['content'].strip()
        logging.debug(f"Generated XPath: {xpath} for element: {element}")
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
