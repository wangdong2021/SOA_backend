import os

PASSED_SCORE = 85

SIMILARITY_THRESHOLD = 0.8

MAX_ARTICLE_WORDS = int(6000 * 0.75 - 500)

MAX_PROBLEM_GEN_TRIES = 3

PROBLEM_NUM_PER_TYPE = 3

# TODO set the secret key to a random string which is hard to guess
SECRET_KEY = 'mysecretkey'

SQLALCHEMY_TRACK_MODIFICATIONS = False

STATIC_PREFIX = "./data/read-hub/"

SQLALCHEMY_DATABASE_URI = 'sqlite:///site.db'

TIME_ZONE = 'Asia/Shanghai'

DOCUMENT_DIR_PREFIX = os.path.join(STATIC_PREFIX, "documents")

RESPONSE_CACHE_FILE = os.path.join(STATIC_PREFIX, "response_cache.json")

CACHE_FILE_DICT = {
    'choice': os.path.join(STATIC_PREFIX, "choice_cache.json"),
    'tf': os.path.join(STATIC_PREFIX, "tf_cache.json"),
    'blank': os.path.join(STATIC_PREFIX, "blank_cache.json"),
    'sum': os.path.join(STATIC_PREFIX, "summary_cache.json"),
    'review': os.path.join(STATIC_PREFIX, "review_cache.json"),
    'judge': os.path.join(STATIC_PREFIX, "judge_cache.json"),
}

# TODO In the production environment, set USE_CACHE to False
USE_CACHE = False

# TODO this setting will disable the user system, and all the requests will be treated as the default user
# in the production environment, set USE_DEFAULT_USER to False
USE_DEFAULT_USER = False

USE_LOW_USER_AUTHORIZATION = True

DEFAULT_PDF_NUMBER_PER_PAGE = 20

GOOD_REVIEWS = ["你的回答基本正确", "你的回答很好", "你的回答非常好"]

BAD_REVIEWS = ["你的回答不正确", "你的回答不够好", "你的回答不够详细"]

os.makedirs(DOCUMENT_DIR_PREFIX, exist_ok=True)


SEARCH_PAPER_NUM = 20

CHOSE_PAPER_NUM = 10

ARXIV_LIMIT_TIME_PER_REQUEST = 2
