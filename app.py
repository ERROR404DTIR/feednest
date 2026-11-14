#!/usr/bin/env python3
"""FeedNest — a tiny offline-first RSS/Atom reader. Python 3.9+, standard library only."""
import argparse, datetime as dt, email.utils, sqlite3, sys, textwrap, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path
DB = Path(__file__).with_name("feednest.db")
def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
    c.executescript("""CREATE TABLE IF NOT EXISTS feeds(id INTEGER PRIMARY KEY,url TEXT UNIQUE,title TEXT);
    CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY,feed_id INTEGER,title TEXT,link TEXT UNIQUE,summary TEXT,published TEXT,read INTEGER DEFAULT 0,FOREIGN KEY(feed_id) REFERENCES feeds(id));""")
    return c
def parse_date(s):
    if not s: return ""
    try: return email.utils.parsedate_to_datetime(s).isoformat()
    except Exception: return s
def fetch(url):
    req=urllib.request.Request(url,headers={"User-Agent":"FeedNest/1.0"})
    with urllib.request.urlopen(req,timeout=18) as r: raw=r.read(4_000_000)
    root=ET.fromstring(raw); ns={"a":"http://www.w3.org/2005/Atom"}
    if root.tag.endswith("feed"):
        title=root.findtext("a:title",default="Untitled",namespaces=ns); entries=root.findall("a:entry",ns)
        rows=[]
        for e in entries:
            link=next((x.get("href") for x in e.findall("a:link",ns) if x.get("rel","alternate")=="alternate"),"")
            rows.append((e.findtext("a:title",default="(untitled)",namespaces=ns),link,e.findtext("a:summary",default="",namespaces=ns),e.findtext("a:updated",default="",namespaces=ns)))
    else:
        ch=root.find("channel"); title=ch.findtext("title","Untitled") if ch is not None else "Untitled"; entries=ch.findall("item") if ch is not None else []
        rows=[(e.findtext("title","(untitled)"),e.findtext("link",""),e.findtext("description",""),parse_date(e.findtext("pubDate",""))) for e in entries]
    return title,rows
def main():
    p=argparse.ArgumentParser(description="Offline-first RSS/Atom reader"); s=p.add_subparsers(dest="cmd",required=True)
    a=s.add_parser("add",help="subscribe to a feed"); a.add_argument("url")
    s.add_parser("refresh",help="fetch all subscribed feeds")
    l=s.add_parser("list",help="list cached articles"); l.add_argument("-n",type=int,default=20); l.add_argument("--all",action="store_true")
    r=s.add_parser("read",help="read an article by ID"); r.add_argument("id",type=int)
    q=s.add_parser("search",help="search cached titles and summaries"); q.add_argument("query")
    d=s.add_parser("remove",help="remove a feed by ID"); d.add_argument("id",type=int)
    args=p.parse_args(); c=db()
    if args.cmd=="add":
        try: title,_=fetch(args.url); c.execute("INSERT OR IGNORE INTO feeds(url,title) VALUES(?,?)",(args.url,title)); c.commit(); print("Subscribed:",title)
        except Exception as e: sys.exit("Feed error: "+str(e))
    elif args.cmd=="refresh":
        for f in c.execute("SELECT * FROM feeds").fetchall():
            try:
                title,rows=fetch(f["url"]); c.execute("UPDATE feeds SET title=? WHERE id=?",(title,f["id"]))
                c.executemany("INSERT OR IGNORE INTO items(feed_id,title,link,summary,published) VALUES(?,?,?,?,?)",[(f["id"],*x) for x in rows if x[1]])
                print(f"✓ {title}: {len(rows)} entries checked")
            except Exception as e: print(f"! {f['url']}: {e}")
        c.commit()
    elif args.cmd in ("list","search"):
        sql="SELECT i.*,f.title AS source FROM items i JOIN feeds f ON f.id=i.feed_id"
        if args.cmd=="search": sql+=" WHERE i.title LIKE ? OR i.summary LIKE ?"; rows=c.execute(sql+" ORDER BY i.id DESC",("%"+args.query+"%","%"+args.query+"%"))
        else:
            if not args.all: sql+=" WHERE i.read=0"
            rows=c.execute(sql+" ORDER BY i.id DESC LIMIT ?",(args.n,))
        for x in rows: print(f"[{x['id']}] {'✓' if x['read'] else '•'} {x['title']}\n    {x['source']} | {x['published']}\n    {x['link']}")
    elif args.cmd=="read":
        x=c.execute("SELECT * FROM items WHERE id=?",(args.id,)).fetchone()
        if not x: sys.exit("Article not found")
        print("\n"+x["title"]+"\n"+x["link"]+"\n"+"-"*60+"\n"+textwrap.fill(x["summary"],88)); c.execute("UPDATE items SET read=1 WHERE id=?",(args.id,)); c.commit()
    elif args.cmd=="remove":
        c.execute("DELETE FROM items WHERE feed_id=?",(args.id,)); c.execute("DELETE FROM feeds WHERE id=?",(args.id,)); c.commit(); print("Feed removed.")
    c.close()
if __name__=="__main__": main()
