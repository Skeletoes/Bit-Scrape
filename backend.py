from flask import Flask, render_template, session, redirect, url_for, request, flash
from flaskwebgui import FlaskUI
import sqlite3

app = Flask(__name__)
app.secret_key = "qa567-KLu8T-ZgD45-9sdfg-1234"

def db(query, params=()):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute(query, params)
    conn.commit()
    results = cursor.fetchall()
    conn.close()
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

        userData = db('SELECT * FROM user WHERE userName = ? AND userPassword = ?;', (session['userName'], session['userPassword']))
        if not userData:
            # No users found
        else:
            # User found
            return render_template('login.html')

@app.route('/accountCreate', methods=['POST', 'GET'])
def accountCreate():
    if request.method == 'POST':
        usernameInput = request.form['username']
        passwordInput = request.form['password']
        emailInput = request.form['email']
        if 5 < len(usernameInput) < 20 and 5 < len(passwordInput) < 20 and 5 < len(emailInput) < 20:
            query = """SELECT * FROM user WHERE userName = ?;"""
            dataList = []
            dataList.append(usernameInput)
            usernameExist = databaseControl(query, dataList, 'check', 'user')
            if len(usernameExist) > 0:
                flash()
                return render_template('accountCreate.html')
            else:
                query = """SELECT * FROM user WHERE userEmail = ?;"""
                del dataList
                dataList = []
                dataList.append(emailInput)
                emailExist = databaseControl(query, dataList, 'check', 'user')
                if len(emailExist) > 0:
                    return render_template('accountCreate.html', error='Email already in use! Try again.')
                else:
                    query = """INSERT INTO user (userName, userPassword, userEmail) VALUES (?, ?, ?);"""
                    del dataList
                    dataList = []
                    dataList.append(usernameInput)
                    dataList.append(passwordInput)
                    dataList.append(emailInput)
                    databaseControl(query, dataList, 'add', 'user')
                    return redirect(url_for('login'))
        return render_template('accountCreate.html', error='One of the credentials are not the correct length. 5 to 20 characters!')

            
        usernameInput = request.form['username']
        passwordInput = request.form['password']
        emailInput = request.form['email']
    return render_template('accountCreate.html')



@app.route('/home')
def home():
    return render_template('home.html')

    

    

if __name__ == '__main__':
    FlaskUI(app=app, server="flask", width=800, height=480, port=8000).run()