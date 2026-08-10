# Essential libraries that make up the backend of the backend
from flask import Flask, render_template, session, redirect, url_for, request, flash
import sqlite3
import webview
from threading import Thread
import os

# Very useful libraries for the little features of the app
from PIL import Image
import datetime
import time

# Libraries for sending emails
import smtplib
from email.mime.text import MIMEText

# Libraries to improve the overall secureness of the app
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# Web scraper libraries
from invisible_playwright import InvisiblePlaywright


load_dotenv()


app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY")


# The all in one database access/control function that will handle all the web apps database needs
def db(query, params=()):
    # Create the connection to the database file
    conn = sqlite3.connect('database.db')
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


def error(errorMessage):
    return render_template('error.html', errorMessage=errorMessage)


@app.route('/')
def index():
    session.clear()
    return redirect(url_for('login'))


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
            else:
                # If the user credentials are correct then redirect the user to home
                session['userID'] = userData[0][0]
                userAgents = db("""SELECT scraperID, scrapeInterval FROM scraperAgent WHERE userID = ?;""", (session['userID'],))
                if userAgents: # Check if the user actuall has any scraper agents
                    for i in userAgents: # Go through the list of scraper agents and start a thread for each scraper agent to run in the background
                        automation_Thread(i[1], i[0], session['userID'])
                return redirect(url_for('home'))
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
            if 5 < len(usernameInput) < 20 and 5 < len(passwordInput) < 20:
                # Check if the username or email is already in the database
                userCheck = db("SELECT * FROM user WHERE userName = ? OR userEmail = ?;", (usernameInput, emailInput))
                # If the username or email is not in the database then add the user credentials
                if not userCheck:
                    hashedPassword = generate_password_hash(passwordInput) # Generate a password hash to keep the users password is secure
                    db("INSERT INTO user (userName, userPassword, userEmail) VALUES (?, ?, ?);", (usernameInput, hashedPassword, emailInput))
                    # Redirect the user to the login page so they can login with their newly created account
                    return redirect(url_for('login'))
                else:
                    flash('That username or email is already being used.')
            else:
                flash('The username of password is not long enough. (5 to 20 characters!!!)')
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


@app.route('/agentSelect', methods=['POST', 'GET'])
@login_required
def agentSelect():
    try:
        if request.method == 'POST':
            agentName = request.form['agentName']
            agent = db("""SELECT scraperID FROM scraperAgent WHERE userID = ? and scraperName = ?;""", (session['userID'], agentName,))
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
        return redirect(url_for('home'))
    except Exception as e:
        return error(e)


@app.route('/userDelete', methods=['POST', 'GET'])
@login_required
def userDelete():
    try:
        if request.method == 'POST':
            db("""DELETE FROM scrapeData WHERE userID = ?;""", (session['userID'],))
            db("""DELETE FROM scraperAgent WHERE userID = ?;""", (session['userID'],))
            db("""DELETE FROM user WHERE userID = ?;""", (session['userID'],))
        return redirect(url_for('index'))
    except Exception as e:
        return error(e)


@app.route('/agentConfig', methods=['POST', 'GET'])
@login_required
def agentConfig():
    try:
        if request.method == 'POST':
            userAgents_names = db("""SELECT scraperName FROM scraperAgent WHERE userID = ?;""", (session['userID'],))
            userAgents_names = [row[0] for row in userAgents_names] # Loops through the tuples and creates a new easy to access list
            scraperID = session['scraperID']
            newAgent_name = request.form['newAgent-name']
            newAgent_link = request.form['newAgent-link']
            newAgent_selector = request.form['newAgent-selector']
            scrapeInterval = request.form['scrapeInterval']
            if newAgent_name:
                if newAgent_name in userAgents_names:
                    flash("You have already used thet scraper agent name!")
                else:
                    db("""UPDATE scraperAgent SET scraperName = ? WHERE scraperID = ?;""", (newAgent_name, scraperID,))
            else:
                print("Scraper Agent name was not changed.")
            if newAgent_link:
                db("""UPDATE scraperAgent SET webPageURL = ? WHERE scraperID = ?;""", (newAgent_link, scraperID,))
            else:
                print("Scraper agent link was not changed.")
            if newAgent_selector:
                db("""UPDATE scraperAgent SET elementSelector = ? WHERE scraperID = ?;""", (newAgent_selector, scraperID,))
            else:
                print("Scraper agent selector was not changed.")
            if scrapeInterval:
                db("""UPDATE scraperAgent SET scrapeInterval = ? WHERE userID = ?;""", (scrapeInterval, session['userID'],))
            return redirect(url_for('home'))
        agentDetails = db("""SELECT scraperName, webPageURL, elementSelector, scrapeInterval FROM scraperAgent WHERE scraperID = ?;""", (session['scraperID'],))
        name, link, selector, interval = agentDetails[0]
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
            with InvisiblePlaywright() as browser:
                try:
                    page = browser.new_page()
                    page.goto(webpageLink_input)                
                    try:
                        page.wait_for_selector(f"{elementSelector_input}", timeout=10000)
                    except Exception as wait_err:
                        print(f"Selector not found: {wait_err}")
                    # Give the screen shot a temporary name, will delete after the image is opened
                    page.screenshot(path="tmpImg.png")
                    price_element = page.locator(f"{elementSelector_input}")
                    price_text = price_element.text_content()
                    print(f"Current price: {price_text}")
                    browser.close()
                    img = Image.open("tmpImg.png")
                    img.show()
                    # Delete the screenshot
                    os.remove("tmpImg.png")
                    if not db("""SELECT * FROM scraperAgent WHERE scraperName = ?;""", (agentName_input, )):
                        db("""INSERT INTO scraperAgent (userID, scraperName, webPageURL, elementSelector, scrapeInterval) VALUES (?, ?, ?, ?, ?);""", (session['userID'], agentName_input, webpageLink_input, elementSelector_input, scrapeInterval))
                        agentID = db("""SELECT scraperID FROM scraperAgent WHERE userID = ? AND scraperName = ?;""", (session['userID'], agentName_input))
                        agentID = agentID[0][0]
                        db("""INSERT INTO scrapeData (userID, scraperID, scrapeValue, scrapeTime, elementSelector) VALUES (?, ?, ?, ?, ?);""", (session['userID'], agentID, price_text, datetime.datetime.now(), elementSelector_input))
                        automation_Thread(scrapeInterval, agentID, session['userID'])
                        return redirect(url_for('home'))
                    else:
                        flash("That scraper agent name is already in use.")
                except Exception as e:
                    flash("There was an error accessing that webpage")
        return render_template('agentCreate.html')
    except Exception as e:
        return error(e)


@app.route('/configure', methods=['POST', 'GET'])
@login_required
def configure():
    try:
        if request.method == 'POST':
            newUsername = request.form['newUsername']
            newPassword = request.form['newPassword']
            newEmail = request.form['newEmail']
            try:
                if newUsername:
                    db("""UPDATE user SET userName = ? WHERE userID = ?;""", (newUsername, session['userID']))
                else:
                    print('User did not change username.')
                if newPassword:
                    hashedPassword = generate_password_hash(newPassword)
                    db("""UPDATE user SET userPassword = ? WHERE userID = ?;""", (hashedPassword, session['userID']))
                else:
                    print('User did not change password.')
                if newEmail:
                    db("""UPDATE user SET userEmail = ? WHERE userID = ?;""", (newEmail, session['userID']))
                else:
                    print('User did not change email.')
                return redirect(url_for('home'))
            except Exception as e:
                print(e)
        userDetails = db("""SELECT userName, userEmail FROM user WHERE userID = ?;""", (session['userID'],))
        name, email = userDetails[0]
        return render_template('configuration.html', name=name, email=email)
    except Exception as e:
        return error(e)


def automation_Thread(interval, agentID, userID):
    try:
        task = Thread(target=automation_Time, args=(interval, agentID, userID), daemon=True)
        task.start()
    except Exception as e:
        return error(e)

def automation_Time(interval, agentID, userID):
    try:
        agentData = db("""SELECT webPageURL, elementSelector FROM scraperAgent WHERE scraperID = ?;""", (agentID,))
        link, selector = agentData[0]
        hours = int(interval) * 10 # Set the interval low for testing purposes
        while True: # Start the loop to do the timely checks
            scrapeValue = automation_Scrape(link, selector)
            prevVal = db("""SELECT scrapeValue FROM scrapeData WHERE scraperID = ? ORDER BY scrapeID DESC LIMIT 1;""", (agentID,))
            db("""INSERT INTO scrapeData (userID, scraperID, scrapeTime, scrapeValue, elementSelector) VALUES (?, ?, ?, ?, ?);""", (userID, agentID, datetime.datetime.now(), scrapeValue, selector,))
            automation_Email(prevVal[0][0], scrapeValue, agentID, userID)
            time.sleep(hours)
    except Exception as e:
        return error(e)

def automation_Scrape(link, selector):
    try:
        with InvisiblePlaywright(headless=True) as browser:
            try:
                page = browser.new_page()
                page.goto(link)
                try:
                    page.wait_for_selector(f"{selector}", timeout=10000)
                except Exception as wait_err:
                    print(f"Selector not found: {wait_err}")
                price_element = page.locator(f"{selector}")
                price_text = price_element.text_content()
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
    webview.start(icon='static/images/BitScrapeLogo.ico', gui='edgechromium')
    # Start the application window