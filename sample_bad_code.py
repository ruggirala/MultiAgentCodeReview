import os
import sys

# A deliberately bad Python file for testing the code review agent

def get_user_data(id):
    import sqlite3
    conn = sqlite3.connect('users.db')
    query = "SELECT * FROM users WHERE id = " + str(id)  # SQL injection vulnerability
    cursor = conn.execute(query)
    data = cursor.fetchone()
    return data

def calculate_average(numbers):
    total = 0
    for i in range(len(numbers)):  # Non-pythonic iteration
        total = total + numbers[i]
    average = total / len(numbers)  # ZeroDivisionError if empty list
    return average

def read_file(filename):
    f = open(filename, 'r')  # File handle never closed
    content = f.read()
    return content

class userAccount:  # Bad class naming (should be PascalCase)
    def __init__(self, name, password):
        self.name = name
        self.password = password  # Storing plain text password

    def check_password(self, input_password):
        if self.password == input_password:  # Plain text comparison
            return True
        else:
            return False

    def transfer_money(self, amount, target):
        self.balance = self.balance - amount  # No check if balance exists or is sufficient
        target.balance = target.balance + amount
        print("Transfer complete")

def process_items(items):
    result = []
    for item in items:
        try:
            processed = item.strip().lower()
            result.append(processed)
        except:  # Bare except clause
            pass  # Silently swallowing errors
    return result

def find_duplicates(lst):
    duplicates = []
    for i in range(len(lst)):
        for j in range(len(lst)):  # O(n^2) and compares element with itself
            if i != j and lst[i] == lst[j]:
                if lst[i] not in duplicates:
                    duplicates.append(lst[i])
    return duplicates

password_list = ["admin123", "password", "qwerty"]  # Hardcoded credentials

def login(username, pwd):
    if pwd in password_list:
        return True
    return False
