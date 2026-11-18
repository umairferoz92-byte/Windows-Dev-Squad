"""
Vulnerable / Buggy test file for Windows Dev Squad TUI verification.
Contains: SQL injection risk, hardcoded secret, missing type hints, bare except, and unused imports.
"""
import os
import sys
import sqlite3
import requests

SECRET_API_KEY = "sk-live-fake-secret-key-1234567890abcdef"

def unsafe_query(username: str):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    # Vulnerable to SQL injection (Reviewer should catch this)
    query = "SELECT * FROM users WHERE username = '" + username + "'"
    cursor.execute(query)
    return cursor.fetchall()

def divide_numbers(a, b):
    try:
        return a / b
    except: # Bare except (Reviewer should catch this)
        return None

def main():
    print("Testing Windows Dev Squad")
    res = unsafe_query("admin' OR '1'=='1")
    print("Query result:", res)

if __name__ == "__main__":
    main()
