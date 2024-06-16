from basic_test import Basic_Tests
import unittest

class Test_User(Basic_Tests):
    
    def test_register(self):
        """
        Test register endpoint
        """
        # Test register with correct data
        data = {
            'username': 'test',
            'email': 'test@example.com',
            'password': '123456'
        }
        response = self.client.post('/register', data=data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['success'], True)
        self.assertEqual(response.json['username'], data['username'])
        self.assertEqual(response.json['email'], data['email'])
    
    def test_login(self):
        """
        Test login endpoint
        """
        # Test login with correct data
        self.test_register()
        data = {
            'username': 'test',
            'password': '123456'
        }
        response = self.client.post('/login', data=data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['success'], True)
        self.assertEqual(response.json['username'], data['username'])
        self.assertEqual(response.json['email'], 'wangdong20@mails.tsinghua.edu.cn')
        response = self.client.get('get_documents')
        assert response.status_code == 200
        assert response.json['success'] == True
        print(response.json['documents'])

    def test_logout(self):
        """
        Test logout endpoint
        """
        # Test logout with correct data
        self.test_login()
        response = self.client.get('/logout')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['success'], True)
        response = self.client.get('get_documents')
        # if logout, we can't get documents
        assert response.status_code != 200
        
        
if __name__ == "__main__":
    unittest.main()
