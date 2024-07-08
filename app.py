import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import openai
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for
from flask_bootstrap import Bootstrap

# Initialize Flask app
app = Flask(__name__)
Bootstrap(app)

# Initialize OpenAI
openai.api_key = 'YOUR KEY'

# Initialize Selenium WebDriver
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))

def scrape_webpage(url):
    response = requests.get(url)
    if response.status_code == 200:
        page_content = response.content
        soup = BeautifulSoup(page_content, 'html.parser')
        return soup
    else:
        return None

def get_element_structure(soup):
    elements = soup.find_all()
    structure = [{'tag': el.name, 'attrs': el.attrs} for el in elements]
    return structure

def generate_xpath(description):
    messages = [
        {"role": "system", "content": "You are an assistant that generates XPath expressions based on descriptions."},
        {"role": "user", "content": f"Generate an XPath expression for an element described as: {description}"}
    ]

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=messages
    )
    xpath = response['choices'][0]['message']['content'].strip()
    return xpath

def validate_xpath(url, xpath):
    driver.get(url)
    try:
        element = driver.find_element(By.XPATH, xpath)
        return True if element else False
    except Exception:
        return False

def get_absolute_xpath(element):
    return driver.execute_script("""
        function absoluteXPath(element) {
            var comp, comps = [];
            var parent = null;
            var xpath = '';
            var getPos = function(element) {
                var position = 1, curNode;
                if (element.nodeType == Node.ATTRIBUTE_NODE) {
                    return null;
                }
                for (curNode = element.previousSibling; curNode; curNode = curNode.previousSibling) {
                    if (curNode.nodeName == element.nodeName) {
                        ++position;
                    }
                }
                return position;
            };

            if (element instanceof Document) {
                return '/';
            }

            for (; element && !(element instanceof Document); element = element.nodeType == Node.ATTRIBUTE_NODE ? element.ownerElement : element.parentNode) {
                comp = comps[comps.length] = {};
                switch (element.nodeType) {
                    case Node.TEXT_NODE:
                        comp.name = 'text()';
                        break;
                    case Node.ATTRIBUTE_NODE:
                        comp.name = '@' + element.nodeName;
                        break;
                    case Node.PROCESSING_INSTRUCTION_NODE:
                        comp.name = 'processing-instruction()';
                        break;
                    case Node.COMMENT_NODE:
                        comp.name = 'comment()';
                        break;
                    case Node.ELEMENT_NODE:
                        comp.name = element.nodeName;
                        break;
                }
                comp.position = getPos(element);
            }

            for (var i = comps.length - 1; i >= 0; i--) {
                comp = comps[i];
                xpath += '/' + comp.name.toLowerCase();
                if (comp.position !== null) {
                    xpath += '[' + comp.position + ']';
                }
            }

            return xpath;
        }

        return absoluteXPath(arguments[0]);
    """, element)

def find_elements_by_xpath(url, description):
    driver.get(url)
    generated_xpath = generate_xpath(description)
    elements = driver.find_elements(By.XPATH, generated_xpath)
    absolute_xpaths = [get_absolute_xpath(element) for element in elements]
    return generated_xpath, absolute_xpaths

def generate_report(description, generated_xpath, validation_result, absolute_xpaths, structure ):
    report = {
        'description': description,
        'generated_xpath': generated_xpath,
        'validation_result': validation_result,
        'absolute_xpaths': absolute_xpaths,
        'webpage_structure': structure
        
    }
    df = pd.DataFrame([report])
    df.to_csv('static/xpath_report.csv', index=False)
    return df

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        url = request.form['url']
        description = request.form['description']

        # Scrape webpage and get structure
        soup = scrape_webpage(url)
        if not soup:
            return render_template('index.html', error="Failed to scrape the webpage. Please check the URL and try again.")

        structure = get_element_structure(soup)

        # Generate XPath and find elements
        generated_xpath, absolute_xpaths = find_elements_by_xpath(url, description)

        # Validate XPath
        validation_result = validate_xpath(url, generated_xpath)

        # Generate Report
        generate_report(description, generated_xpath, validation_result, absolute_xpaths, structure )

        return redirect(url_for('result', description=description, generated_xpath=generated_xpath, validation_result=validation_result,xpaths=absolute_xpaths))

    return render_template('index.html')

@app.route('/result')
def result():
    description = request.args.get('description')
    generated_xpath = request.args.get('generated_xpath')
    validation_result = request.args.get('validation_result')
    xpaths = request.args.getlist('xpaths')
    return render_template('result.html', description=description, generated_xpath=generated_xpath, validation_result=validation_result, xpaths=xpaths)

if __name__ == "__main__":
    app.run(debug=True)
