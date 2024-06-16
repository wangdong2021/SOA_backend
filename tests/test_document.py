from basic_test import Basic_Tests
import unittest
from models import Document, Question, QUESTION_TYPE_LIST

class Test_Document(Basic_Tests):
    
    def upload_document(self):
        """
        Test upload_document endpoint
        """
        self.register()
        # Test upload_document with correct data
        data = {
            'pdf_url': 'https://arxiv.org/abs/2309.10305'
        }
        response = self.client.post('/upload_document', data=data)
        assert response.status_code == 200
        assert response.json['success'] == True
        # TODO add other judgement here
        # Test recomendation paper and person_labels

    def get_recommendations(self):
        """
        Test get_recommendations endpoint
        """
        response = self.client.get('/get_recommendations')
        assert response.status_code == 200
        assert response.json['success'] == True
        recomandations = response.json['recommendations']
        print('Recommendations:')
        for rec in recomandations:
            print(rec['title'])
        print("End of Recommendations\n")
        return recomandations

    def get_user_profile(self):
        """
        Test get_user_profile endpoint, note that if only part of exam was done, will the score update?
        """
        response = self.client.get('/get_user_profile')
        assert response.status_code == 200
        assert response.json['success'] == True
        print("User Profile:")
        print(response.json)
        print("End of User Profile\n")
        return response.json
    
    def get_documents(self):
        """
        Test get_documents endpoint
        """
        self.upload_document()
        self.get_recommendations()
        self.get_user_profile()
        response = self.client.get('/get_documents')
        assert response.status_code == 200
        assert response.json['success'] == True
        return response.json['documents']

    def generate_exam(self):
        documents = self.get_documents()
        for document in documents:
            response = self.client.post(
                '/generate_exam',
                data={
                    'document_id': document['document_id']
                }
            )
            assert response.status_code == 200
            assert response.json['success'] == True
            print(response.json)
        return documents
    
    def get_exams(self):
        """
        Test get_exams endpoint
        """
        documents = self.generate_exam()
        exams = []
        for document in documents:
            response = self.client.get(f'/get_exams?document_id={document["document_id"]}')
            assert response.status_code == 200
            assert response.json['success'] == True
            print(f"Exams of document {document['document_id']}")
            print(response.json)
            print("End of Exams\n")
            exams.extend(response.json['exams'])
        return exams
    
    def get_exam_questions(self):
        exams = self.get_exams()
        questions = []
        for exam in exams:
            response = self.client.get(f'/get_exam?exam_id={exam["exam_id"]}')
            assert response.status_code == 200
            assert response.json['success'] == True
            print(f"Questions of exam {exam['exam_id']}")
            for question in response.json['questions']:
                print(f'question type: {QUESTION_TYPE_LIST[question["question_type"]]}')
                print('questsion_content:')
                print(question['question_content'])
            print("End of Questions\n")
            questions.extend(response.json['questions'])        
        return questions
    
    def test_answer_question(self):
        """
        'test submit answer to a question'
        """
        questions = self.get_exam_questions()
        for question in questions[-2:]:
            if question['done']:
                continue
            print(f'question type: {QUESTION_TYPE_LIST[question["question_type"]]}')
            print('questsion_content:')
            print(question['question_content'])
            while True:
                user_answer = input('Please input your answer: ')
                if user_answer == 'pdb':
                    import pdb; pdb.set_trace()
                else:
                    break
            response = self.client.post(
                '/answer_question',
                data={
                    'question_id': question['question_id'],
                    'user_answer': user_answer
                }
            )
            print(response.json)
            assert response.status_code == 200
            assert response.json['success'] == True

        
if __name__ == "__main__":
    unittest.main()