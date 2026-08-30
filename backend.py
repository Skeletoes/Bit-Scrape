"""Bit Scrape backend.

Flask application that serves the Bit Scrape UI, manages user accounts and
scraper agents, runs background scraping threads, and emails users when a
watched value changes.
"""

import datetime
import os
import random
import smtplib
import sys
import threading
import sqlite3
from email.mime.text import MIMEText
from functools import wraps
from threading import Event, Thread

import webview
from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from invisible_playwright import InvisiblePlaywright
from invisible_playwright import cli as ip_cli
from PIL import Image
from werkzeug.security import check_password_hash, generate_password_hash


def resource_path(relative_path):
    """Resolve a path that works both when run as a .py file and as a
    PyInstaller-built .exe (which extracts to a temporary folder)."""
    try:
        # Temporary extraction folder created by the .exe on every startup.
        base_path = sys._MEIPASS  # pylint: disable=protected-access
    except AttributeError:
        # File path falls back to normal when the .py is run during dev.
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# Set important global variables.
# Connect to the .env file with all the important secret values.
load_dotenv(resource_path('.env'))
# A dict that stores the states of each threaded agent and is used to stop
# threaded agents.
running_agents = {}
# Helps prevent agent create from failing if there is an automated scrape
# running at the moment of creation.
playwright_lock = threading.Lock()
load_status = {}


app = Flask(__name__)
# Set the flask secret app key to the one stored secretly, or just generate
# a random one if the secret file cannot be found.
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(24)


def ensure_engine_available():
    """Check and, if needed, install the invisible playwright engine.

    pyinstaller does not package the browser engine with the .exe, so on a
    fresh install it has to be fetched the first time the app runs.
    """
    try:
        # Check if the browser is installed and works.
        with InvisiblePlaywright() as browser:
            browser.close()
        return True
    except Exception:  # pylint: disable=broad-exception-caught
        # Any failure here means the engine isn't ready yet; try to fetch
        # it rather than crashing the app on first run.
        print("First run: downloading scraper engine, this may take a minute...")
        try:
            ip_cli.main(['fetch'])  # verify this matches the actual entry point in cli.py
            return True
        except Exception as download_error:  # pylint: disable=broad-exception-caught
            print(f"Engine download failed: {download_error}")
            return False


if getattr(sys, 'frozen', False):
    app_dir = os.path.dirname(sys.executable)
else:
    app_dir = os.path.abspath(".")
DB_PATH = os.path.join(app_dir, 'database.db')


def db(query, params=()):
    """Run a query against the SQLite database and return the fetched rows.

    The all-in-one database access function that handles all of the web
    app's database needs.
    """
    # Create the connection to the database file.
    conn = sqlite3.connect(DB_PATH)
    # Create the cursor which will handle queries.
    cursor = conn.cursor()
    # Execute the query and use the parameters.
    cursor.execute(query, params)
    # Always commit changes even if there are not any.
    conn.commit()
    # Store the data that was fetched from the database as 'results'.
    results = cursor.fetchall()
    # Always close connection when done with the function.
    conn.close()
    # Return the data.
    return results


def login_required(f):
    """Redirect anonymous visitors to the login page before running `f`."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'userID' not in session:  # Check if the user is actually logged in.
            flash('Please log in to continue.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


@app.errorhandler(404)
def page_not_found(_error):
    """Render the custom 404 page for Flask's built-in error handler."""
    return render_template('404.html'), 404


def error(error_message):
    """Render the generic error page with a message."""
    return render_template('error.html', errorMessage=error_message)


@app.route('/')
def index():
    """Clear any existing session and send the visitor to the login page."""
    session.clear()
    return redirect(url_for('login'))


@app.route('/loadCheck')
def load_check():
    """Poll endpoint used by the loading page JS to check load progress."""
    load_id = session.get('loadID')
    next_page = session.get('nextPage')
    if load_status.get(load_id) == 'error':
        # An error occurred while loading, so flash an error message.
        flash('An error occured while trying to perform the most recent requested action.')
        return redirect(url_for('home'))
    if load_status.get(load_id) is True:
        # Loading is complete, redirect to the next page.
        return redirect(url_for(next_page))
    # Keep waiting; the page refreshes itself again.
    return render_template('loadingPage.html')


# Must use 'POST' and 'GET' because 'GET' is required for the url redirection
# from index to login.
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle the login form and start the user's agent threads."""
    try:
        if request.method == 'POST':
            # Fetch the data from the form.
            username_input = request.form['username']
            password_input = request.form['password']
            # Check if the user credentials are in the database.
            user_data = db("""SELECT * FROM user WHERE userName = ?;""", (username_input,))
            if not user_data or not check_password_hash(user_data[0][2], password_input):
                flash('Credentials are incorrect')
                return render_template('login.html')

            # If the user credentials are correct then redirect the user to home.
            session['userID'] = user_data[0][0]
            user_id = user_data[0][0]
            session['nextPage'] = 'home'
            load_status[user_id] = False
            session['loadID'] = random.randint(1, 100)
            load_id = session['loadID']

            # Display the loading page while the backend sets up the scraper agent threads.
            def loading(user_id, load_id):
                try:
                    user_agents = db(
                        """SELECT scraperID, scrapeInterval FROM scraperAgent
                        WHERE userID = ?;""",
                        (user_id,),
                    )
                    # Start a background thread for each of the user's scraper agents.
                    for agent in user_agents:
                        automation_thread(agent[1], agent[0], user_id)
                    load_status[load_id] = True
                except Exception:  # pylint: disable=broad-exception-caught
                    load_status[load_id] = 'error'

            Thread(target=loading, args=(user_id, load_id), daemon=True).start()
            return render_template('loadingPage.html')
        return render_template('login.html')
    except Exception as login_error:  # pylint: disable=broad-exception-caught
        return error(login_error)


@app.route('/accountCreate', methods=['POST', 'GET'])
def account_create():
    """Handle account creation."""
    try:
        if request.method == 'POST':
            # Get the credentials the user input from the form.
            username_input = request.form['username']
            password_input = request.form['password']
            email_input = request.form['email']

            # Check the length of the username and password.
            if not 3 < len(username_input) < 20 or not 3 < len(password_input) < 20:
                flash('The username or password is not the correct length. '
                      '(3 to 20 characters!!!)')
                return render_template('accountCreate.html')

            # Check if the username is already in the database.
            if db("""SELECT * FROM user WHERE userName = ?;""", (username_input,)):
                flash('That username is already in use.')
                return render_template(
                    'accountCreate.html', password=password_input, email=email_input,
                )

            # Check if the email is already in the database.
            if db("""SELECT * FROM user WHERE userEmail = ?;""", (email_input,)):
                flash('That email is already in use.')
                return render_template(
                    'accountCreate.html', name=username_input, password=password_input,
                )

            session['loadID'] = random.randint(1, 100)
            load_id = session['loadID']
            load_status[load_id] = False
            session['nextPage'] = 'login'

            def loading(username_input, password_input, email_input, load_id):
                # Generate a password hash to keep the user's password secure.
                hashed_password = generate_password_hash(password_input)
                db(
                    "INSERT INTO user (userName, userPassword, userEmail) VALUES (?, ?, ?);",
                    (username_input, hashed_password, email_input),
                )
                load_status[load_id] = True

            Thread(
                target=loading,
                args=(username_input, password_input, email_input, load_id),
                daemon=True,
            ).start()
            return render_template('loadingPage.html')
        return render_template('accountCreate.html')
    except Exception as create_error:  # pylint: disable=broad-exception-caught
        return error(create_error)


@app.route('/home')
@login_required
def home():
    """Show all of the logged-in user's scraper agents."""
    try:
        scraper_details = db(
            """SELECT scraperName, webPageURL FROM scraperAgent WHERE userID = ?;""",
            (session['userID'],),
        )
        agents = [{'name': row[0], 'url': row[1]} for row in scraper_details]
        return render_template('home.html', agents=agents)
    except Exception as home_error:  # pylint: disable=broad-exception-caught
        return error(home_error)


@app.route('/agentSelect', methods=['POST', 'GET'])
@login_required
def agent_select():
    """Store which agent was selected so agent_config can look it up."""
    try:
        if request.method == 'POST':
            agent_name = request.form['agentName']
            agent = db(
                """SELECT scraperID FROM scraperAgent WHERE userID = ? AND scraperName = ?;""",
                (session['userID'], agent_name),
            )
            session['scraperID'] = agent[0][0]
        return redirect(url_for('agent_config'))
    except Exception as select_error:  # pylint: disable=broad-exception-caught
        return error(select_error)


@app.route('/agentDelete', methods=['POST', 'GET'])
@login_required
def agent_delete():
    """Delete the currently selected scraper agent and its history."""
    try:
        if request.method == 'POST':
            db("""DELETE FROM scrapeData WHERE scraperID =?;""", (session['scraperID'],))
            db("""DELETE FROM scraperAgent WHERE scraperID = ?;""", (session['scraperID'],))
            stop_event = running_agents.get(session['scraperID'])
            if stop_event:
                stop_event.set()
            return redirect(url_for('home'))
        return redirect(url_for('home'))
    except Exception as delete_error:  # pylint: disable=broad-exception-caught
        return error(delete_error)


@app.route('/userDelete', methods=['POST', 'GET'])
@login_required
def user_delete():
    """Delete the logged-in user's account, agents, and scrape history."""
    try:
        if request.method == 'POST':
            user_agent_ids = db(
                """SELECT scraperID FROM scraperAgent WHERE userID = ?;""",
                (session['userID'],),
            )
            # Stop the user's scraper agent threads when they delete their account.
            for row in user_agent_ids:
                stop_event = running_agents.get(row[0])
                if stop_event:
                    stop_event.set()
            # Delete all of the user's details.
            db("""DELETE FROM scrapeData WHERE userID = ?;""", (session['userID'],))
            db("""DELETE FROM scraperAgent WHERE userID = ?;""", (session['userID'],))
            db("""DELETE FROM user WHERE userID = ?;""", (session['userID'],))
            return redirect(url_for('index'))
        return redirect(url_for('index'))
    except Exception as user_delete_error:  # pylint: disable=broad-exception-caught
        return error(user_delete_error)


@app.route('/agentConfig', methods=['POST', 'GET'])
@login_required
def agent_config():  # pylint: disable=too-many-return-statements
    """View and update the currently selected scraper agent's settings."""
    try:
        agent_details = db(
            """SELECT scraperName, webPageURL, elementSelector, scrapeInterval
            FROM scraperAgent WHERE scraperID = ?;""",
            (session['scraperID'],),
        )
        name, link, selector, interval = agent_details[0]
        if request.method != 'POST':
            return render_template(
                'agentConfig.html', name=name, link=link, selector=selector, interval=interval,
            )

        scraper_id = session['scraperID']
        new_agent_name = request.form['newAgent-name']
        new_agent_link = request.form['newAgent-link']
        new_agent_selector = request.form['newAgent-selector']
        scrape_interval = request.form['scrapeInterval']

        if new_agent_name != name:
            if not 3 < len(new_agent_name) < 20:
                flash('That scraper name is not the correct length, must be 3 to 20 '
                      'characters long.')
                return render_template(
                    'agentConfig.html', name=name, link=new_agent_link,
                    selector=new_agent_selector, interval=scrape_interval,
                )
            if db(
                """SELECT * FROM scraperAgent WHERE userID = ? AND scraperName = ?;""",
                (session['userID'], new_agent_name),
            ):
                flash('That scraper name is in use.')
                return render_template(
                    'agentConfig.html', name=name, link=new_agent_link,
                    selector=new_agent_selector, interval=scrape_interval,
                )
            db(
                """UPDATE scraperAgent SET scraperName WHERE scraperID = ?;""",
                (scraper_id,),
            )

        if scrape_interval != interval:
            db(
                """UPDATE scraperAgent SET scrapeInterval = ? WHERE scraperID = ?;""",
                (scrape_interval, scraper_id),
            )

        if new_agent_link != link or new_agent_selector != selector:
            if db(
                """SELECT * FROM scraperAgent
                WHERE userID = ? AND webPageURL = ? AND elementSelector = ?;""",
                (session['userID'], new_agent_link, new_agent_selector),
            ):
                flash('You are already monitoring that webpage element.')
                return render_template(
                    'agentConfig.html', name=new_agent_name, link=link,
                    selector=selector, interval=scrape_interval,
                )

            session['loadID'] = random.randint(1, 100)
            load_id = session['loadID']
            load_status[load_id] = False
            session['nextPage'] = 'home'

            def loading(load_id, new_agent_link, new_agent_selector, scraper_id):
                with playwright_lock:
                    # Scrape website and fetch the requested value.
                    with InvisiblePlaywright(headless=True) as browser:
                        try:
                            page = browser.new_page()
                            page.goto(new_agent_link)
                            page.screenshot(path="tmpImg.png")
                            img = Image.open("tmpImg.png")
                            img.show()
                            # Delete the screenshot.
                            os.remove("tmpImg.png")
                            # Wait for the element to show.
                            page.wait_for_selector(f"{new_agent_selector}", timeout=10000)
                            price_element = page.locator(new_agent_selector)
                            price_text = price_element.text_content()  # Fetch the value.
                            print(f"Current price: {price_text}")
                            browser.close()
                            db(
                                """UPDATE scraperAgent SET webPageURL = ?, elementSelector = ?
                                WHERE scraperID = ?;""",
                                (new_agent_link, new_agent_selector, scraper_id),
                            )
                            load_status[load_id] = True
                        except Exception:  # pylint: disable=broad-exception-caught
                            load_status[load_id] = 'error'

            Thread(
                target=loading,
                args=(load_id, new_agent_link, new_agent_selector, scraper_id),
                daemon=True,
            ).start()
            return render_template('loadingPage.html')

        return redirect(url_for('home'))
    except Exception as config_error:  # pylint: disable=broad-exception-caught
        return error(config_error)


@app.route('/agentCreate', methods=['POST', 'GET'])
@login_required
def agent_create():
    """Create a new scraper agent and start monitoring it."""
    try:
        if request.method == 'POST':
            agent_name_input = request.form['agentName']
            webpage_link_input = request.form['webpageLink']
            element_selector_input = request.form['elementSelector']
            scrape_interval = request.form['scrapeInterval']

            if db(
                """SELECT * FROM scraperAgent WHERE userID = ? AND scraperName = ?;""",
                (session['userID'], agent_name_input),
            ):
                flash("That scraper agent name is already in use.")
                return render_template(
                    'agentCreate.html', link=webpage_link_input,
                    selector=element_selector_input, interval=scrape_interval,
                )

            if not 3 < len(agent_name_input) < 20:
                flash('That scraper name is not the correct length. (3 to 20 characters!!!)')
                return render_template(
                    'agentCreate.html', link=webpage_link_input,
                    selector=element_selector_input, interval=scrape_interval,
                )

            if db(
                """SELECT * FROM scraperAgent
                WHERE userID = ? AND webPageURL = ? AND elementSelector = ?;""",
                (session['userID'], webpage_link_input, element_selector_input),
            ):
                flash("That webpage element is already being monitored.")
                return render_template(
                    'agentCreate.html', name=agent_name_input, link=webpage_link_input,
                    interval=scrape_interval,
                )

            session['loadID'] = random.randint(1, 100)
            load_id = session['loadID']
            load_status[load_id] = False
            session['nextPage'] = 'home'
            user_id = session['userID']

            def loading(  # pylint: disable=too-many-arguments,too-many-positional-arguments
                load_id, user_id, agent_name_input, webpage_link_input,
                element_selector_input, scrape_interval,
            ):
                with playwright_lock:
                    with InvisiblePlaywright(headless=True) as browser:
                        try:
                            page = browser.new_page()
                            page.goto(webpage_link_input)
                            page.wait_for_selector(f"{element_selector_input}", timeout=10000)
                            # Give the screenshot a temporary name; delete after it's opened.
                            page.screenshot(path="tmpImg.png")
                            price_element = page.locator(f"{element_selector_input}")
                            price_text = price_element.text_content()
                            print(f"Current price: {price_text}")
                            browser.close()
                            img = Image.open("tmpImg.png")
                            img.show()
                            # Delete the screenshot.
                            os.remove("tmpImg.png")
                            db(
                                """INSERT INTO scraperAgent
                                (userID, scraperName, webPageURL, elementSelector,
                                scrapeInterval) VALUES (?, ?, ?, ?, ?);""",
                                (
                                    user_id, agent_name_input, webpage_link_input,
                                    element_selector_input, scrape_interval,
                                ),
                            )
                            agent_id = db(
                                """SELECT scraperID FROM scraperAgent
                                WHERE userID = ? AND scraperName = ?;""",
                                (user_id, agent_name_input),
                            )
                            agent_id = agent_id[0][0]
                            db(
                                """INSERT INTO scrapeData
                                (userID, scraperID, scrapeValue, scrapeTime, elementSelector)
                                VALUES (?, ?, ?, ?, ?);""",
                                (
                                    user_id, agent_id, price_text,
                                    datetime.datetime.now(), element_selector_input,
                                ),
                            )
                            automation_thread(scrape_interval, agent_id, user_id)
                            load_status[load_id] = True
                        except Exception:  # pylint: disable=broad-exception-caught
                            load_status[load_id] = 'error'

            Thread(
                target=loading,
                args=(
                    load_id, user_id, agent_name_input, webpage_link_input,
                    element_selector_input, scrape_interval,
                ),
                daemon=True,
            ).start()
            return render_template('loadingPage.html')
        return render_template('agentCreate.html')
    except Exception as create_error:  # pylint: disable=broad-exception-caught
        return error(create_error)


@app.route('/configure', methods=['POST', 'GET'])
@login_required
def configure():  # pylint: disable=too-many-return-statements
    """View and update the logged-in user's account settings."""
    try:
        user_details = db(
            """SELECT userName, userEmail FROM user WHERE userID = ?;""",
            (session['userID'],),
        )
        name, email = user_details[0]
        if request.method == 'POST':
            new_username = request.form['newUsername']
            new_password = request.form['newPassword']
            new_email = request.form['newEmail']
            try:
                if new_username != name:
                    if not 2 < len(new_username) < 20:
                        flash('That username is not the correct length. '
                              '(3 to 20 characters!!!)')
                        return render_template('configuration.html', name=name, email=new_email)
                    if db("""SELECT * FROM user WHERE userName = ?;""", (new_username,)):
                        flash('That username is unavailable.')
                        return render_template('configuration.html', name=name, email=new_email)
                    db(
                        """UPDATE user SET userName = ? WHERE userID = ?;""",
                        (new_username, session['userID']),
                    )
                if new_password:
                    if not 3 < len(new_password) < 20:
                        flash('That password is not the correct length. (3 to 20 chracters!!!)')
                        return render_template(
                            'configuration.html', name=new_username, email=new_email,
                        )
                    hashed_password = generate_password_hash(new_password)
                    db(
                        """UPDATE user SET userPassword = ? WHERE userID = ?;""",
                        (hashed_password, session['userID']),
                    )
                if new_email != email:
                    if db("""SELECT * FROM user WHERE userEmail = ?;""", (new_email,)):
                        flash('That email is unavailable.')
                        return render_template(
                            'configuration.html', name=new_username, email=email,
                        )
                    db(
                        """UPDATE user SET userEmail = ? WHERE userID = ?;""",
                        (new_email, session['userID']),
                    )
                return redirect(url_for('home'))
            except Exception as update_error:  # pylint: disable=broad-exception-caught
                print(update_error)
        return render_template('configuration.html', name=name, email=email)
    except Exception as configure_error:  # pylint: disable=broad-exception-caught
        return error(configure_error)


def automation_thread(interval, agent_id, user_id):
    """Start a background scraper thread for an agent, if not already running."""
    try:
        if agent_id in running_agents:
            return None  # Already running, don't start a duplicate.
        stop_event = Event()
        running_agents[agent_id] = stop_event
        task = Thread(
            target=automation_time, args=(interval, agent_id, user_id, stop_event), daemon=True,
        )
        task.start()
    except Exception as thread_error:  # pylint: disable=broad-exception-caught
        return error(thread_error)
    return None


def automation_time(interval, agent_id, user_id, stop_event):
    """Repeatedly scrape an agent's target element on its configured interval."""
    try:
        agent_data = db(
            """SELECT webPageURL, elementSelector FROM scraperAgent WHERE scraperID = ?;""",
            (agent_id,),
        )
        if not agent_data:
            # Agent was deleted before this thread even got its first data — bail out cleanly.
            running_agents.pop(agent_id, None)
            return None
        link, selector = agent_data[0]
        # Multiply the scraper agent's set interval (hours) by 3600 seconds.
        seconds = int(interval) * 3600

        while not stop_event.is_set():
            scrape_value = automation_scrape(link, selector)
            prev_val = db(
                """SELECT scrapeValue FROM scrapeData
                WHERE scraperID = ? ORDER BY scrapeID DESC LIMIT 1;""",
                (agent_id,),
            )
            db(
                """INSERT INTO scrapeData
                (userID, scraperID, scrapeTime, scrapeValue, elementSelector)
                VALUES (?, ?, ?, ?, ?);""",
                (user_id, agent_id, datetime.datetime.now(), scrape_value, selector),
            )
            if prev_val:  # Guard against the very first scrape, where prev_val is empty.
                automation_email(prev_val[0][0], scrape_value, agent_id, user_id)

            # stop_event.wait() sleeps for `seconds`, but returns immediately (True) if the
            # event gets set, instead of time.sleep() which would block regardless.
            stop_event.wait(seconds)

        running_agents.pop(agent_id, None)  # Clean up once the loop actually exits.
    except Exception as time_error:  # pylint: disable=broad-exception-caught
        return error(time_error)
    return None


def automation_scrape(link, selector):
    """Load a page with Playwright and return the text of the watched element."""
    try:
        with playwright_lock:
            with InvisiblePlaywright(headless=True) as browser:
                try:
                    page = browser.new_page()
                    page.goto(link)
                    page.wait_for_selector(f"{selector}", timeout=10000)
                    price_element = page.locator(selector)
                    price_text = price_element.text_content()
                    browser.close()
                    return price_text
                except Exception as scrape_error:  # pylint: disable=broad-exception-caught
                    return str(scrape_error)
    except Exception as outer_scrape_error:  # pylint: disable=broad-exception-caught
        return error(outer_scrape_error)


def automation_email(prev_val, cur_val, agent_id, user_id):  # pylint: disable=too-many-locals
    """Email the user if a scraper agent's watched value has changed."""
    try:
        if cur_val == prev_val:  # No difference between the previous and current values.
            return None

        user_details = db(
            """SELECT userName, userEmail FROM user WHERE userID = ?;""", (user_id,),
        )
        username, email = user_details[0]
        agent_details = db(
            """SELECT scraperName, webPageURL FROM scraperAgent WHERE scraperID = ?;""",
            (agent_id,),
        )
        agent_name, scrape_link = agent_details[0]

        # Email account credentials.
        sender_email = os.environ.get("SENDER_EMAIL")
        # Generated from Google Account > Security > App passwords.
        app_password = os.environ.get("APP_PASSWORD")
        receiver_email = email

        # Email content.
        subject = f"Agent-{agent_name} detected a change"
        body = (
            f"Hello {username}, \n\n"
            f"Agent-{agent_name} detected a change from {scrape_link}.\n\n"
            f"Previous value = {prev_val}.\n"
            f"Current value = {cur_val}.\n"
        )

        # Create MIMEText object.
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = sender_email
        msg["To"] = receiver_email

        try:
            # Connect to Gmail's SMTP server.
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(sender_email, app_password)
                server.send_message(msg)
            print("Email sent successfully!")
        except Exception as send_error:  # pylint: disable=broad-exception-caught
            print(f"Error: {send_error}")
    except Exception as email_error:  # pylint: disable=broad-exception-caught
        return error(email_error)
    return None


def run_flask():
    """Run the Flask app on port 8000."""
    app.run(port=8000)


if __name__ == '__main__':
    # Create the thread 't' so the flask app runs on a separate thread.
    t = Thread(target=run_flask)
    # Set 't.daemon' to true so that when the webview window is closed then the flask app
    # is ended too.
    t.daemon = True
    # Start the flask app in the background; the code beneath this can run at the same time.
    t.start()

    # Define the webview configuration.
    window = webview.create_window(
        'Bit Scrape',
        'http://127.0.0.1:8000',
        # Set the fixed size for the application window.
        width=400,
        height=580,
        # Set resizable to false so that the window can not be resized at all.
        resizable=False,
    )
    # Start the application window.
    webview.start(icon=resource_path('static/images/BitScrapeLogo.ico'), gui='edgechromium')