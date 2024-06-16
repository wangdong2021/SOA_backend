from utils import get_json_response_with_max_try, jsonfy_response, check_max_word, get_response


profile_prompt = """
你是一个用户画像系统, 你需要根据我提供的用户信息, 生成一个用户画像.
已知这个用户读过的书籍信息如下:
{documents}
请你按照以下格式为我生成用户画像. 你需要返回一个字典, 其中包含以下字段:
{{
    "领域": ["领域 1", "领域 2", "领域 3", ...], # 从文章中总结出用户的研究领域
    "描述": "用户的描述信息", # 从用户读过的文章中总结出用户的描述信息, 可以包括研究方向, 感兴趣的内容以及阅读深度等等
}}
注意你必须输出【英文】, 且你应当只返回这个字典不应该有其他输出
You must output in English, and you should only return this dictionary without any other output.
"""

def get_user_profile_prompt(documents: list[tuple[str, str]]) -> dict:
    """
    Generate user profile based on the documents the user has read
    Args:
        documents: a list of tuples, each tuple contains the title and content of a document
    """
    for i in range(len(documents), -1, -1):
        # the first i element use content in summary, the rest use title in summary
        summary = [doc[1] for doc in documents[:i]] + [doc[0] for doc in documents[i:]]
        summary = "\n".join(summary)
        if not check_max_word(summary):
            break
    else:
        for i in range(len(documents), -1, -1):
            # use title for the first i elements
            summary = [doc[0] for doc in documents[:i]]
            summary = "\n".join(summary)
            if not check_max_word(summary):
                break
        else:
            raise ValueError("The documents are too long")
    return profile_prompt.format(documents=summary)

def get_user_profile_response(documents: list[tuple[str, str]]) -> tuple[list[str], str]:
    def check_profile_data(data: dict):
        if not isinstance(data, dict):
            return False
        if '领域' not in data or '描述' not in data:
            return False
        if not isinstance(data['领域'], list) or not isinstance(data['描述'], str):
            return False
        return all(isinstance(item, str) for item in data['领域'])
    prompt = get_user_profile_prompt(documents)
    data = get_json_response_with_max_try(prompt, check_profile_data)
    if data is None:
        return None, None
    return data['领域'], data['描述']
