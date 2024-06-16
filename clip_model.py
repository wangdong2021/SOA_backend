from transformers import BertTokenizerFast
from component.model import BertCLIPTextModel
import torch
from multilingual_clip import pt_multilingual_clip
import transformers
import clip

device = "cuda" if torch.cuda.is_available() else "cpu"

def calculate_similarity(text_features: torch.Tensor) -> float:
    text_features /= text_features.norm(dim=-1, keepdim=True)
    similarity = torch.matmul(text_features, text_features.T)
    text_similarity = similarity[0, 1].item()
    return text_similarity

class Chinese_Clip:
    model_name = 'YeungNLP/clip-vit-bert-chinese-1M'
    def __init__(self) -> None:
        self.model = BertCLIPTextModel.from_pretrained(self.model_name).to(device)
        self.tokenizer = BertTokenizerFast.from_pretrained(self.model_name)
        self.model.eval()

    @torch.no_grad()
    def calculate_similarity(self, text1: str, text2: str) -> float:
        inputs = self.tokenizer([text1, text2], return_tensors='pt', padding=True).to(device)
        inputs.pop('token_type_ids')
        outputs = self.model(**inputs)
        text_embeds = outputs.pooler_output
        return calculate_similarity(text_embeds)

class Multi_Clip:
    model_name = 'M-CLIP/XLM-Roberta-Large-Vit-L-14'
    def __init__(self) -> None:
        self.model = pt_multilingual_clip.MultilingualCLIP.from_pretrained(self.model_name)
        self.tokenizer = transformers.AutoTokenizer.from_pretrained(self.model_name)
        self.model.to(device)
        self.model.eval()
        
    @torch.no_grad()
    def forward(self, texts: list[str]):
        txt_tok = self.tokenizer(texts, padding=True, return_tensors='pt')
        txt_tok.to(device)
        embs: torch.Tensor = self.model.transformer(**txt_tok)[0]
        att: torch.Tensor = txt_tok['attention_mask']
        embs = (embs * att.unsqueeze(2)).sum(dim=1) / att.sum(dim=1)[:, None]
        return self.model.LinearTransformation(embs)
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        text_features: torch.Tensor = self.forward([text1, text2])
        return calculate_similarity(text_features)

class Clip:
    model_name = "ViT-B/32"
    def __init__(self):
        self.model, _ = clip.load(self.model_name, device=device)
        self.model.eval()
    
    @torch.no_grad()
    def calculate_similarity(self, text1: str, text2: str) -> float:
        text_features = clip.tokenize([text1, text2], truncate=True).to(device)
        text_features = self.model.encode_text(text_features)
        return calculate_similarity(text_features)
    
if __name__ == "__main__":
    text1 = "you are right"
    text2 = 'you are wrong'
    c = Chinese_Clip()
    print(c.calculate_similarity(text1, text2))
