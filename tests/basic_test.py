import copy
import unittest
from app import app, db, add_default_user
from config import TestConfig
from models import User

app.config.from_object(TestConfig)
db.init_app(app)

class Basic_Tests(unittest.TestCase):
    def __init__(self, methodName: str = "runTest") -> None:
        super().__init__(methodName)
        
    def setUp(self):
        """
        Create a test client before each test
        """
        self.app = app
        self.client = app.test_client()
        self.tearDown()
        with app.app_context():
            db.create_all()
            add_default_user()


    def tearDown(self):
        with app.app_context():
            # 删除所有数据库表
            db.session.remove()
            db.drop_all()
    
    def register(self):
        # Test register with correct data
        data = {
            'username': 'test',
            'email': 'test@example.com',
            'password': '123456'
        }
        return self.client.post('/register', data=data)
if __name__ == "__main__":
    unittest.main()
