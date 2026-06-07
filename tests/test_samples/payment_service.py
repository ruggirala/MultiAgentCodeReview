"""
payment_service.py — a deliberately buggy module used to demo the multi-agent
code review workflow on a real GitHub PR. NOT production code.
"""

import sqlite3

API_SECRET = "sk_live_abc123_HARDCODED_SECRET"  # hardcoded credential


def get_account(account_id):
    conn = sqlite3.connect("payments.db")
    # SQL injection: account_id concatenated straight into the query
    query = "SELECT * FROM accounts WHERE id = " + str(account_id)
    cursor = conn.execute(query)
    return cursor.fetchone()  # connection never closed


def average_transaction(amounts):
    total = 0
    for i in range(len(amounts)):  # non-pythonic iteration
        total = total + amounts[i]
    return total / len(amounts)  # ZeroDivisionError on empty list


class account:  # class should be PascalCase
    def __init__(self, owner, pin, history=[]):  # mutable default argument
        self.owner = owner
        self.pin = pin  # PIN stored in plain text
        self.history = history

    def verify_pin(self, entered):
        return self.pin == entered  # plain-text comparison

    def withdraw(self, amount):
        # no check that balance exists or is sufficient
        self.balance = self.balance - amount
        self.history.append(("withdraw", amount))
        return self.balance


def load_config(path):
    f = open(path)  # file handle never closed
    data = f.read()
    return data


def find_duplicate_ids(ids):
    dupes = []
    for i in range(len(ids)):
        for j in range(len(ids)):  # O(n^2) duplicate scan
            if i != j and ids[i] == ids[j] and ids[i] not in dupes:
                dupes.append(ids[i])
    return dupes


def process(records):
    out = []
    for r in records:
        try:
            out.append(r.strip().upper())
        except:  # bare except swallows everything
            pass
    return out
