"""OpenAI Responses API client; uses only Python's standard library."""
import json, os
from pathlib import Path
from urllib.request import Request, urlopen
ROOT=Path(__file__).resolve().parents[1]

def load_env(path=ROOT/".env"):
    if path.exists():
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            line=raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key,value=line.split("=",1); os.environ.setdefault(key.strip(),value.strip().strip('"').strip("'"))

def validate_output(value):
    missing={"title","grant_status","decision","decision_reason","confidence"}-value.keys()
    if missing: raise ValueError(f"agent output missing: {', '.join(sorted(missing))}")
    if not 0 <= float(value["confidence"]) <= 1: raise ValueError("confidence must be between 0 and 1")
    return value

class OpenAIAgent:
    def __init__(self, config, api_key=None):
        load_env(); self.config=config; self.api_key=api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key: raise RuntimeError("OPENAI_API_KEY is missing. Copy .env.example to .env.")
        self.prompt=(ROOT/"agent"/"prompt.md").read_text(encoding="utf-8-sig")
        self.schema=json.loads((ROOT/"agent"/"schema.json").read_text(encoding="utf-8-sig"))
    def analyze(self, *, source, url, page_text, preliminary):
        content={"source":source,"url":url,"preliminary_rule_result":preliminary,"page_text":page_text[:self.config["max_page_characters"]]}
        payload={"model":self.config["model"],"instructions":self.prompt,"input":json.dumps(content,ensure_ascii=False),
                 "text":{"format":{"type":"json_schema","name":"grant_assessment","strict":True,"schema":self.schema}},
                 "max_output_tokens":self.config["max_output_tokens"]}
        request=Request("https://api.openai.com/v1/responses",data=json.dumps(payload).encode(),method="POST",
                        headers={"Authorization":f"Bearer {self.api_key}","Content-Type":"application/json"})
        with urlopen(request,timeout=self.config["timeout_seconds"]) as response: data=json.load(response)
        output_text=next(part["text"] for item in data.get("output",[]) for part in item.get("content",[]) if part.get("type")=="output_text")
        return validate_output(json.loads(output_text))

