"""Germinate: collect, pre-filter, optionally analyze, and export grant opportunities."""
import argparse,csv,json,sys
from dataclasses import asdict,dataclass
from datetime import datetime,timezone
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.parse import urlparse
from agent.client import OpenAIAgent
from collectors.html import Link,extract_links,extract_text,fetch_html
from collectors.interactive import limitation_note
ROOT=Path(__file__).resolve().parent

@dataclass
class Result:
    source:str; collector_type:str; title:str; url:str; decision:str; score:int
    matched_grant_terms:str; matched_topics:str; rejection_terms:str; checked_at:str; note:str
    agent_used:bool=False; agent_decision:str=""; agent_confidence:str=""; grant_status:str=""
    deadline:str=""; amount_min:str=""; amount_max:str=""; currency:str=""
    eligible_countries:str=""; eligible_applicants:str=""; topics:str=""; consortium_required:str=""; agent_reason:str=""

def load_json(path): return json.loads(Path(path).read_text(encoding="utf-8-sig"))
def find_terms(text,terms):
    lowered=text.casefold(); return sorted({term for term in terms if term.casefold() in lowered})

def classify(link,source,rules,checked_at):
    searchable=f"{link.title} {link.url}"; grants=find_terms(searchable,rules["grant_terms"])
    topics=find_terms(searchable,rules["topic_terms"]); rejected=find_terms(searchable,rules["rejection_terms"])
    if not grants and not topics and not rejected: return None
    score=len(grants)*2+len(topics)-len(rejected)*4
    if rejected: decision,note="rejected","Contains an excluded financing or procurement term."
    elif grants and topics and score>=rules["minimum_score"]: decision,note="candidate","Relevant under preliminary rules; full-page verification remains."
    else: decision,note="review","Grant type or thematic fit is incomplete."
    return Result(source["name"],source["collector_type"],link.title,link.url,decision,score,"; ".join(grants),"; ".join(topics),"; ".join(rejected),checked_at,note)

def classify_page(link,page_text,source,rules,checked_at):
    """Classify an opportunity using its link and full visible page text."""
    searchable=f"{link.title} {link.url} {page_text}"
    grants=find_terms(searchable,rules["grant_terms"]); topics=find_terms(searchable,rules["topic_terms"])
    rejected=find_terms(searchable,rules["rejection_terms"])
    if not grants and not topics and not rejected: return None
    score=len(grants)*2+len(topics)-len(rejected)*4
    if rejected: decision,note="rejected","Full page contains an excluded financing or procurement term."
    elif grants and topics and score>=rules["minimum_score"]: decision,note="candidate","Grant and relevant theme confirmed in the full page text."
    else: decision,note="review","Full page does not clearly confirm both grant type and thematic fit."
    return Result(source["name"],source["collector_type"],link.title,link.url,decision,score,"; ".join(grants),"; ".join(topics),"; ".join(rejected),checked_at,note)

def is_same_site(url,start_url):
    host=urlparse(url).hostname or ""; start_host=urlparse(start_url).hostname or ""
    return host.casefold().removeprefix("www.")==start_host.casefold().removeprefix("www.")

def is_promising_link(link,rules):
    searchable=f"{link.title} {link.url}"
    return bool(find_terms(searchable,rules["grant_terms"]+rules["topic_terms"])) and not find_terms(searchable,rules["rejection_terms"])

def crawl_start_url(start_url,source,rules,checked_at,fetcher=fetch_html):
    """Follow relevant same-site links and classify their full pages."""
    max_depth=int(source.get("max_depth",2)); max_pages=int(source.get("max_pages",30))
    queue=[(Link(source["name"],start_url),0)]; visited=set(); results=[]; errors=[]
    while queue and len(visited)<max_pages:
        link,depth=queue.pop(0)
        normalized=link.url.casefold()
        if normalized in visited: continue
        visited.add(normalized)
        try:
            html=fetcher(link.url); page_text=extract_text(html)
        except (HTTPError,URLError,TimeoutError,ValueError) as exc:
            errors.append(f"{source['name']} | {link.url} | {exc}"); continue
        if depth>0:
            result=classify_page(link,page_text,source,rules,checked_at)
            if result: results.append(result)
        if depth>=max_depth: continue
        for child in extract_links(html,link.url):
            if child.url.casefold() not in visited and is_same_site(child.url,start_url) and is_promising_link(child,rules):
                queue.append((child,depth+1))
    return results,errors

def inspect_html(html,base_url,source,rules,checked_at):
    return [r for link in extract_links(html,base_url) if (r:=classify(link,source,rules,checked_at))]

def run_demo(rules,checked_at):
    html=(ROOT/"demo"/"sample_source.html").read_text(encoding="utf-8")
    return inspect_html(html,"https://example.org/funding/",{"name":"Demo Environmental Fund","collector_type":"html"},rules,checked_at)

def run_live(sources,rules,checked_at):
    results,errors=[],[]
    for source in sources:
        print(f"Checking {source['name']}...",flush=True)
        if source["collector_type"]=="interactive_search":
            results.append(Result(source["name"],source["collector_type"],"Specialized collector required",source["start_urls"][0],"needs_specialized_collector",0,"","","",checked_at,limitation_note())); continue
        for url in source["start_urls"]:
            found,failures=crawl_start_url(url,source,rules,checked_at)
            results.extend(found); errors.extend(failures)
    return results,errors

def enrich(results,agent_config):
    agent=OpenAIAgent(agent_config); used=0; errors=[]
    for result in results:
        if result.decision not in {"candidate","review"} or used>=agent_config["max_pages_per_run"]: continue
        try:
            page_text=extract_text(fetch_html(result.url))
            answer=agent.analyze(source=result.source,url=result.url,page_text=page_text,preliminary={"decision":result.decision,"score":result.score})
            used+=1; result.agent_used=True; result.agent_decision=answer["decision"]; result.agent_confidence=str(answer["confidence"])
            result.grant_status=answer["grant_status"]; result.deadline=answer["deadline"] or ""; result.amount_min=answer["amount_min"] or ""
            result.amount_max=answer["amount_max"] or ""; result.currency=answer["currency"] or ""
            result.eligible_countries="; ".join(answer["eligible_countries"]); result.eligible_applicants="; ".join(answer["eligible_applicants"])
            result.topics="; ".join(answer["topics"]); result.consortium_required=str(answer["consortium_required"] or "")
            result.agent_reason=answer["decision_reason"]
            if answer["confidence"]<agent_config["minimum_confidence"]: result.agent_decision="review"
        except Exception as exc: errors.append(f"Agent | {result.url} | {exc}")
    return errors

def deduplicate(results):
    unique={}
    for result in results:
        key=(result.source.casefold(),result.url.casefold())
        if key not in unique or result.score>unique[key].score: unique[key]=result
    return list(unique.values())

def write_csv(results,output_path):
    output_path.parent.mkdir(parents=True,exist_ok=True)
    with output_path.open("w",newline="",encoding="utf-8-sig") as handle:
        writer=csv.DictWriter(handle,fieldnames=list(Result.__dataclass_fields__)); writer.writeheader(); writer.writerows(asdict(r) for r in results)

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--demo",action="store_true"); parser.add_argument("--agent",action="store_true")
    parser.add_argument("--output",type=Path,default=ROOT/"output"/"opportunities.csv"); args=parser.parse_args()
    rules=load_json(ROOT/"config"/"rules.json"); sources=load_json(ROOT/"config"/"sources.json"); config=load_json(ROOT/"config"/"agent.json")
    checked=datetime.now(timezone.utc).isoformat(timespec="seconds")
    results,errors=(run_demo(rules,checked),[]) if args.demo else run_live(sources,rules,checked)
    results=deduplicate(results)
    if args.agent or config["enabled"]: errors.extend(enrich(results,config))
    write_csv(results,args.output); print(f"Saved {len(results)} records to {args.output}")
    for error in errors: print(error,file=sys.stderr)
    return 0 if results else 1
if __name__=="__main__": raise SystemExit(main())
