from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from flask_login import UserMixin
import numpy as np
from utils import judge_answer
from constants import PASSED_SCORE
from sqlalchemy.ext.hybrid import hybrid_property

db = SQLAlchemy()

# enum for question type
class QuestionType:
    MULTIPLE_CHOICE = 0
    TRUE_OR_FALSE = 1
    FILL_IN_THE_BLANK = 2
    REVIEW = 3

QUESTION_TYPE_LIST = ['choice', 'tf', 'blank', 'review']

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=False, nullable=True)
    password_hash = db.Column(db.String(128))
    documents = db.relationship('Document', backref='user', lazy=True)
    reading_plans = db.relationship('ReadingPlan', backref='user', lazy=True)
    topics = db.relationship('Topic', backref='user', lazy=True)
    recommendations = db.relationship('Recommendation', backref='user', lazy=True)
    labels_text = db.Column(db.Text, nullable=True)
    description = db.Column(db.Text, nullable=True)
    upload_document_number = db.Column(db.Integer, default=0)

    @hybrid_property
    def labels(self) -> list[str]:
        return self.labels_text.split(',') if self.labels_text is not None else []

    @labels.setter
    def labels(self, labels: list[str]):
        self.labels_text = ','.join(labels)
        
    def get_average_score(self) -> dict[str, float]:
        question_score = np.zeros((4, 2))
        for document in self.documents:
            document: Document
            question_score += document.get_question_score()
        avarage_score = question_score[:, 0] / question_score[:, 1]
        # 如果是nan，就设置为0
        avarage_score[np.isnan(avarage_score)] = 0
        question_type_to_average_score = dict(zip(QUESTION_TYPE_LIST, avarage_score))
        return question_type_to_average_score

    def get_summary_of_documents(self) -> list[tuple[str, str]]:
        """
        Return:
            documents: list[(title, summary)], note that the list is sorted by created_time, the latest document is the first
        """
        # sorted by created_time, the latest document is the first
        documents = sorted(self.documents, key=lambda x: x.created_time, reverse=True)
        return [
            (document.title, document.abstract)
            for document in documents
        ]


class Topic(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    documents = db.relationship('Document', secondary='topic_document', back_populates='topics')

class TopicDocument(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(db.Integer, db.ForeignKey('topic.id'), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey('document.id'), nullable=False)

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    abstract = db.Column(db.Text, nullable=True)
    description = db.Column(db.Text, nullable=True)
    base_dir = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_time = db.Column(db.DateTime, default=datetime.now)
    is_arxiv = db.Column(db.Boolean, default=True)
    arxiv_id = db.Column(db.String(50), nullable=True)
    # question_templates = db.relationship('QuestionTemplate', backref='document', lazy=True)
    exams = db.relationship('Exam', backref='document', lazy=True)
    topics = db.relationship('Topic', secondary='topic_document', back_populates='documents')
    chunks = db.relationship('Chunk', backref='document', lazy=True)
    questions = db.relationship('Question', backref='document', lazy=True)
    reading_plan_id = db.Column(db.Integer, db.ForeignKey('reading_plan.id'), nullable=True, default=None)

    def get_question_score(self):
        question_score = np.zeros((4, 2))
        for question in self.questions:
            question: Question
            if question.score is not None:
                question_score[question.question_type][0] += question.score
                question_score[question.question_type][1] += 1
        return question_score
    
class Chunk(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('document.id'), nullable=False)
    file_path = db.Column(db.Text, nullable=False)
    questions = db.relationship('Question', backref='chunk', lazy=True)
    @property
    def chunk_text(self):
        with open(self.file_path, 'r', encoding='utf-8') as f:
            return f.read()
    
class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_time = db.Column(db.DateTime, default=datetime.now)
    answer_time = db.Column(db.DateTime, nullable=True)
    question_type = db.Column(db.Integer, nullable=False)
    
    question_content = db.Column(db.Text, nullable=False)
    standard_answer = db.Column(db.Text, nullable=True)
    standard_review = db.Column(db.Text, nullable=True)
    user_answer = db.Column(db.Text, nullable=True)
    score = db.Column(db.Integer, nullable=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exam.id'), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey('document.id'), nullable=False)
    # some question is belong to document summary, some is belong to chunk
    chunk_id = db.Column(db.Integer, db.ForeignKey('chunk.id'), nullable=True)
    @property
    def done(self):
        return self.answer_time is not None
    
    @property
    def passed(self):
        if self.score is None:
            return False
        else:
            return self.score > PASSED_SCORE
        
    def set_user_answer(self, user_answer: str):
        self.answer_time = datetime.now()
        self.user_answer = user_answer
        if self.question_type == QuestionType.MULTIPLE_CHOICE or self.question_type == QuestionType.TRUE_OR_FALSE:
            self.score = 100 if self.user_answer == self.standard_answer else 0
        # elif self.question_type == QuestionType.FILL_IN_THE_BLANK:
        #     self.score = 100 if calculate_similarity(self.user_answer, self.standard_answer) > SIMILARITY_THRESHOLD else 0
        # elif self.question_type == QuestionType.REVIEW:
        elif self.question_type == QuestionType.FILL_IN_THE_BLANK:
            self.score, self.standard_review = judge_answer(self.user_answer, self.standard_answer)
        elif self.question_type == QuestionType.REVIEW:
            self.score, self.standard_review = judge_answer(self.user_answer, self.standard_answer, self.document.abstract)
        else:
            raise ValueError("Invalid question type")
        
class Exam(db.Model):
    """
    contain 10 questions
    """
    id = db.Column(db.Integer, primary_key=True)
    questions = db.relationship('Question', backref='exam', lazy=True)
    document_id = db.Column(db.Integer, db.ForeignKey('document.id'), nullable=False)
    created_time = db.Column(db.DateTime, default=datetime.now)
    @property
    def done(self):
        return all(question.done for question in self.questions)
    
    @property
    def done_number(self):
        return len([question for question in self.questions if question.done])
    
    @property
    def question_number(self):
        return len(self.questions)
    
class ReadingPlan(db.Model):
    @staticmethod
    def _set_expired_time():
        return datetime.now().date() + timedelta(days=1)

    id = db.Column(db.Integer, primary_key=True)
    create_time = db.Column(db.DateTime, default=datetime.now)
    expired_time = db.Column(db.DateTime, nullable=False, default=_set_expired_time())
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    documents = db.relationship('Document', backref='reading_plan', lazy=True)

class Recommendation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_time = db.Column(db.DateTime, default=datetime.now)
    arxiv_id = db.Column(db.String(50), nullable=False)
    title = db.Column(db.Text, nullable=False)
    date = db.Column(db.Text, nullable=False)
    abstract = db.Column(db.Text, nullable=False)
    link = db.Column(db.Text, nullable=False)
    authors_text = db.Column(db.Text, nullable=False)
    
    @hybrid_property
    def authors(self):
        return self.authors_text.split(',')
    
    @authors.setter
    def authors(self, authors: list[str]):
        self.authors_text = ','.join(authors)

    @staticmethod
    def transform_authors_to_text(authors: list[str]) -> str:
        return ','.join(authors)
