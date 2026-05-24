from flask import Flask, render_template, session, redirect, url_for, request
from flaskwebgui import FlaskUI
import sqlite3

app = Flask(__name__)
app.secret_key = "qa567-KLu8T-ZgD45-9sdfg-1234"

def databaseControl(query, data, function, table):
    # 'query' = the query that needs to be executed
    # 'data' = a list of the data that will be used for the query
    # 'function' = the what will the data be used for (e.g Add, Delete, Retrieve)
    # 'table' = what table will be effected
    dbConnection = sqlite3.connect('database.db')
    dbCursor = dbConnection.cursor()
    if function == 'add': # If data needs to be added to the database
        if table == 'user': # If the user wants to create an account
            # Using try and except to handle errors and easier to diagnose the errors
            try:
                # Execute the query to add a user
                dbCursor.execute(query, (data[0], data[1], data[2], data[3]))
                # Commit to save the data
                dbConnection.commit()
            except Exception as e:
                print(f"An error occured at function=databaseControl while trying to 'add' a 'user' to the database. {e}")
    # If data needs to be retrieved from the database
    elif function == 'retrieve': 
        # If the user wants to login
        if table == 'user': 
            try:
                # Executes the query to retrieve all the 'user' data associated with the credentials provided.
                dbCursor.execute(query, (data[0], data[1],)) 
                userData = dbCursor.fetchall()
                dbConnection.close()
                # Sends the retrieved data back to the login function
                return userData 
            except Exception as e:
                print(f"An error has occured at function=databaseControl while trying to 'retrieve' data from 'user' table. {e}")
    



@app.route('/')
def index():
    session.clear()
    return redirect(url_for('login'))

# Must use 'POST' and 'GET' because 'GET' is required for the url redirection from index to login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Create the list of data for the 'databaseControl' function
        dataList = []
        # Fetch the data from the form and add it to the 'dataList'
        dataList.append(request.form['username'])
        dataList.append(request.form['password'])

        # Prepare the query for the 'databaseControl' function
        query = """SELECT * FROM user WHERE userName = ? AND userPassword = ?;"""
        # Create a variable from the data send from the 'databaseControl' function
        data = databaseControl(query, dataList, 'retrieve', 'user')
        # Create a list variable, 'userData', from the dictionary 'data'
        userData = data[0]

        # Check if there was anything actually returned from the 'databaseControl' function to confirm if user login credentials were correct
        # If the 'databaseControl' function returned nothing then redirect back to 'index' so login process may begin again
        if len(data) == 0:
            return redirect(url_for('index'))
        # If the 'databaseControl' function did return data then login succeeded
        else:
            # Create important session variables to use throughout the code
            session['UserID'] = userData[0]
            session['UserEmail'] = userData[3]
            return redirect(url_for('home'))
    return render_template('login.html')

@app.route('/home')
def home():
    return render_template('home.html')

    

    

if __name__ == '__main__':
    FlaskUI(app=app, server="flask", width=800, height=480, port=8000).run()