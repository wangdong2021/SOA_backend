from flask import Flask, request, jsonify
from arxiv import get_recommendation_paper_info_list, Document_Reader
from models import *
from flask_cors import CORS
from flask_bcrypt import Bcrypt
import os
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
import uuid
from user_profile import get_user_profile_response
from utils import get_problems_for_article
from constants import CHOSE_PAPER_NUM, DEFAULT_PDF_NUMBER_PER_PAGE, STATIC_PREFIX, DOCUMENT_DIR_PREFIX, SECRET_KEY, SQLALCHEMY_DATABASE_URI, TIME_ZONE, SQLALCHEMY_TRACK_MODIFICATIONS, USE_DEFAULT_USER, USE_LOW_USER_AUTHORIZATION
from functools import wraps
from error_message import *

app = Flask(__name__, static_folder=STATIC_PREFIX)
# TODO change the secret key
app.config['SECRET_KEY'] = SECRET_KEY
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = SQLALCHEMY_TRACK_MODIFICATIONS
app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
app.config['TIME_ZONE'] = TIME_ZONE

# CORS(app, resources={r"/*": {"origins": ["http://localhost:8080", "http://192.168.180.65:8080"], "supports_credentials": True}})
# CORS(app, supports_credentials=True)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

bcrypt = Bcrypt(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id: int):
    return db.session.get(User, int(user_id))

# @app.route('/get_default_user')
def get_default_user():
    return User.query.filter_by(username='default').first()

def add_default_user():
    if User.query.filter_by(username='default').first() is None:
        default_user = User(
            username='default',
            password_hash=bcrypt.generate_password_hash('default').decode('utf-8'),
            email='default'
        )
        db.session.add(default_user)
        db.session.commit()

def handle_error(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            func_ret = func(*args, **kwargs)
            if func_ret is None or isinstance(func_ret, str):
                db.session.rollback()
                return jsonify({'success': False, 'message': func_ret or "Unknown error"})
            else:
                return func_ret
        except Exception as e:
            db.session.rollback()
            print(str(e))
            # TODO Note that the exception message should not be returned to the front end in the production environment
            return jsonify({'success': False, 'message': str(e)})
    return wrapper

def identity_wrapper(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper

def low_user_authorization_wrapper(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if get_logined_user():
            return func(*args, **kwargs)
        return jsonify({'success': False, 'message': 'The user system is disabled'})
    return wrapper

if USE_DEFAULT_USER:
    login_wrapper = identity_wrapper
elif USE_LOW_USER_AUTHORIZATION:
    login_wrapper = low_user_authorization_wrapper
else:
    login_wrapper = login_required

def get_logined_user() -> User | None:
    if USE_DEFAULT_USER:
        return get_default_user()
    elif USE_LOW_USER_AUTHORIZATION:
        if request.method == "GET":
            username = request.args.get('myusername')
        elif request.method == "POST":
            username = request.form.get('myusername')
        else:
            raise ValueError("Unsupported request method")
        return User.query.filter_by(username=username).first()
    else:
        return current_user

@app.route('/login', methods=['POST'])
@handle_error
def login():
    """
    args:
        username: str
        password: str
    return:
        username: str
        email: str
        id: int
        success: bool (True if login successfully)
    """
    username = request.form.get('username')
    password = request.form.get('password')
    if not username or not password:
        return FORM_NOT_COMPLETE
    user: User = User.query.filter_by(username=username).first()
    if user and bcrypt.check_password_hash(user.password_hash, password):
        login_user(user)
        return jsonify({
            'username': user.username,
            'email': user.email,
            'id': user.id,
            'success': True
        })
    elif user is None:
        return USERNAME_NOT_FOUND
    else:
        return WRONG_PASSWORD

@app.route('/register', methods=['POST'])
@handle_error
def register():
    """
    args:
        username: str
        email: str
        password: str
    return:
        success: bool (True if register successfully)
        username: str (username if success)
        email: str (email if success)
        message: str (error message if failed)        
    """
    username = request.form.get('username')
    email = request.form.get('email')
    password = request.form.get('password')
    if not username or not password:
        return FORM_NOT_COMPLETE
    user = User.query.filter_by(username=username).first()  # 查询是否已存在该用户名
    if user:
        return USERNAME_EXISTS
    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    new_user = User(username=username, email=email, password_hash=hashed_password)
    db.session.add(new_user)
    db.session.commit()
    login_user(new_user)
    return jsonify({'success': True, 'username': username, 'email': email, 'id': new_user.id})
    
@app.route('/logout')
def logout():
    logout_user()
    return jsonify({'success': True})


@app.route('/get_user_profile', methods=['GET'])
def get_user_profile():
    user = get_logined_user()
    avgscore = user.get_average_score()

    return jsonify({
        'name': user.username,
        'labels': user.labels,
        'description': user.description if user.description else 'No description.',
        'average_score': avgscore,
        'success': True
    })


def update_user_profile(user: User):
    """
    Update the user profile based on the documents the user has read
    """
    documents = user.get_summary_of_documents()
    labels, description = get_user_profile_response(documents)
    if labels is None or description is None:
        return False
    user.labels = labels
    user.description = description
    db.session.commit()
    return True


def update_recommendation(user: User):
    """update the recommendation for the user based on the user's documents
    Args:
        user (User): 
    Returns:
        _type_: 
    """
    if not (user.labels and user.description):
        return
    labels = user.labels
    description = user.description
    exists_arxiv_ids = [recommendation.arxiv_id for recommendation in user.recommendations]
    exists_arxiv_ids += [document.arxiv_id for document in user.documents if document.is_arxiv]
    recommendation_paper_info_list = get_recommendation_paper_info_list(labels, description, exists_arxiv_ids)
    for paper_info in recommendation_paper_info_list:
        recommendation = Recommendation(
            user=user,
            arxiv_id=paper_info['id'],
            title=paper_info['title'],
            date=paper_info['date'],
            abstract=paper_info['abstract'],
            link=paper_info['link'],
            authors_text=Recommendation.transform_authors_to_text(paper_info['authors'])
        )
        db.session.add(recommendation)
    db.session.commit()
    return True if recommendation_paper_info_list else False


def auto_update_user_profile():
    user = get_logined_user()
    user.upload_document_number += 1
    db.session.commit()
    if user.upload_document_number % 5 == 0 or user.upload_document_number == 1:
        update_user_profile(user)
        update_recommendation(user)
    

@app.route('/upload_document', methods=['POST'])
@login_wrapper
@handle_error
def upload_document():
    """
    1. get the file content
    2. split the file to chunks
    3. create a Document object and Chunk objects to store the file
    4. chat with GLM to get the  question templates and create QuestionTemplate objects
    
    args:
        pdf_url: str
    """
    user = get_logined_user()
    pdf_url = request.form.get('pdf_url')

    if not pdf_url:
        return FORM_NOT_COMPLETE
    doc_reader = Document_Reader(pdf_url)
    base_dir_name = str(uuid.uuid4())
    base_dir_path = os.path.join(DOCUMENT_DIR_PREFIX, base_dir_name)
    document = Document(
        user=user, base_dir=base_dir_path, title=doc_reader.title, 
        abstract=doc_reader.abstract, arxiv_id=doc_reader.arxiv_id
    )
    
    db.session.add(document)

    chunk_path_list = doc_reader.save_pdf_chunks(base_dir_path)
    for chunk_path in chunk_path_list:
        chunk = Chunk(document=document, file_path=chunk_path)
        db.session.add(chunk)

    db.session.commit()
    auto_update_user_profile()
    return jsonify({'success': True, 'document_id': document.id})

@app.route('/get_documents', methods=['GET'])
@login_wrapper
def get_documents():
    """
    Args:
        pdf_number_per_page: optional, int
        page_index: optional, int
    return:
        documents: list[dict]
        success: bool
    """
    user = get_logined_user()
    pdf_number_per_page = request.args.get('pdf_number_per_page', DEFAULT_PDF_NUMBER_PER_PAGE)
    page_index = int(request.args.get('page_index', 0))
    documents: list[Document] = Document.query.filter_by(user=user).order_by(Document.created_time).all()[::-1]
    total_document_number = len(documents)
    total_page_number = (total_document_number + pdf_number_per_page - 1) // pdf_number_per_page
    documents = documents[page_index * pdf_number_per_page: (page_index + 1) * pdf_number_per_page]
    document_data_list: list[dict] = []
    for document in documents:
        document_data_list.append({
            'document_id': document.id,
            'title': document.title,
            'created_time': document.created_time.timestamp()
        })
    return jsonify({
        'documents': document_data_list,
        'total_page_number': total_page_number,
        'total_document_number': total_document_number,
        'success': True
    })


@app.route('/get_recommendations', methods=['GET'])
@login_wrapper
def get_recommendations():
    """
    Return a list of recommendations
    """
    user = get_logined_user()
    document_arxiv_ids = [document.arxiv_id for document in user.documents if document.is_arxiv]
    # remove the recommendations that are in the user's documents
    to_be_removed_recommendations = Recommendation.query.filter(Recommendation.user == user, Recommendation.arxiv_id.in_(document_arxiv_ids)).all()
    for recommendation in to_be_removed_recommendations:
        db.session.delete(recommendation)
    db.session.commit()
    # filter the recommendations arxiv id that are in the user's documents
    recommendations = Recommendation.query.filter_by(user=user).order_by(Recommendation.created_time).all()[::-1][:CHOSE_PAPER_NUM]
    
    return jsonify({
        'recommendations': [
            {
                'arxiv_id': recommendation.arxiv_id,
                'title': recommendation.title,
                'date': recommendation.date,
                'abstract': recommendation.abstract,
                'link': recommendation.link,
                'authors': recommendation.authors
            } for recommendation in recommendations
        ],
        'success': True
    })
    
@app.route('/get_exams', methods=['GET'])
def get_exams():
    """
    Args:
        document_id: int
    Return:
        exams: list[dict]
        success: bool
    """
    document_id = request.args.get('document_id')
    document = Document.query.get(document_id)
    if document is None:
        return DOCUMENT_NOT_FOUND
    # sorted by created_time
    exams = Exam.query.filter_by(document=document).order_by(Exam.created_time).all()
    return jsonify({
        'exams': [
            {
                'exam_id': exam.id, 
                'created_time': exam.created_time.timestamp(),
                'done': exam.done,
                'done_number': exam.done_number,
                'quesiton_number': exam.question_number,
            } for exam in exams
        ],
        'success': True
    })


@app.route('/get_exam', methods=['GET'])
def get_exam():
    """
    Args:
        exam_id: int
    Return:
        questions: list[dict]
        success: bool
    """
    exam_id = request.args.get('exam_id')
    exam: Exam = Exam.query.get(exam_id)
    if exam is None:
        return EXAM_NOT_FOUND
    # sorted by created_time
    questions: list[Question] = Question.query.filter_by(exam_id=exam.id).order_by(Question.created_time).all()
    question_data_list: list[dict] = []
    for question in questions:
        question_data_list.append({
            'question_id': question.id,
            'question_type': question.question_type,
            'question_content': question.question_content,
            'done': question.done,
            'user_answer': question.user_answer,
            'score': question.score,
            'passed': question.passed,
            'created_time': question.created_time.timestamp(),
            'answer_time': question.answer_time.timestamp() if question.answer_time else None,
            'standard_answer': question.standard_answer if question.done else None,
            'review': question.standard_review
        })
    return jsonify({'questions': question_data_list, 'success': True})

@app.route('/generate_exam', methods=['POST'])
def generate_exam():
    """
    Args:
        document_id: int
    Return:
        exam_id: int
    """
    document_id = request.form.get('document_id')
    document = Document.query.get(document_id)
    if document is None:
        return DOCUMENT_NOT_FOUND
    exam = Exam(document=document)
    chunk_object_list: list[Chunk] = Chunk.query.filter_by(document=document).all()
    chunk_text_list = [chunk.chunk_text for chunk in chunk_object_list]
    question_data_list, chunk_index_list = get_problems_for_article(chunk_text_list)
    
    for question_data, chunk_index in zip(question_data_list, chunk_index_list):
        chunk_object = chunk_object_list[chunk_index] if chunk_index != -1 else None
        question = Question(
            document=document,
            exam=exam,
            chunk=chunk_object,
            question_type=question_data['question_type'],
            question_content=question_data['question_content'],
            standard_answer=question_data['standard_answer'],
        )
        db.session.add(question)
    db.session.add(exam)
    db.session.commit()
    return jsonify({'exam_id': exam.id, 'success': True})


@app.route('/answer_question', methods=['POST'])
@handle_error
def answer_question():
    """
    args:
        question_id: int
        user_answer: str
    return:
        success: bool
        score: int
        review: str | None
        passed: bool
        answer_time: datetime
    """
    question_id = request.form.get('question_id')
    user_answer = request.form.get('user_answer')
    if not question_id or not user_answer:
        return FORM_NOT_COMPLETE
    question: Question = db.session.get(Question, question_id)
    if question.done:
        return QUESTION_NOT_FOUND
    question.set_user_answer(user_answer)
    db.session.commit()
    return jsonify({
        'success': True,
        'score': question.score,
        'review': question.standard_review,
        'passed': question.passed,
        'answer_time': question.answer_time.timestamp(),
        'standard_answer': question.standard_answer
    })

if __name__ == "__main__":
    db.init_app(app)
    with app.app_context():
        db.create_all()
        add_default_user()
    
    app.run(debug=True, host='0.0.0.0', port=10086)
