"""Interactive read-only login through the current multi-account DPAPI path."""
import argparse
import getpass
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from chaoxing_desktop.accounts import AccountStore
from chaoxing_desktop.config import defaults,to_payload


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--app',type=Path,help='Optional frozen application directory; default is current source')
    parser.add_argument('--output',type=Path,default=ROOT/'build/account-check.json')
    args=parser.parse_args()
    username=getpass.getpass('Account (hidden): ')
    password=getpass.getpass('Password (hidden): ')
    config=to_payload(defaults());config['common'].update(username=username,password=password)
    executable=[str(args.app.resolve()/'ChaoxingWorker.exe'),'--worker'] if args.app else [sys.executable,str(ROOT/'run.py'),'--worker']
    report={}
    with tempfile.TemporaryDirectory(prefix='cx-account-check-') as directory:
        store=AccountStore(Path(directory));row=store.add(username)
        command=dict(action='courses',demo=False,config=config,selected=[],data_dir=directory,account_id=row['id'])
        def read():
            result=subprocess.run(executable,input=json.dumps(command)+'\n',capture_output=True,
                                  encoding='utf-8',timeout=100)
            return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        try:
            events=read()
            ready=next((e for e in events if e.get('type')=='session_ready'),None)
            courses=next((e for e in events if e.get('type')=='courses'),None)
            report['password_login']=courses is not None
            if ready and courses:
                store.update(row['id'],uid=ready['uid'])
                expected={(str(c['courseId']),str(c['clazzId'])) for c in courses['courses']}
                report['course_count']=len(expected)
                report['encrypted_cookie_saved']=store.cookie_path(row['id']).is_file()
                config['common'].update(password='',use_cookies=True)
                events=read()
                restored=next((e for e in events if e.get('type')=='courses'),None)
                report['cookie_login']=restored is not None
                report['same_courses']=restored is not None and expected=={(str(c['courseId']),str(c['clazzId'])) for c in restored['courses']}
            report['success']=all(report.get(key,False) for key in ('password_login','encrypted_cookie_saved','cookie_login','same_courses'))
        finally:
            username=password='';config['common']['password']=''
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
    return 0 if report['success'] else 1


if __name__=='__main__':raise SystemExit(main())
