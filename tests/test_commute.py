from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo
from commute_agent import commute, storage
Z=ZoneInfo('Europe/London')
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.db=patch.object(storage,'DB',Path(self.tmp.name)/'test.db'); self.db.start()
  self.p={'timezone':'Europe/London','origin':{'address':'home','stop_id':'s'},'destination':{'address':'work'},'time_window':{'start':'08:50','end':'09:10'},'travel_days':commute.DAYS[:5],'advance_warning_minutes':30,'rail_line_ids':['bakerloo'],'interchange_search':'Elephant & Castle'}
 def tearDown(self): self.db.stop(); self.tmp.cleanup()
 def prepare(self):
  k=commute.profile_key(self.p)
  storage.write('baseline',{'key':k,'journeys':[],'discovery':{'candidates':[],'failures':[]}})
  storage.write('daily_plan',{'key':k,'date':'2026-11-18','check_from':'2026-11-18T07:30:00+00:00'})
 def test_weekend(self):
  for t in ['2026-11-20T10:00','2026-11-21T07:00']:
   self.assertEqual(str(commute.travel_date(self.p,datetime.fromisoformat(t).replace(tzinfo=Z))),'2026-11-23')
 def test_dst(self): self.assertEqual(commute.local_time('2026-07-01T07:00:00Z',Z).hour,8)
 def test_sample_filter(self):
  js=[{'startDateTime':'2026-11-18T08:00:00','arrivalDateTime':'2026-11-18T08:55:00','legs':[]},{'startDateTime':'2026-11-18T07:00:00','arrivalDateTime':'2026-11-18T08:40:00','legs':[]}]
  with patch.object(commute.api,'plan_journey',return_value={'journeys':js}) as call: plan=commute.get_plan(self.p,datetime(2026,11,18).date())
  self.assertEqual(call.call_count,3); self.assertEqual(len(plan['journeys']),1); self.assertIn('07:30',plan['check_from'])
 def test_expired(self):
  lines=[{'id':'bakerloo','lineStatuses':[{'statusSeverityDescription':'Closure','validityPeriods':[{'toDate':'2026-11-17T05:00:00Z'}]}]}]
  self.assertEqual(commute.status_issues(lines,datetime(2026,11,18,8,tzinfo=Z)),[])
 def test_missing_unknown_manual_no_events(self):
  self.prepare()
  with patch.object(commute.api,'get_line_status',return_value=[]): r=commute.check(self.p,datetime(2026,11,18,8,tzinfo=Z),manual=True)
  self.assertEqual(r['state'],'unknown'); self.assertEqual(storage.events(),[])
 def test_dedup_recovery(self):
  self.prepare(); now=datetime(2026,11,18,8,tzinfo=Z)
  warning=[{'id':'bakerloo','lineStatuses':[{'statusSeverityDescription':'Severe Delays','reason':'incident'}]}]
  with patch.object(commute.api,'get_line_status',return_value=warning), patch.object(commute,'get_plan',return_value={'journeys':[]}): commute.check(self.p,now); commute.check(self.p,now)
  self.assertEqual(len(storage.events()),1)
  with patch.object(commute.api,'get_line_status',return_value=[{'id':'bakerloo','lineStatuses':[{'statusSeverityDescription':'Good Service'}]}]): commute.check(self.p,now)
  self.assertEqual(len(storage.events()),2); self.assertEqual(storage.events()[0]['state'],'clear')
 def test_changed_settings(self):
  self.prepare(); self.p['advance_warning_minutes']=45
  with self.assertRaises(ValueError): commute.check(self.p,datetime(2026,11,18,8,tzinfo=Z))
 def test_waiting(self):
  self.prepare()
  with patch.object(commute.api,'get_line_status') as fetch: r=commute.check(self.p,datetime(2026,11,18,6,tzinfo=Z))
  fetch.assert_not_called(); self.assertEqual(r['state'],'waiting')
 def test_downstream(self):
  origin={'lineModeGroups':[{'modeName':'bus','lineIdentifier':['172']} ]}
  seq={'stopPointSequences':[{'stopPoint':[{'id':'early','name':'Elephant & Castle'},{'id':'s'},{'id':'late','name':'Elephant & Castle'}]}]}
  with patch.object(commute.api,'get_stop_details',return_value=origin),patch.object(commute.api,'get_route_sequence',return_value=seq): r=commute.discover(self.p)
  self.assertEqual({c['stop_id'] for c in r['candidates']},{'late'})

 def test_tfl_line_identifier_is_object(self):
  plan={'journeys':[{'legs':[{'routeOptions':[{'lineIdentifier':{'id':'bakerloo'}}]},{'routeOptions':[{'name':''}]}]}]}
  self.assertEqual(commute.line_ids(plan),{'bakerloo'})
