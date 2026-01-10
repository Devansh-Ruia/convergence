"""
Helper script to create a test PR with intentional issues.
This creates a branch with vulnerable code for testing.

Run with: python scripts/create_test_pr.py
"""

VULNERABLE_CODE = '''
# user_service.py - Example file with intentional issues

import os
import sqlite3

# SECURITY: Hardcoded credentials
DB_PASSWORD = "admin123"
API_KEY = "sk-1234567890abcdef"

class UserService:
    def __init__(self):
        # PERFORMANCE: Connection created but never closed
        self.conn = sqlite3.connect("users.db")
    
    def find_user(self, username):
        """Find user by username."""
        # SECURITY: SQL Injection vulnerability
        query = f"SELECT * FROM users WHERE username = '{username}'"
        cursor = self.conn.execute(query)
        return cursor.fetchone()
    
    def get_all_users(self):
        """Get all users."""
        # PERFORMANCE: SELECT * fetches unnecessary data
        # PERFORMANCE: No pagination - could return millions of rows
        cursor = self.conn.execute("SELECT * FROM users")
        return cursor.fetchall()
    
    def search_users(self, query):
        """Search users by name."""
        users = self.get_all_users()
        results = []
        # PERFORMANCE: O(n) search when database query would be faster
        for user in users:
            if query.lower() in user[1].lower():
                results.append(user)
        return results
    
    def delete_user(self, user_id):
        """Delete a user."""
        # SECURITY: No authorization check
        # TESTING: No error handling
        self.conn.execute(f"DELETE FROM users WHERE id = {user_id}")
        self.conn.commit()
    
    def export_users(self, filename):
        """Export users to file."""
        # SECURITY: Path traversal vulnerability
        with open(f"/data/exports/{filename}", "w") as f:
            for user in self.get_all_users():
                f.write(str(user))


# TESTING: No tests exist for this module
'''

print("="*60)
print("TEST PR CREATION HELPER")
print("="*60)
print("""
To test Convergence, create a PR with the code above.

Option 1: Manual
  1. Create a new branch in your test repo
  2. Add a file with the vulnerable code above
  3. Open a PR
  4. Use that PR number in the demo

Option 2: GitHub CLI
  gh repo create convergence-test --public
  echo '<paste code>' > user_service.py
  git add . && git commit -m "Add user service"
  git push origin main
  git checkout -b feature/user-service
  # Make a small change
  git push origin feature/user-service
  gh pr create --title "Add user service" --body "New feature"

The vulnerable code contains:
  🔒 SQL injection (lines 18, 40)
  🔒 Hardcoded secrets (lines 7-8)
  🔒 Path traversal (line 44)
  🔒 Missing auth check (line 36)
  ⚡ Memory leak / unclosed connection (line 12)
  ⚡ SELECT * anti-pattern (line 23)
  ⚡ Missing pagination (line 23)
  ⚡ O(n) search vs database (line 30)
  🧪 No error handling (line 38)
  🧪 No tests for module
""")
print("="*60)