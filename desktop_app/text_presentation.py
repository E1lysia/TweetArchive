"""Reading-only paragraph layout; archived text and translation hashes stay intact."""
import re


def readable_text(value,post_type=''):
    value=str(value or '').replace('\r\n','\n').replace('\r','\n').strip()
    if post_type=='retweet':value=re.sub(r'^RT\s+@[A-Za-z0-9_]+[:：]\s*','',value)
    paragraphs=[]
    structural=re.compile(r'^(?:https?://|[@#]|[•●・※]|\d+[.、)])')
    for paragraph in re.split(r'\n\s*\n',value):
        rows=[line.strip() for line in paragraph.split('\n') if line.strip()]
        combined=''
        for row in rows:
            if not combined:combined=row;continue
            previous=combined.rsplit('\n',1)[-1]
            if structural.match(row) or structural.match(previous):
                combined+='\n'+row
            else:
                # CJK soft wraps can be joined directly; Latin words need a space.
                cjk=lambda char:'\u3040'<=char<='\u30ff' or '\u3400'<=char<='\u9fff'
                combined+=('' if cjk(previous[-1]) and cjk(row[0]) else ' ')+row
        if combined:paragraphs.append(combined)
    return '\n\n'.join(paragraphs)
