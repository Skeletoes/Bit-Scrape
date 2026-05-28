from flask import Flask, render_template, session, redirect, url_for, request, flash
import sqlite3
import webview
from threading import Thread

app = Flask(__name__)
app.secret_key = "qa567-KLu8T-ZgD45-9sdfg-1234"

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


@app.route('/')
def index():
    session.clear()
    return redirect(url_for('login'))

# Must use 'POST' and 'GET' because 'GET' is required for the url redirection from index to login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Fetch the data from the form and add it to session variables
        session['userName'] = request.form['username']
        session['userPassword'] = request.form['password']

        # Check if the user credentials are in the database
        userData = db('SELECT * FROM user WHERE userName = ? AND userPassword = ?;', (session['userName'], session['userPassword']))
        if not userData:
            flash('Credentials are incorrect')
        else:
            # If the user credentials are correct then redirect the user to home
            return redirect(url_for('home'))
    return render_template('login.html')

@app.route('/accountCreate', methods=['POST', 'GET'])
def accountCreate():
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
                db("INSERT INTO user (userName, userPassword, userEmail) VALUES (?, ?, ?);", (usernameInput, passwordInput, emailInput))
                # Redirect the user to the login page so they can login with their newly created account
                return redirect(url_for('login'))
            else:
                flash('That username or email is already being used.')
        else:
            flash('The username of password is not long enough. (5 to 20 characters!!!)')

    return render_template('accountCreate.html')



@app.route('/home')
def home():
    return render_template('home.html')


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
    # Start the application window
    webview.start()