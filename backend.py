# Essential libraries that make up the backend of the backend
from flask import Flask, render_template, session, redirect, url_for, request, flash
import sqlite3
import webview
from threading import Thread, Event
import threading
import os

# Very useful libraries for the little features of the app
from PIL import Image
import datetime
import sys
import random

# Libraries for sending emails
import smtplib
from email.mime.text import MIMEText

# Libraries to improve the overall secureness of the app
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# Web scraper libraries
from invisible_playwright import InvisiblePlaywright, cli as ip_cli





# This function helps the .exe find the files needed for the app while it runs
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS # Temporary extraction folder created by the .exe on every startup
    except AttributeError:
        base_path = os.path.abspath(".") # File path falls back to normal when .py is run during dev
    return os.path.join(base_path, relative_path) # Ends up joining the relative path to the base path whether the .py was run or the .exe was run


# Set important global variables
load_dotenv(resource_path('.env')) # Connect to the .env file with all the important secret values
running_agents = {} # A dict that stores the states of each threaded agent and is used to stop threaded agents
playwright_lock = threading.Lock() # Helps prevent agent create from failing if there is a automated scrape running at the moment of creation
loadStatus = {}


app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(24)


# This function checks and handles the installation of the invisible palywright on another users device because pyinstaller does not package it with the .exe
def ensure_engine_available():
    try: # Check if the browser ius installed and works
        with InvisiblePlaywright() as browser:
            browser.close()
        return True
    except Exception: # Install invisible playwright
        print("First run: downloading scraper engine, this may take a minute...")
        try:
            ip_cli.main(['fetch'])  # verify this matches the actual entry point in cli.py
            return True
        except Exception as e:
            print(f"Engine download failed: {e}")
            return False


if getattr(sys, 'frozen', False):
    app_dir = os.path.dirname(sys.executable)
else:
    app_dir = os.path.abspath(".")
DB_PATH = os.path.join(app_dir, 'database.db')


# The all in one database access/control function that will handle all the web apps database needs
def db(query, params=()):
    # Create the connection to the database file
    conn = sqlite3.connect(DB_PATH)
    # Create the cursor which will handle queries
    cursor = conn.cursor()
    # Execute the query and use the parameters
    cursor.execute(query, params)
    # Always commit changes even if there are not any
    conn.commit()
    # Store the data that was fetched from the database as 'results'
    results = cursor.fetchall()
    # Always close connection when done with the function
    conn.close()
    # Return the data
    return results


# The function that verifies that users are actually logged in and not able to visit each page via their route
def login_required(f): # f is the route function such as home or configuration
    @wraps(f)
    def decorated_function(*args, **kwargs): # Function when a user visits any of the routes and can pass on the arguments from any previous routes that call the other route
        if 'userID' not in session: # Check if the user is actually logged in
            flash('Please log in to continue.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


@app.errorhandler(404) # Handler for flask page not found errors
def page_not_found(e):
    return render_template('404.html'), 404


def error(errorMessage): # Error page handler
    return render_template('error.html', errorMessage=errorMessage)


def get_selector_text(page, selector):
    """Return the visible text for a selector and raise a clear error if it is missing."""
    locator = page.locator(selector)
    try:
        if locator.count() == 0:
            raise ValueError(f"No element matched selector: {selector}")
        text = locator.first.text_content(timeout=10000)
        return text.strip() if text else ""
    except Exception as exc:
        raise RuntimeError(f"Could not read text from selector '{selector}': {exc}") from exc


@app.route('/')
def index():
    session.clear()
    return redirect(url_for('login'))

@app.route('/loadCheck')
def loadCheck():
    loadID = session.get('loadID')
    nextPage = session.get('nextPage')
    if loadStatus.get(loadID) == 'error':
        flash('An error occured while trying to perform the most recent requested action.')
        return redirect(url_for('home'))
    if loadStatus.get(loadID) is True:
        return redirect(url_for(nextPage))
    else:
        return render_template('loadingPage.html')  # keep waiting, page refreshes itself again


# Must use 'POST' and 'GET' because 'GET' is required for the url redirection from index to login
@app.route('/login', methods=['GET', 'POST'])
def login():
    try:
        if request.method == 'POST':
            # Fetch the data from the form and add it to session variables
            usernameInput = request.form['username']
            passwordInput = request.form['password']
            # Check if the user credentials are in the database
            userData = db("""SELECT * FROM user WHERE userName = ?;""", (usernameInput,))
            if not userData or not check_password_hash(userData[0][2], passwordInput):
                flash('Credentials are incorrect')
                return render_template('login.html')
            else:
                # If the user credentials are correct then redirect the user to home
                session['userID'] = userData[0][0]
                userID = userData[0][0]
                session['nextPage'] = 'home'
                loadStatus[userID] = False
                session['loadID'] = random.randint(1, 100)
                loadID = session['loadID']

                def loading(userID, loadID):
                    try:
                        userAgents = db("""SELECT scraperID, scrapeInterval FROM scraperAgent WHERE userID = ?;""", (userID,))
                        for i in userAgents: # Go through the list of scraper agents and start a thread for each scraper agent to run in the background
                            automation_Thread(i[1], i[0], userID)
                        loadStatus[loadID] = True
                    except:
                        loadStatus[loadID] = 'error'
                Thread(target=loading, args=(userID, loadID,), daemon=True).start()
                return render_template('loadingPage.html')
        return render_template('login.html')
    except Exception as e:
        return error(e)


@app.route('/accountCreate', methods=['POST', 'GET']) # Account creation
def accountCreate():
    try:
        if request.method == 'POST':
            # Get the credentials the the user input from the form
            usernameInput = request.form['username']
            passwordInput = request.form['password']
            emailInput = request.form['email']
            
            # Check the length of the username and password
            if 3 < len(usernameInput) < 20 and 3 < len(passwordInput) < 20:
                # Check if the username or email is already in the database
                # If the username or email is not in the database then add the user credentials
                if not db("""SELECT * FROM user WHERE userName = ?;""", (usernameInput,)):
                    if not db("""SELECT * FROM user WHERE userEmail = ?;""", (emailInput,)):
                        session['loadID'] = random.randint(1, 100)
                        loadID = session['loadID']
                        loadStatus[loadID] = False
                        session['nextPage'] = 'login'

                        def loading(usernameInput, passwordInput, emailInput, loadID):
                            hashedPassword = generate_password_hash(passwordInput) # Generate a password hash to keep the users password is secure
                            db("INSERT INTO user (userName, userPassword, userEmail) VALUES (?, ?, ?);", (usernameInput, hashedPassword, emailInput))
                            loadStatus[loadID] = True

                        Thread(target=loading, args=(usernameInput, passwordInput, emailInput, loadID,), daemon=True).start()
                        return render_template('loadingPage.html')
                    else:
                        flash('That email is already in use.')
                        return render_template('accountCreate.html', name=usernameInput, password=passwordInput)
                else:
                    flash('That username is already in use.')
                    return render_template('accountCreate.html', password=passwordInput, email=emailInput)
            else:
                flash('The username or password is not long enough. (3 to 20 characters!!!)')
        return render_template('accountCreate.html')
    except Exception as e:
        return error(e)


@app.route('/home')
@login_required
def home():
    try:
        scraperAgents = db("""SELECT scraperName FROM scraperAgent WHERE userID = ?;""", (session['userID'], ))
        return render_template('home.html', agents=[row[0] for row in scraperAgents])
    except Exception as e:
        return error(e)


@app.route('/agentSelect', methods=['POST', 'GET']) # get the name of the agent that was selected and pass it on to the agent config function
@login_required
def agentSelect():
    try:
        if request.method == 'POST':
            agentName = request.form['agentName']
            agent = db("""SELECT scraperID FROM scraperAgent WHERE userID = ? AND scraperName = ?;""", (session['userID'], agentName,))
            session['scraperID'] = agent[0][0]
        return redirect(url_for('agentConfig'))
    except Exception as e:
        return error(e)


@app.route('/agentDelete', methods=['POST', 'GET'])
@login_required
def agentDelete():
    try:
        if request.method == 'POST':
            db("""DELETE FROM scrapeData WHERE scraperID =?;""", (session['scraperID'],))
            db("""DELETE FROM scraperAgent WHERE scraperID = ?;""", (session['scraperID'],))
            stop_event = running_agents.get(session['scraperID'])
            if stop_event:
                stop_event.set()
            return redirect(url_for('home'))
    except Exception as e:
        return error(e)

@app.route('/userDelete', methods=['POST', 'GET'])
@login_required
def userDelete():
    try:
        if request.method == 'POST':
            userAgentIDs = db("""SELECT scraperID FROM scraperAgent WHERE userID = ?;""", (session['userID'],))
            for row in userAgentIDs:
                stop_event = running_agents.get(row[0])
                if stop_event:
                    stop_event.set()

            db("""DELETE FROM scrapeData WHERE userID = ?;""", (session['userID'],))
            db("""DELETE FROM scraperAgent WHERE userID = ?;""", (session['userID'],))
            db("""DELETE FROM user WHERE userID = ?;""", (session['userID'],))
            return redirect(url_for('index'))
    except Exception as e:
        return error(e)

@app.route('/agentConfig', methods=['POST', 'GET']) # Function to configure a scraper agent
@login_required
def agentConfig():
    try:
        agentDetails = db("""SELECT scraperName, webPageURL, elementSelector, scrapeInterval FROM scraperAgent WHERE scraperID = ?;""", (session['scraperID'],))
        name, link, selector, interval = agentDetails[0]
        if request.method == 'POST':
            scraperID = session['scraperID']
            newAgent_name = request.form['newAgent-name']
            newAgent_link = request.form['newAgent-link']
            newAgent_selector = request.form['newAgent-selector']
            scrapeInterval = request.form['scrapeInterval']
            if newAgent_name != name:
                if newAgent_name > 3 and newAgent_name < 20:
                    if not db("""SELECT * FROM scraperAgent WHERE userID = ? AND scraperName = ?;""", (session['userID'], newAgent_name,)):
                        db("""UPDATE scraperAgent SET scraperName WHERE scraperID = ?;""", (scraperID,))
                    else:
                        flash('That scraper name is in use.')
                        return render_template('agentConfig.html', name=name, link=newAgent_link, selector=newAgent_selector, interval=scrapeInterval)
                else:
                    flash('That scraper name is not the correct length, must be 3 to 20 characters long.')
                    return render_template('agentConfig.html', name=name, link=newAgent_link, selector=newAgent_selector, interval=scrapeInterval)

            if scrapeInterval != interval:
                db("""UPDATE scraperAgent SET scrapeInterval = ? WHERE scraperID = ?;""", (scrapeInterval, scraperID,))
            if newAgent_link != link or newAgent_selector != selector:
                if not db("""SELECT * FROM scraperAgent WHERE userID = ? AND webPageURL = ? AND elementSelector = ?;""", (session['userID'], newAgent_link, newAgent_selector,)):
                    session['loadID'] = random.randint(1, 100)
                    loadID = session['loadID']
                    loadStatus[loadID] = False
                    session['nextPage'] = 'home'
                    def loading(loadID, newAgent_link, newAgent_selector, scraperID,):
                        with playwright_lock:
                            with InvisiblePlaywright(headless=True) as browser:
                                try:
                                    page = browser.new_page()
                                    page.goto(newAgent_link)
                                    page.screenshot(path="tmpImg.png")
                                    img = Image.open("tmpImg.png")
                                    img.show()
                                    # Delete the screenshot
                                    os.remove("tmpImg.png")              
                                    page.wait_for_selector(f"{newAgent_selector}", timeout=10000)
                                    # Give the screen shot a temporary name, will delete after the image is opened
                                    price_text = get_selector_text(page, newAgent_selector)
                                    print(f"Current price: {price_text}")
                                    browser.close()
                                    db("""UPDATE scraperAgent SET webPageURL = ?, elementSelector = ? WHERE scraperID = ?;""", (newAgent_link, newAgent_selector, scraperID,))
                                    loadStatus[loadID] = True
                                except:
                                    loadStatus[loadID] = 'error'
                    Thread(target=loading, args=(loadID, newAgent_link, newAgent_selector, scraperID), daemon=True).start()
                    return render_template('loadingPage.html')
                else:
                    flash('You are already monitoring that webpage element.')
                    return render_template('agentConfig.html', name=newAgent_name, link=link, selector=selector, interval=scrapeInterval)
            return redirect(url_for('home'))
        return render_template('agentConfig.html', name=name, link=link, selector=selector, interval=interval)
    except Exception as e:
        return error(e)


@app.route('/agentCreate', methods=['POST', 'GET'])
@login_required
def agentCreate():
    try:
        if request.method == 'POST':
            agentName_input = request.form['agentName']
            webpageLink_input = request.form['webpageLink']
            elementSelector_input = request.form['elementSelector']
            scrapeInterval = request.form['scrapeInterval']
            if not db("""SELECT * FROM scraperAgent WHERE userID = ? AND scraperName = ?;""", (session['userID'], agentName_input,)):
                if not db("""SELECT * FROM scraperAgent WHERE userID = ? AND webPageURL = ? AND elementSelector = ?;""", (session['userID'], webpageLink_input, elementSelector_input,)):
                    session['loadID'] = random.randint(1, 100)
                    loadID = session['loadID']
                    loadStatus[loadID] = False
                    session['nextPage'] = 'home'
                    userID = session['userID']
                    def loading(loadID, userID, agentName_input, webpageLink_input, elementSelector_input, scrapeInterval):
                        with playwright_lock:
                            with InvisiblePlaywright(headless=True) as browser:
                                try:
                                    page = browser.new_page()
                                    page.goto(webpageLink_input)                
                                    page.wait_for_selector(f"{elementSelector_input}", timeout=10000)
                                    # Give the screen shot a temporary name, will delete after the image is opened
                                    page.screenshot(path="tmpImg.png")
                                    price_text = get_selector_text(page, elementSelector_input)
                                    print(f"Current price: {price_text}")
                                    browser.close()
                                    img = Image.open("tmpImg.png")
                                    img.show()
                                    # Delete the screenshot
                                    os.remove("tmpImg.png")
                                    db("""INSERT INTO scraperAgent (userID, scraperName, webPageURL, elementSelector, scrapeInterval) VALUES (?, ?, ?, ?, ?);""", (userID, agentName_input, webpageLink_input, elementSelector_input, scrapeInterval))
                                    agentID = db("""SELECT scraperID FROM scraperAgent WHERE userID = ? AND scraperName = ?;""", (userID, agentName_input))
                                    agentID = agentID[0][0]
                                    db("""INSERT INTO scrapeData (userID, scraperID, scrapeValue, scrapeTime, elementSelector) VALUES (?, ?, ?, ?, ?);""", (userID, agentID, price_text, datetime.datetime.now(), elementSelector_input))
                                    automation_Thread(scrapeInterval, agentID, userID)
                                    loadStatus[loadID] = True
                                except:
                                    loadStatus[loadID] = 'error'
                    Thread(target=loading, args=(loadID, userID, agentName_input, webpageLink_input, elementSelector_input, scrapeInterval), daemon=True).start()
                    return render_template('loadingPage.html')

                else:
                    flash("That webpage element is already being monitored.")
                    return render_template('agentCreate.html', name=agentName_input, link=webpageLink_input, interval=scrapeInterval)
            else:
                flash("That scraper agent name is already in use.")
                return render_template('agentCreate.html', link=webpageLink_input, selector=elementSelector_input, interval=scrapeInterval)
        return render_template('agentCreate.html')
    except Exception as e:
        return error(e)


@app.route('/configure', methods=['POST', 'GET'])
@login_required
def configure():
    try:
        userDetails = db("""SELECT userName, userEmail FROM user WHERE userID = ?;""", (session['userID'],))
        name, email = userDetails[0]
        if request.method == 'POST':
            newUsername = request.form['newUsername']
            newPassword = request.form['newPassword']
            newEmail = request.form['newEmail']
            try:
                if newUsername != name:
                    if not db("""SELECT * FROM user WHERE userName = ?;""", (newUsername,)):
                        db("""UPDATE user SET userName = ? WHERE userID = ?;""", (newUsername, session['userID']))
                    else:
                        flash('That username is unavailable.')
                        return render_template('configuration.html', name=name, email=newEmail)
                if newPassword:
                    hashedPassword = generate_password_hash(newPassword)
                    db("""UPDATE user SET userPassword = ? WHERE userID = ?;""", (hashedPassword, session['userID']))
                if newEmail != email:
                    if not db("""SELECT * FROM user WHERE userEmail = ?;""", (newEmail,)):
                        db("""UPDATE user SET userEmail = ? WHERE userID = ?;""", (newEmail, session['userID']))
                    else:
                        flash('That email is unavailable.')
                        return render_template('configuration.html', name=newUsername, email=email)
                return redirect(url_for('home'))
            except Exception as e:
                print(e)
        return render_template('configuration.html', name=name, email=email)
    except Exception as e:
        return error(e)


def automation_Thread(interval, agentID, userID):
    try:
        if agentID in running_agents:
            return  # already running, don't start a duplicate
        stop_event = Event()
        running_agents[agentID] = stop_event
        task = Thread(target=automation_Time, args=(interval, agentID, userID, stop_event), daemon=True)
        task.start()
    except Exception as e:
        return error(e)

def automation_Time(interval, agentID, userID, stop_event):
    try:
        agentData = db("""SELECT webPageURL, elementSelector FROM scraperAgent WHERE scraperID = ?;""", (agentID,))
        if not agentData:
            # Agent was deleted before this thread even got its first data — bail out cleanly
            running_agents.pop(agentID, None)
            return
        link, selector = agentData[0]
        hours = int(interval) * 3600  # Multiply the uscraper agent's set interval by 3600 seconds (1 hour)

        while not stop_event.is_set():
            scrapeValue = automation_Scrape(link, selector)
            prevVal = db("""SELECT scrapeValue FROM scrapeData WHERE scraperID = ? ORDER BY scrapeID DESC LIMIT 1;""", (agentID,))
            db("""INSERT INTO scrapeData (userID, scraperID, scrapeTime, scrapeValue, elementSelector) VALUES (?, ?, ?, ?, ?);""", (userID, agentID, datetime.datetime.now(), scrapeValue, selector,))
            if prevVal:  # guard against the very first scrape, where prevVal is empty
                automation_Email(prevVal[0][0], scrapeValue, agentID, userID)

            # stop_event.wait() sleeps for `hours` seconds, but returns immediately (True) if the event gets set,
            # instead of time.sleep() which would block the full duration regardless
            stop_event.wait(hours)

        running_agents.pop(agentID, None)  # clean up once the loop actually exits
    except Exception as e:
        return error(e)

def automation_Scrape(link, selector):
    try:
        with playwright_lock:
            with InvisiblePlaywright(headless=True) as browser:
                try:
                    page = browser.new_page()
                    page.goto(link)
                    try:
                        page.wait_for_selector(f"{selector}", timeout=10000)
                    except Exception as wait_err:
                        print(f"Selector not found: {wait_err}")
                    price_text = get_selector_text(page, selector)
                    browser.close()
                    return(price_text)
                except Exception as e:
                    return str(e)
    except Exception as e:
        return error(e)


def automation_Email(prevVal, curVal, agentID, userID):
    try:
        if curVal != prevVal: # Check if there is a difference between the previous and current values.
            userDetails = db("""SELECT userName, userEmail FROM user WHERE userID = ?;""", (userID,))
            username, email = userDetails[0]
            agentDetails = db("""SELECT scraperName, webPageURL FROM scraperAgent WHERE scraperID = ?;""", (agentID,))
            agentName, scrapeLink = agentDetails[0]

            # Email account credentials
            SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
            APP_PASSWORD = os.environ.get("APP_PASSWORD")  # Generated from Google Account > Security > App passwords
            RECEIVER_EMAIL = email

            # Email content
            subject = f"Agent-{agentName} detected a change"
            body = (
                f"Hello {username}, \n\n"
                f"Agent-{agentName} detected a change from {scrapeLink}.\n\n"
                f"Previous value = {prevVal}.\n"
                f"Current value = {curVal}.\n"
            )

            # Create MIMEText object
            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = SENDER_EMAIL
            msg["To"] = RECEIVER_EMAIL

            try:
                # Connect to Gmail's SMTP server
                with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                    server.login(SENDER_EMAIL, APP_PASSWORD)
                    server.send_message(msg)
                print("Email sent successfully!")
            except Exception as e:
                print(f"Error: {e}")
    except Exception as e:
        return error(e)
        

def run_flask():
    app.run(port=8000)


if __name__ == '__main__':
    # Create the variable 't' so the flask app runs on a seperate thread
    t = Thread(target=run_flask)
    # Set 't.daemon' to true so that when the webview window is closed then the flask app is ended too
    t.daemon = True
    # Start the flask app in the background and then the code beneath this can run at the same time
    t.start()

    # Define the webview configuration
    window = webview.create_window(
        'Bit Scrape',
        'http://127.0.0.1:8000',
        # Set the fixed size for the application window
        width=400,
        height=580,
        # Set resizable to false so that the window can not be resized at all
        resizable=False
    )
    webview.start(icon=resource_path('static/images/BitScrapeLogo.ico'), gui='edgechromium')
    # Start the application window