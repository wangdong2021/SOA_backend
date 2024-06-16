import os
from pathlib import Path
import pickle
from constants import CHOSE_PAPER_NUM, DOCUMENT_DIR_PREFIX, SEARCH_PAPER_NUM
import feedparser
from utils import decode_pdf, get_json_response_with_max_try, get_arxiv_id_from_link, save_pdf_text_chunks

def parse_entry(entry):
    pdf_link = None
    for link_info in entry.links:
        if link_info['type'] == 'application/pdf':
            pdf_link = link_info['href']
            break
    else:
        # TODO log something here
        pdf_link = entry.links[0]['href']
    return {
        'title': entry.title.replace("\n", ""), 
        'link': pdf_link,
        'date': entry.published.split('T')[0].strip(),
        'authors': [author['name'] for author in entry.authors],
        'id': get_arxiv_id_from_link(pdf_link),
        'abstract': entry.summary
    }


def parse_entries(data) -> list[dict[str, str]]:
    paper_info_list = []
    for entry in data.entries:
        paper_info_list.append(parse_entry(entry))
    return paper_info_list


def get_arxiv_response(url):
    data = feedparser.parse(url)
    return data


def get_base_info_with_paper_id(paper_id: str):
    """get the abstract, title, authors, date, link, id of the paper with the paper_id
    Args:
        paper_id (str): like 2309.10305
    Returns:
        data (dict): key-value pairs of the abstract, title, authors, date, link, id of the paper
    """
    api_query = f'http://export.arxiv.org/api/query?id_list={paper_id}'
    data = get_arxiv_response(api_query)
    if len(data.entries) == 0:
        return data
    entry = data.entries[0]
    return parse_entry(entry)


# 获取arxiv的api接口
def get_arxiv_search_url(search_labels: list[str], start_index: int = 0, max_results: int = 10):
    url_base = "http://export.arxiv.org/api/query?search_query="
    search_query_list = []
    for label in search_labels:
        label_search = []
        for key_word in label.split(' '):
            label_search.append(f"(all:{key_word}+OR+all:{key_word.capitalize()})")
        search_query_list.append(f"({'+AND+'.join(label_search)})")
    search_query = f"({'+OR+'.join(search_query_list)})"
    return f"{url_base}{search_query}&start={start_index}&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"


def get_paper_info_list(person_labels: list[str], exists_ids: list[str] = [], search_paper_num: int=SEARCH_PAPER_NUM) -> list[dict[str, str]]:
    papers = []
    start_index = 0
    while len(papers) < search_paper_num:
        arxiv_search_url = get_arxiv_search_url(person_labels, start_index=start_index, max_results=search_paper_num)
        search_data = get_arxiv_response(arxiv_search_url)
        paper_info_list = parse_entries(search_data)
        
        if len(paper_info_list) == 0:
            break
        start_index += len(paper_info_list)
        for paper_info in paper_info_list:
            if get_arxiv_id_from_link(paper_info['link']) not in exists_ids:
                papers.append(paper_info)
    return papers[:search_paper_num]


def paper_info_to_str(paper_info: dict[str, str]):
    return f"""
{{
    "paper_id": "{paper_info['id']}",
    "paper_title": "{paper_info['title']}",
    "paper_date": "{paper_info['date']}",
    "paper_abstract": "{paper_info['abstract']}",
}}"""

def get_recommendation_prompt(paper_info_list: list[dict[str, str]], person_labels: list[str], person_description: str, chose_number: int=CHOSE_PAPER_NUM):
    return \
f"""我是一名学生, 我最近在研究{', '.join(person_labels)}方面的内容, 我对这个领域的研究很感兴趣, 以下是我的一些描述信息
{person_description}
我最近看到了下面这一些论文, 但是论文数目太多, 我没有时间阅读这么多, 请你根据这些论文的摘要, 帮我筛选出和我研究的内容最相关的{chose_number}篇论文. 注意你需要考虑到论文的时效性.
[{
    ', '.join([paper_info_to_str(paper_info) for paper_info in paper_info_list])    
}]
注意, 你应该以一个python 列表的格式输出你的答案, 列表中的每一项都是一个如下的字典
{{
    "paper_id": "论文的id",
    "reason": "筛选这篇论文的原因"
}}
你输出的内容需要能够被 json.loads 函数解析, 注意不要输出列表之外的其他内容.
"""


def filter_the_papers(paper_info_list: list[dict[str, str]], person_labels: list[str], person_description: str, chose_paper_num: int=CHOSE_PAPER_NUM) -> list[dict[str, str]]:
    def check_response_data(data: list[dict[str, str]]):
        if not isinstance(data, list):
            return False
        for item in data:
            if not isinstance(item, dict):
                return False
            if 'paper_id' not in item or 'reason' not in item:
                return False
            if not isinstance(item['paper_id'], str) or not isinstance(item['reason'], str):
                return False
        return True
    
    if len(paper_info_list) < chose_paper_num:
        return paper_info_list
    all_paper_id_list = [paper_info['id'] for paper_info in paper_info_list]
    paper_id_to_info = {paper_info['id']: paper_info for paper_info in paper_info_list}
    all_paper_ids = set(all_paper_id_list)
    selected_paper_ids = set()
    while len(selected_paper_ids) < chose_paper_num:
        prompt_paper_ids = set(all_paper_ids) - selected_paper_ids
        prompt_paper_info_list = [paper_id_to_info[paper_id] for paper_id in sorted(all_paper_id_list) if paper_id not in selected_paper_ids]
        prompt = get_recommendation_prompt(prompt_paper_info_list, person_labels, person_description, chose_paper_num - len(selected_paper_ids))
        data = get_json_response_with_max_try(prompt, check_response_data)
        if data is None:
            break
        response_paper_ids = set([item['paper_id'] for item in data])
        response_paper_ids = response_paper_ids & prompt_paper_ids
        if len(response_paper_ids) == 0:
            break
        selected_paper_ids |= response_paper_ids
    return [paper_id_to_info[paper_id] for paper_id in selected_paper_ids]
    

def get_recommendation_paper_info_list(person_labels: str, person_description: str, exist_ids: list[str]=[], search_paper_num: int=SEARCH_PAPER_NUM, chose_paper_num: int=CHOSE_PAPER_NUM) -> list[dict[str, str]]:
    paper_info_list = get_paper_info_list(person_labels, exist_ids, search_paper_num)
    if len(paper_info_list) < chose_paper_num:
        return paper_info_list
    try:
        return filter_the_papers(paper_info_list, person_labels, person_description, chose_paper_num)
    except Exception as e:
        print(f"Error: {e}")
        return paper_info_list[:chose_paper_num]

class Document_Reader:
    def __init__(self, pdf_url: str):
        self.arxiv_id = get_arxiv_id_from_link(pdf_url)
        self.init_document_info()
        
    def init_paper_info(self, paper_info: dict[str, str]):
        self.title = paper_info['title']
        self.abstract = paper_info['abstract']
        self.authors = paper_info['authors']
        self.date = paper_info['date']
        self.link = paper_info['link']
                
    def init_document_info(self):
        file_name = f"{self.arxiv_id}.pkl"
        save_doc_cache_path = os.path.join(DOCUMENT_DIR_PREFIX, file_name)
        if os.path.exists(save_doc_cache_path):
            with open(save_doc_cache_path, "rb") as f:
                document_data: dict = pickle.load(f)
            self.doc = document_data.pop("doc")
            self.init_paper_info(document_data)
        else:
            paper_info = get_base_info_with_paper_id(self.arxiv_id)
            self.init_paper_info(paper_info)
            self.doc = decode_pdf(self.link)
            
            paper_info['doc'] = self.doc
            with open(save_doc_cache_path, "wb") as f:
                pickle.dump(paper_info, f)
        
    def save_pdf_chunks(self, save_dir: str | Path) -> list[str]:
        return save_pdf_text_chunks(self.doc, save_dir)
    
    @staticmethod
    def get_chunk_text(chunk_path: str | Path) -> str:
        with open(chunk_path, "r", encoding='utf-8') as f:
            return f.read()
