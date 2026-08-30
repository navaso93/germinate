import importlib.util,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("germinate_app",ROOT/"germinate.py")
APP=importlib.util.module_from_spec(SPEC); sys.modules[SPEC.name]=APP; SPEC.loader.exec_module(APP)

class GerminateTests(unittest.TestCase):
    def setUp(self):
        self.rules=APP.load_json(ROOT/"config"/"rules.json"); self.source={"name":"Test","collector_type":"html"}; self.checked="2026-08-30T00:00:00+00:00"
    def test_relevant_grant(self):
        self.assertEqual(APP.classify(APP.Link("Regenerative ecosystem restoration grant","https://x/call"),self.source,self.rules,self.checked).decision,"candidate")
    def test_loan_rejected(self):
        self.assertEqual(APP.classify(APP.Link("Sustainable agriculture loan","https://x/loan"),self.source,self.rules,self.checked).decision,"rejected")
    def test_irrelevant_ignored(self):
        self.assertIsNone(APP.classify(APP.Link("Contact us","https://x/contact"),self.source,self.rules,self.checked))
    def test_agent_validation(self):
        from agent.client import validate_output
        value={"title":"A","grant_status":"confirmed","decision":"accept","decision_reason":"clear","confidence":0.9}
        self.assertEqual(validate_output(value),value)
    def test_deduplicate(self):
        a=APP.Result("S","html","A","https://x","review",1,"","","",self.checked,"")
        b=APP.Result("S","html","B","https://x","candidate",5,"","","",self.checked,"")
        self.assertEqual(APP.deduplicate([a,b])[0].title,"B")
if __name__=="__main__": unittest.main()
