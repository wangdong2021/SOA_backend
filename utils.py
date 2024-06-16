from collections import defaultdict
import pickle
from llmsherpa.readers import LayoutPDFReader, Document
from zhipuai import ZhipuAI
import os
import json
from pathlib import Path
import random
import time
from concurrent.futures import ThreadPoolExecutor
from constants import BAD_REVIEWS, GOOD_REVIEWS, PASSED_SCORE, MAX_ARTICLE_WORDS, MAX_PROBLEM_GEN_TRIES, PROBLEM_NUM_PER_TYPE, DOCUMENT_DIR_PREFIX, USE_CACHE, CACHE_FILE_DICT
from threading import Semaphore


# Global variables
API_KEY = os.environ.get("API_KEY")
assert API_KEY is not None, "You must export the variable API_KEY in your os environment"
CLIENT = ZhipuAI(api_key=API_KEY)

LLMSERPA_API_URL = "https://readers.llmsherpa.com/api/document/developer/parseDocument?renderFormat=all"

SEMAPHORE = Semaphore(16)


def PROBLEM_CHOICE_PROMPT(text, num):
    return f"{text.strip()}\n\n" + "以上是一篇arxiv论文，你是一位博士生导师，请向你的博士生提出" + str(num) + "道四选一选择题，考察他对论文的掌握程度，并给出答案。考察对论文宏观的理解把握，不要考察能简单根据图表回答的问题。你的问题应该有足够的多样性。你的问题格式应该【严格采用json格式】，不要有多余的字眼：\
\n[{'问题': **, 'A': *, 'B', *, 'C': *, 'D': *, '正确答案': *}, ...]"

def PROBLEM_TF_PROMPT(text, num):
    return f"{text.strip()}\n\n" + "以上是一篇arxiv论文，你是一位博士生导师，请向你的博士生提出" + str(num) + "道判断题，考察他对论文的掌握程度，并给出答案（用正确/错误表示）。考察对论文宏观的理解把握，不要考察能简单根据图表回答的问题。你的问题应该有足够的多样性，问题应该是一个【陈述句】。你的问题格式应该【严格采用json格式】，不要有多余的字眼：\
\n[{'问题': **, '答案': *}, ...]"

def PROBLEM_BLANK_PROMPT(text, num):
    return f"{text.strip()}\n\n" + "以上是一篇arxiv论文，你是一位博士生导师，请向你的博士生提出" + str(num) + "道填空题，其中每一道题只能有一个空，用下划线表示，考察他对论文的掌握程度，并给出答案。考察对论文宏观的理解把握，不要考察能简单根据图表回答的问题。你的问题应该有足够的多样性，问题的【答案长度不超过20】。你的问题格式应该【严格采用json格式】，不要有多余的字眼：\
\n[{'问题': **, '答案': *}, ...]"

def PROBLEM_SUM_PROMPT(text, num):
    return f"{text.strip()}\n\n" + "以上是一篇arxiv论文的一部分，请你详细介绍该部分的内容，你的回复不少于300字。你的回复格式应该【严格采用json格式】，不要有多余的字眼：\
\n{'总结': **}"

def PROBLEM_REVIEW_PROMPT(text, num):
    return f"{text.strip()}\n\n" + "以上是一篇arxiv论文的简要总结，你是一位该领域的审稿人，请你指出该论文的优点和缺点。注意，在分析缺点时，由于只给出了总结，你应该考虑总结中内容的缺点，而不要考虑总结中缺失或者未详细说明的内容。你的回复格式应该【严格采用json格式】，不要有多余的字眼：\
\n{'优点': [**, **, ...], '缺点': [**, **, ...]}"

REVIEW_QUESTION = "在通读文章后，请你指出该论文的优点和缺点。"

def JUDGE_ANSWER_PROMPT(user_answer: str, standard_answer: str, prior_knowledge: str=None):
    prior_knowledge = "" if prior_knowledge is None else f"你的学生在阅读了一篇论文后写下了他对这个论文的一个总结, 这篇论文的摘要为{prior_knowledge}. "
    return f"你是一个博士生导师, {prior_knowledge}你的学生的回答如下: {user_answer}\n一个标准的回答是：{standard_answer}\n" + "请你给出对你的学生回答内容的评价, 注意你应该模拟面对面与学生交谈的口吻回答, 并且注意标准答案实际上是你阅读完论文后的回答, 请不要生硬的在评价中提及,【严格采用json格式】：\
\n{'评分': **, '评价': **}, " + f"注意你的评分应该是一个0-100的整数。并且如果你的评分大于{PASSED_SCORE}，那么我会认为你大致认可你的学生的回答。"

PROBLEM_PROMPT_FUNC = {
    "choice": PROBLEM_CHOICE_PROMPT,
    "tf": PROBLEM_TF_PROMPT,
    "blank": PROBLEM_BLANK_PROMPT,
    "sum": PROBLEM_SUM_PROMPT,
    "review": PROBLEM_REVIEW_PROMPT
}

def jsonfy_response(response):
    begin_index1 = response.find('[')
    begin_index2 = response.find('{')
    if begin_index1 == -1 or begin_index2 == -1:
        begin_index = max(begin_index1, begin_index2)
    else:
        begin_index = min(begin_index1, begin_index2)
    begin_index = max(begin_index, 0)
    end_index1 = response.rfind(']')
    end_index2 = response.rfind('}')
    end_index = max(end_index1, end_index2)
    if end_index == -1:
        end_index = len(response)
    else:
        end_index += 1
    response = response[begin_index:end_index]
    response = response.replace('True', 'true').replace('False', 'false')
    lines = response.split('\n')
    for line in lines:
        if line.strip().startswith("//") or line.strip().startswith("..."):
            response = response.replace(line, '')
    return json.loads(response.replace("'", '"'))


# Functions
def _get_response(prompt: str):
    with SEMAPHORE:
        response = CLIENT.chat.completions.create(
            model="glm-4",
            messages=[
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content

def get_response(prompt: str, problem_type: str, use_cache=USE_CACHE):
    if not use_cache:
        return _get_response(prompt)
    cache_file_path = CACHE_FILE_DICT[problem_type]
    if not os.path.exists(cache_file_path):
        cache = {}
    else:
        with open(cache_file_path, "r") as f:
            cache = json.load(f)
    if prompt in cache:
        return cache[prompt]
    else:
        cache[prompt] = _get_response(prompt)
        with open(cache_file_path, "w") as f:
            json.dump(cache, f)
        return cache[prompt]

def get_json_response_with_max_try(prompt: str, check_response=lambda x: True, max_try: int=MAX_PROBLEM_GEN_TRIES):
    for i in range(max_try):
        try:
            response = get_response(prompt, 'judge', use_cache=(USE_CACHE and i == 0))
            data = jsonfy_response(response)
            if check_response(data):
                return data
        except:
            continue
    return None

def update_cache(prompt, problem_type, update_content: list | str):
    with open(CACHE_FILE_DICT[problem_type], "r") as f:
        cache: dict = json.load(f)
    if problem_type == "sum" or problem_type == "review":
        if not isinstance(update_content, list) or len(update_content) != 1:
            cache.pop(prompt)
        else:
            cache[prompt] = json.dumps(update_content[0])
    elif problem_type == "choice" or problem_type == "tf" or problem_type == "blank":
        if not isinstance(update_content, list):
            cache.pop(prompt)
        else:
            cache[prompt] = json.dumps(update_content)
    else:
        cache[prompt] = update_content
    with open(CACHE_FILE_DICT[problem_type], "w") as f:
        json.dump(cache, f)

def word_count(text):
    return len(text.split())

def check_max_word(text: str) -> bool:
    return word_count(text) > MAX_ARTICLE_WORDS

def decode_pdf(pdf_url: str) -> Document:
    pdf_reader = LayoutPDFReader(LLMSERPA_API_URL)
    doc = pdf_reader.read_pdf(pdf_url)
    return doc

def save_pdf_text_chunks(doc: Document, save_dir: str | Path) -> list[str]:
    """
    save the document text chunks to the save_dir
    args:
        doc: the Document object which decoded from pdf
        save_dir: the dir to save the text chunks 
    return:
        the list of the saved text chunks's path
    """
    os.makedirs(save_dir, exist_ok=True)
    text = ""
    now_flag = ""
    chunk_text_list = []
    for chunk in doc.chunks():
        t = chunk.to_context_text()
        if t.split("\n", 1)[0].strip() == "References":
            break
        if t.split("\n", 1)[0].strip() != now_flag:
            s = t + "\n\n"
        else:
            s = t.split("\n", 1)[1] + "\n"
        if word_count(text + s) > MAX_ARTICLE_WORDS:
            chunk_text_list.append(text.strip())
            while word_count(s) > MAX_ARTICLE_WORDS:
                chunk_text_list.append(" ".join(s.split()[:MAX_ARTICLE_WORDS]))
                s = " ".join(s.split()[MAX_ARTICLE_WORDS:])
            text = s
        else:
            text += s
        now_flag = t.split("\n", 1)[0].strip()
    chunk_text_list.append(text.strip())
    chunk_path_list = []
    for i in range(len(chunk_text_list)):
        chunk_path = os.path.join(save_dir, f"chunk{i}.txt")
        chunk_path_list.append(chunk_path)
        with open(chunk_path, "w+", encoding='utf-8') as f:
            f.write(chunk_text_list[i])
    return chunk_path_list

def chunk_id_to_chunk_name(chunk_id: int) -> str:
    return f"chunk{chunk_id}.txt"

def chunk_name_to_chunk_id(chunk_name: str) -> int:
    return int(chunk_name.split(".")[0].replace("chunk", ""))

def get_arxiv_id_from_link(link: str) -> str:
    arxiv_id = link.split("/")[-1]
    return arxiv_id



# def calculate_similarity(user_answer: str, standard_answer: str) -> float:
#     # text_tokens = clip.tokenize([user_answer, standard_answer], truncate=True).to(device)
#     text_features: torch.Tensor = model.forward([user_answer, standard_answer], tokenizer)
#     text_features /= text_features.norm(dim=-1, keepdim=True)
#     similarity = torch.matmul(text_features, text_features.T)
#     text_similarity = similarity[0, 1].item()
#     return text_similarity


def _judge_answer(user_answer: str, standard_answer: str, prior_knowledge: str=None) -> tuple[int, str]:
    """
    args:
        user_answer: str the user's answer
        standard_answer: str the standard answer
    return:
        score: int the score of the answer
        passed: bool whether the answer passed the test
        review: str the review of the answer
    """
    def check_response_judge(data) -> bool:
        if '评分' in data and '评价' in data:
            score = data['评分']
            review = data['评价']
            if isinstance(review, str):
                if isinstance(score, int) or isinstance(score, float):
                    return True
                if isinstance(score, str):
                    try:
                        score = int(float(score))
                        return True
                    except:
                        return False

    prompt = JUDGE_ANSWER_PROMPT(user_answer, standard_answer, prior_knowledge)
    response_dict = get_json_response_with_max_try(prompt, check_response_judge)
    if response_dict is None:
        return None, None
    return int(float(response_dict['评分'])), response_dict['评价']

def judge_answer(user_answer: str, standard_answer: str, prior_knowledge: str=None) -> tuple[int, str]:
    score, review = _judge_answer(user_answer, standard_answer, prior_knowledge)
    # if score is None:
    #     score = calculate_similarity(user_answer, standard_answer) * 100
    #     score = int(score)
    #     passed = score > PASSED_SCORE
    #     review = random.choice(GOOD_REVIEWS if passed else BAD_REVIEWS)
    
    return score, review

def process_json(problem):
    try:
        return json.loads(problem.replace("'", '"').strip(), strict=False)
    except:
        problem = problem.replace("```json", '').replace("```", "").strip()
        return json.loads(problem.replace("'", '"').strip(), strict=False)
            
            
def check_problem_format(problem, problem_type):
    try:
        data = process_json(problem)
        formated_data = []
        if problem_type == "choice":
            for d in data:
                if not ("问题" in d and "A" in d and "B" in d and "C" in d and "D" in d and "正确答案" in d):
                    continue
                if d["正确答案"] not in ["A", "B", "C", "D"]:
                    continue
                formated_data.append(d)
        elif problem_type == "tf":
            for i in range(len(data)):
                d = data[i]
                if not ("问题" in d and "答案" in d):
                    continue
                if d["答案"] not in ["正确", "错误"]:
                    if "true" in d["答案"].lower():
                        data[i]["答案"] = "正确"
                    elif "false" in d["答案"].lower():
                        data[i]["答案"] = "错误"
                    elif "对" in d["答案"]:
                        data[i]["答案"] = "正确"
                    elif "错" in d["答案"]:
                        data[i]["答案"] = "错误"
                    else:
                        continue
                formated_data.append(data[i])
        elif problem_type == "blank":
            for d in data:
                if not ("问题" in d and "答案" in d):
                    continue
                if len(d["答案"]) > 20:
                    continue
                formated_data.append(d)
        elif problem_type == "review":
            if not ("优点" in data and "缺点" in data):
                raise ValueError("Invalid json format")
            formated_data = data
        elif problem_type == "sum":
            if not ("总结" in data):
                raise ValueError("Invalid json format")
            formated_data = data
        if not formated_data:
            raise ValueError("Invalid json format")
        return formated_data
    except:
        # print(problem)
        raise ValueError("Invalid json format")

def get_problems(text, problem_type, num):
    # 得到模型回复，并解码json, 如果失败重复到最大次数，这里保证返回的长度在0-num之间，且0的情况是重复了最大次数的
    try:
        func = PROBLEM_PROMPT_FUNC[problem_type]
        prompt = func(text, num)
    except:
        raise ValueError("Invalid problem type")
    problems = []
    for i in range(MAX_PROBLEM_GEN_TRIES):
        try:
            response = get_response(prompt, problem_type, use_cache=(USE_CACHE and i == 0))
            problem_data = check_problem_format(response, problem_type)
            if type(problem_data) == list:
                problems.extend(problem_data)
            else:
                problems.append(problem_data)
            if len(problems) >= num:
                break
        except Exception as e:
            continue
    if USE_CACHE:
        update_cache(prompt, problem_type, problems)
    return problems[:num]

def get_problem_for_each_article_per_type(chunks: list[str], problem_type: str, nums: int)-> tuple[tuple[list, list[int]], str]:
    # 对于每个chunk分配问题，总共得到PROBLEM_NUM_PER_TYPE个问题，所以每个chunk得到PROBLEM_NUM_PER_TYPE/len(chunks)个问题。
    # 如果PROBLEM_NUM_PER_TYPE不能整除len(chunks)，则最后一个chunk得到的问题数为PROBLEM_NUM_PER_TYPE%len(chunks) + PROBLEM_NUM_PER_TYPE//len(chunks)
    # 如果PROBLEM_NUM_PER_TYPE < len(chunks)，则随机sample PROBLEM_NUM_PER_TYPE个chunk
    chunks = list(enumerate(chunks))
    if len(chunks) <= nums:
        chunks_sample = chunks
    else:
        chunks_sample = random.sample(chunks, nums)
        
    problems = []
    chunk_index_list = []
    for i, (chunk_index, chunk) in enumerate(chunks_sample):
        num = nums // len(chunks_sample)
        if i == 0:
            num += nums % len(chunks_sample)
        problems.extend(get_problems(chunk, problem_type, num))
        chunk_index_list.extend([chunk_index] * num)
    return (problems, chunk_index_list), problem_type

def get_problems_for_article(chunks):
    # problems = {
    #     key : [] for key in ["choice", "tf", "blank"]
    # }
    question_type_list = ['choice', 'tf', 'blank']
    problems: dict[str, list] = defaultdict(list)
    start = time.time()
    
    threads = []
    with ThreadPoolExecutor() as pool:
        for key in question_type_list:
            res = pool.submit(get_problem_for_each_article_per_type, *(chunks, key, PROBLEM_NUM_PER_TYPE))
            threads.append(res)
        summarization = ""
        threads.append(pool.submit(get_problem_for_each_article_per_type, *(chunks, "sum", len(chunks))))
    for thread in threads:
        data, key = thread.result()
        problems[key] = data if key != "sum" else data[0]
        
    # for key in problems:
    #     problems[key] = get_problem_for_each_article_per_type(chunks, key, PROBLEM_NUM_PER_TYPE)[0]
    
    # summarization = ""
    # problems['sum'], _ = get_problem_for_each_article_per_type(chunks, "sum", len(chunks))[0]

    print(f"time: {time.time() - start}")
        
    for data in problems["sum"]:
        summarization += data["总结"]
    if not summarization:
        summarization = chunks[0]
    problems["review"] = get_problems(summarization, "review", 1) # TODO: 如果模型说不出优缺点，这里处理不了
    
    questions = []
    chunk_index_list = []
    # 按 choice, tf, blank, review的顺序排列
    # question_content, standard_answer
    for i, key in enumerate(["choice", "tf", "blank"]):
        for data, chunk_index in zip(*problems[key]):
            questions.append({
                "question_content": data["问题"] if key != "choice" else data["问题"] + f"\nA. {data['A']}\nB. {data['B']}\nC. {data['C']}\nD. {data['D']}", # TODO: 前端如果觉得这样解析有困难再改
                "standard_answer": data["正确答案"] if key == "choice" else data["答案"],
                "question_type": i
            })
            chunk_index_list.append(chunk_index)
            
    for data in problems["review"]:
        questions.append({
            "question_content": REVIEW_QUESTION,
            "standard_answer": f"优点: {'；'.join(data['优点'])}\n缺点: {'；'.join(data['缺点'])}", # TODO: 前端如果觉得这样解析有困难再改
            "question_type": 3
        })
        chunk_index_list.append(-1)
    return questions, chunk_index_list
 