"""Regression tests for public funding adapters and date semantics."""
from datetime import date
import json
import csv
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch
from collectors.funding import (collect, policy_reason, rural_matches, rural_data,
                                embedded_array, ipyme_publication)
from run_sources import apply_answer, exclude_existing

COMMON = {'publication_last_days':90, 'missing_publication':'include_if_open',
          'exclude_closed':True, 'topic_terms':['agricultur'], 'max_linked_documents':0}
TODAY = date(2026,10,5)

class FundingTests(unittest.TestCase):
    def test_date_window_boundaries_and_open_fallback(self):
        self.assertEqual(policy_reason('2026-07-07','','unknown',TODAY,COMMON),'')
        self.assertEqual(policy_reason('2026-07-06','','open',TODAY,COMMON),'old_publication')
        self.assertEqual(policy_reason('2026-10-06','','open',TODAY,COMMON),'future_publication')
        self.assertEqual(policy_reason('','2026-10-05','open',TODAY,COMMON),'')
        self.assertEqual(policy_reason('','2026-10-04','open',TODAY,COMMON),'closed')
        self.assertEqual(policy_reason('','2026-11-01','unknown',TODAY,COMMON),'publication_unverified')
        self.assertEqual(policy_reason('','','open',TODAY,{**COMMON,'missing_publication':'exclude'}),'publication_unverified')

    def test_only_call_publication_not_bases_or_amendments(self):
        detail={'Boletines':[{'FechaPublicacion':'2025-01-01','NaturalezaAnuncio':'Bases reguladoras'},
                            {'FechaPublicacion':'2026-08-10','NaturalezaAnuncio':'Convocatoria'},
                            {'FechaPublicacion':'2026-09-01','NaturalezaAnuncio':'Modificación'}]}
        self.assertEqual(ipyme_publication(detail),'2026-08-10')

    def test_toolkit_multiselect_or_within_and_between_fields(self):
        row={'FICHE_TYPEFUND':'( Grant * 1 )','FILTER_THEMFOCUS_CODE':'2,9','FILTER_WHO_CODE':'3'}
        config={'support_code':1,'activity_codes':[4,9],'applicant_codes':[3]}
        self.assertTrue(rural_matches(row,config))
        self.assertFalse(rural_matches(row,{**config,'applicant_codes':[8]}))
        self.assertFalse(rural_matches({**row,'FICHE_TYPEFUND':'( Financial Instruments * 3 )'},config))

    def test_downloaded_javascript_is_parsed_as_data(self):
        self.assertEqual(embedded_array('const dataProposals = [{"id":1}];','dataProposals'),[{'id':1}])
        with self.assertRaises(ValueError):
            embedded_array('const dataProposals = [dangerous()];','dataProposals')
        bundle='"./ruraltoolkit.json":42;42:function(e){e.exports=JSON.parse(\'[ {"id": 1} ]\')}'
        self.assertEqual(rural_data(bundle,'ruraltoolkit.json'),[{'id':1}])

    def test_ipyme_zero_based_pagination_and_missing_pages_reported(self):
        class API:
            pages=[]
            def json(self,url):
                query=parse_qs(urlsplit(url).query)
                if '/detalle/' in url:
                    return {'Ayuda':{'Titulo':'Agricultura','TipoAyuda':'Subvención','esVigente':True},
                            'Boletines':[{'FechaPublicacion':'2026-09-01','NaturalezaAnuncio':'Convocatoria'}]}
                if 'pagina' not in query: return 3
                page=int(query['pagina'][0]); self.pages.append(page)
                return [{'Id':page,'Titulo':'Agricultura','Vigentes':True,'FechaSolicitud':'20/10/2026'}] if page<3 else []
        site={'id':'ipyme','name':'IPYME','url':'https://example.org/search','api_url':'https://example.org/api',
              'query':'agricultura','only_open':True,'grant_types':['subvención'],'page_size':1,'max_listing_pages':5}
        api=API(); rows,report=collect(site,COMMON,TODAY,api)
        self.assertEqual([0,1,2],api.pages)
        self.assertEqual(len(rows),3); self.assertEqual(report['errors'],[])
        rows,report=collect({**site,'max_listing_pages':2},COMMON,TODAY,API())
        self.assertTrue(report['errors'])

    def test_cascade_missing_date_is_not_database_created_time(self):
        record={'call_type':'Proposals','title':'Agriculture grant','permalink':'https://example.org/grant',
                'created_time':'2026-09-15','closes':'20/10/2026','domains':[{'value':'Agriculture'}],
                'technologies':[],'type_of_beneficiary':[],'links':{}}
        class API:
            def text(self,url): return 'const dataProposals = '+json.dumps([record])+';'
        site={'id':'cascade','name':'Cascade','url':'https://example.org','call_type':'Proposals',
              'domains':['Agriculture'],'technologies':[],'beneficiaries':[]}
        rows,report=collect(site,COMMON,TODAY,API())
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['publication_date'],'')
        self.assertNotIn('created_time',rows[0]['evidence'])
        rows,report=collect({**site,'domains':['Space']},COMMON,TODAY,API())
        self.assertEqual(rows,[])

    def test_existing_table_title_rows_and_url_deduplication(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"existing.csv"
            with path.open("w",encoding="utf-8",newline="") as handle:
                csv.writer(handle).writerows([["Grant tracker"],[],["Titulo","URL (link)"],
                                             ["Existing","https://example.org/grant/"]])
            existing=SimpleNamespace(url="https://example.org/grant#details")
            new=SimpleNamespace(url="https://example.org/new")
            self.assertEqual(exclude_existing([existing,new],path),[new])
            path.write_text("Wrong columns",encoding="utf-8")
            with self.assertRaises(ValueError): exclude_existing([new],path)

    def test_model_deadline_first_stage_and_conflicting_open_flags(self):
        item={'title':'Grant','url':'https://example.org/grant','source':'IPYME','site_id':'ipyme',
              'evidence':'Agriculture grant','publication_date':'2026-09-01','deadline':'2027-01-01',
              'application_status':'unknown','notes':['Listing says open but detail disagrees.'],'evidence_urls':[]}
        answer={'decision':'accept','confidence':.95,'title':'Grant','decision_reason':'Grant',
                'deadline':'2026-10-20','application_status':'open'}
        with patch('run_sources.classify_page',return_value=None):
            row=apply_answer(item,answer,{},'2026-10-05',.8)
        self.assertEqual(row.deadline,'2026-10-20')
        self.assertEqual(row.application_status,'unknown')

if __name__=='__main__': unittest.main()
