from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, id, full_name, email, role, location=None):
        self.id = id
        self.full_name = full_name
        self.email = email
        self.role = role
        self.location = location # This line now correctly handles the location